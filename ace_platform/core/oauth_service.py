"""OAuth authentication service layer.

Handles user creation, account linking, and OAuth account management.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.db.models import OAuthProvider, User, UserOAuthAccount


class OAuthService:
    """Service for handling OAuth authentication logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_or_create_user_from_oauth(
        self,
        provider: OAuthProvider,
        provider_user_id: str,
        email: str,
        user_info: dict,
        access_token: str | None = None,
        refresh_token: str | None = None,
        token_expires_at: datetime | None = None,
    ) -> tuple[User, bool]:
        """Get existing user or create new one from OAuth data.

        Account linking logic:
        1. Check if OAuth account already exists -> return linked user
        2. Check if user with same email exists -> link OAuth to existing user
        3. Create new user and OAuth account

        Args:
            provider: OAuth provider (google, github)
            provider_user_id: User ID from the OAuth provider
            email: User's email from OAuth provider
            user_info: Raw user info from OAuth provider
            access_token: OAuth access token (optional)
            refresh_token: OAuth refresh token (optional)
            token_expires_at: Token expiration time (optional)

        Returns:
            Tuple of (User, is_new_user)
        """
        # 1. Check for existing OAuth link
        existing_oauth = await self._get_oauth_account(provider, provider_user_id)
        if existing_oauth:
            # Update tokens if provided
            if access_token:
                existing_oauth.access_token = access_token
                existing_oauth.refresh_token = refresh_token
                existing_oauth.token_expires_at = token_expires_at
                existing_oauth.raw_user_info = user_info
                await self.db.commit()

            # Load user relationship
            await self.db.refresh(existing_oauth, ["user"])
            return existing_oauth.user, False

        # 2. Check for existing user by email (only auto-link if email is verified)
        existing_user = await self._get_user_by_email(email)
        if existing_user and existing_user.email_verified:
            # Link OAuth to existing verified account
            oauth_account = UserOAuthAccount(
                user_id=existing_user.id,
                provider=provider,
                provider_user_id=provider_user_id,
                provider_email=email,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires_at=token_expires_at,
                raw_user_info=user_info,
            )
            self.db.add(oauth_account)
            await self.db.commit()
            return existing_user, False
        # Note: If existing_user exists but email is NOT verified, we create a new
        # account. This prevents account hijacking where an attacker could create
        # an OAuth account with an unverified user's email to gain access.

        # 3. Create new user
        new_user = User(
            email=email.lower(),
            hashed_password=None,  # OAuth users don't have passwords initially
            email_verified=True,  # OAuth emails are verified by provider
        )
        self.db.add(new_user)
        await self.db.flush()  # Get user ID

        oauth_account = UserOAuthAccount(
            user_id=new_user.id,
            provider=provider,
            provider_user_id=provider_user_id,
            provider_email=email,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
            raw_user_info=user_info,
        )
        self.db.add(oauth_account)
        await self.db.commit()
        await self.db.refresh(new_user)

        return new_user, True

    async def _get_oauth_account(
        self, provider: OAuthProvider, provider_user_id: str
    ) -> UserOAuthAccount | None:
        """Get OAuth account by provider and provider user ID."""
        result = await self.db.execute(
            select(UserOAuthAccount)
            .where(UserOAuthAccount.provider == provider)
            .where(UserOAuthAccount.provider_user_id == provider_user_id)
        )
        return result.scalar_one_or_none()

    async def _get_user_by_email(self, email: str) -> User | None:
        """Get user by email."""
        result = await self.db.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def get_user_oauth_accounts(self, user_id: UUID) -> list[UserOAuthAccount]:
        """Get all OAuth accounts linked to a user."""
        result = await self.db.execute(
            select(UserOAuthAccount).where(UserOAuthAccount.user_id == user_id)
        )
        return list(result.scalars().all())

    async def unlink_oauth_account(self, user_id: UUID, provider: OAuthProvider) -> bool:
        """Unlink an OAuth provider from a user account.

        Prevents unlinking if it's the only auth method.

        Args:
            user_id: User ID
            provider: OAuth provider to unlink

        Returns:
            True if unlinked successfully

        Raises:
            ValueError: If unlinking would leave user with no auth method
        """
        user = await self.db.get(User, user_id)
        if not user:
            return False

        # Check if user has password or other OAuth accounts
        oauth_accounts = await self.get_user_oauth_accounts(user_id)
        has_password = user.hashed_password is not None
        other_oauth_count = sum(1 for acc in oauth_accounts if acc.provider != provider)

        if not has_password and other_oauth_count == 0:
            raise ValueError("Cannot unlink the only authentication method")

        # Find and delete the OAuth account
        for acc in oauth_accounts:
            if acc.provider == provider:
                await self.db.delete(acc)
                await self.db.commit()
                return True

        return False

    async def link_oauth_account(
        self,
        user_id: UUID,
        provider: OAuthProvider,
        provider_user_id: str,
        email: str,
        user_info: dict,
        access_token: str | None = None,
        refresh_token: str | None = None,
        token_expires_at: datetime | None = None,
    ) -> UserOAuthAccount:
        """Link a new OAuth account to an existing user.

        Args:
            user_id: User ID to link to
            provider: OAuth provider
            provider_user_id: User ID from the OAuth provider
            email: Email from OAuth provider
            user_info: Raw user info from OAuth provider
            access_token: OAuth access token (optional)
            refresh_token: OAuth refresh token (optional)
            token_expires_at: Token expiration time (optional)

        Returns:
            Created UserOAuthAccount

        Raises:
            ValueError: If OAuth account is already linked to another user
        """
        # Check if this OAuth account is already linked
        existing_oauth = await self._get_oauth_account(provider, provider_user_id)
        if existing_oauth:
            if existing_oauth.user_id == user_id:
                # Already linked to this user, update tokens
                existing_oauth.access_token = access_token
                existing_oauth.refresh_token = refresh_token
                existing_oauth.token_expires_at = token_expires_at
                existing_oauth.raw_user_info = user_info
                await self.db.commit()
                return existing_oauth
            else:
                raise ValueError(f"This {provider.value} account is already linked to another user")

        # Check if user already has this provider linked
        user_accounts = await self.get_user_oauth_accounts(user_id)
        for acc in user_accounts:
            if acc.provider == provider:
                raise ValueError(f"You already have a {provider.value} account linked")

        # Create new OAuth link
        oauth_account = UserOAuthAccount(
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            provider_email=email,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
            raw_user_info=user_info,
        )
        self.db.add(oauth_account)
        await self.db.commit()
        await self.db.refresh(oauth_account)
        return oauth_account
