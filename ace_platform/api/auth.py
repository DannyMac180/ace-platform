"""Authentication dependencies for FastAPI and MCP.

This module provides authentication middleware and dependencies for:
- JWT bearer token authentication (for user sessions)
- API key authentication (for MCP and programmatic access)
- Scope-based authorization
- Proper HTTP error responses (401/403)

Usage in FastAPI routes:
    # JWT-based auth (for web/mobile clients)
    @app.get("/me")
    async def get_current_user(user: User = Depends(require_user)):
        return {"email": user.email}

    # API key auth (for MCP/programmatic access)
    @app.get("/playbooks")
    async def list_playbooks(auth: AuthContext = Depends(require_auth)):
        return {"user_id": str(auth.user.id)}

    @app.post("/playbooks/{id}/evolve")
    async def evolve_playbook(
        id: UUID,
        auth: AuthContext = Depends(require_scope("evolution:write")),
    ):
        ...
"""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.core.api_keys import authenticate_api_key_async, check_scope
from ace_platform.core.limits import SubscriptionTier, get_tier_limits
from ace_platform.core.security import (
    InvalidTokenError,
    TokenExpiredError,
    decode_access_token,
)
from ace_platform.db.models import ApiKey, SubscriptionStatus, User

from .deps import get_db

# Header name for API key authentication
API_KEY_HEADER = "X-API-Key"
AUTHORIZATION_HEADER = "Authorization"
BEARER_PREFIX = "Bearer "


class AuthenticationError(HTTPException):
    """Raised when authentication fails (401)."""

    def __init__(self, detail: str = "Invalid or missing API key"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


class AuthorizationError(HTTPException):
    """Raised when authorization fails (403)."""

    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
        )


@dataclass
class AuthContext:
    """Authentication context containing the authenticated user and API key."""

    user: User
    api_key: ApiKey

    @property
    def user_id(self):
        """Get the authenticated user's ID."""
        return self.user.id

    @property
    def scopes(self) -> list[str]:
        """Get the API key's scopes."""
        return self.api_key.scopes

    def has_scope(self, required_scope: str) -> bool:
        """Check if the API key has a required scope."""
        return check_scope(self.api_key, required_scope)


def extract_api_key(
    x_api_key: str | None = Header(None, alias=API_KEY_HEADER),
    authorization: str | None = Header(None, alias=AUTHORIZATION_HEADER),
) -> str | None:
    """Extract API key from request headers.

    Supports two formats:
    - X-API-Key header (preferred for API keys)
    - Authorization: Bearer <key> header

    Args:
        x_api_key: Value from X-API-Key header.
        authorization: Value from Authorization header.

    Returns:
        The API key if found, None otherwise.
    """
    # Prefer X-API-Key header
    if x_api_key:
        return x_api_key

    # Fall back to Authorization header
    if authorization and authorization.startswith(BEARER_PREFIX):
        return authorization[len(BEARER_PREFIX) :]

    return None


async def get_optional_auth(
    db: Annotated[AsyncSession, Depends(get_db)],
    api_key: Annotated[str | None, Depends(extract_api_key)],
) -> AuthContext | None:
    """Get authentication context if API key is provided.

    This dependency does not require authentication - it returns None
    if no API key is provided. Use `require_auth` for mandatory auth.

    Args:
        db: Database session.
        api_key: API key from headers.

    Returns:
        AuthContext if authenticated, None if no key provided.

    Raises:
        AuthenticationError: If key is provided but invalid.
    """
    if not api_key:
        return None

    result = await authenticate_api_key_async(db, api_key)
    if not result:
        raise AuthenticationError("Invalid or revoked API key")

    api_key_record, user = result
    return AuthContext(user=user, api_key=api_key_record)


async def require_auth(
    auth: Annotated[AuthContext | None, Depends(get_optional_auth)],
) -> AuthContext:
    """Require authentication for a route.

    Use this dependency to protect routes that require authentication.

    Args:
        auth: Optional auth context from get_optional_auth.

    Returns:
        AuthContext for the authenticated user.

    Raises:
        AuthenticationError: If no valid API key is provided.
    """
    if not auth:
        raise AuthenticationError("API key required")
    return auth


def require_scope(required_scope: str):
    """Create a dependency that requires a specific scope.

    Use this factory to create dependencies for routes that require
    specific permissions.

    Args:
        required_scope: The scope required to access the route.

    Returns:
        A FastAPI dependency function.

    Usage:
        @app.post("/evolve")
        async def evolve(auth: AuthContext = Depends(require_scope("evolution:write"))):
            ...
    """

    async def scope_checker(
        auth: Annotated[AuthContext, Depends(require_auth)],
    ) -> AuthContext:
        """Check that the authenticated user has the required scope."""
        if not auth.has_scope(required_scope):
            raise AuthorizationError(f"API key lacks required scope: {required_scope}")
        return auth

    return scope_checker


def require_any_scope(*required_scopes: str):
    """Create a dependency that requires any of the specified scopes.

    Args:
        *required_scopes: Scopes where at least one must be present.

    Returns:
        A FastAPI dependency function.

    Usage:
        @app.get("/playbooks")
        async def list_playbooks(
            auth: AuthContext = Depends(require_any_scope("playbooks:read", "playbooks:*"))
        ):
            ...
    """

    async def scope_checker(
        auth: Annotated[AuthContext, Depends(require_auth)],
    ) -> AuthContext:
        """Check that the authenticated user has at least one required scope."""
        for scope in required_scopes:
            if auth.has_scope(scope):
                return auth

        scopes_str = ", ".join(required_scopes)
        raise AuthorizationError(f"API key requires one of these scopes: {scopes_str}")

    return scope_checker


# Type aliases for cleaner dependency injection
OptionalAuth = Annotated[AuthContext | None, Depends(get_optional_auth)]
RequiredAuth = Annotated[AuthContext, Depends(require_auth)]


# =============================================================================
# JWT-based User Authentication
# =============================================================================
# These dependencies are for JWT bearer token authentication, typically used
# by web/mobile clients after login. For MCP/programmatic access, use the
# API key-based authentication above.


def extract_bearer_token(
    authorization: str | None = Header(None, alias=AUTHORIZATION_HEADER),
) -> str | None:
    """Extract JWT bearer token from Authorization header.

    Args:
        authorization: Value from Authorization header.

    Returns:
        The bearer token if found, None otherwise.
    """
    if authorization and authorization.startswith(BEARER_PREFIX):
        return authorization[len(BEARER_PREFIX) :]
    return None


async def get_optional_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[str | None, Depends(extract_bearer_token)],
) -> User | None:
    """Get the current user from JWT token if provided.

    This dependency does not require authentication - it returns None
    if no token is provided. Use `require_user` for mandatory auth.

    Args:
        db: Database session.
        token: JWT token from Authorization header.

    Returns:
        User if authenticated, None if no token provided.

    Raises:
        AuthenticationError: If token is provided but invalid/expired.
    """
    if not token:
        return None

    try:
        payload = decode_access_token(token)
    except TokenExpiredError:
        raise AuthenticationError("Token has expired")
    except InvalidTokenError:
        # Use generic message to avoid leaking token parsing details
        raise AuthenticationError("Invalid token")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise AuthenticationError("Invalid token: missing subject")

    try:
        user_id = UUID(user_id_str)
    except ValueError:
        raise AuthenticationError("Invalid token: malformed user ID")

    # Fetch user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise AuthenticationError("User not found")

    if not user.is_active:
        raise AuthenticationError("User account is disabled")

    return user


async def require_user(
    user: Annotated[User | None, Depends(get_optional_user)],
) -> User:
    """Require JWT authentication for a route.

    Use this dependency to protect routes that require user authentication.

    Args:
        user: Optional user from get_optional_user.

    Returns:
        The authenticated User.

    Raises:
        AuthenticationError: If no valid token is provided.
    """
    if not user:
        raise AuthenticationError("Authentication required")
    return user


async def require_active_user(
    user: Annotated[User, Depends(require_user)],
) -> User:
    """Require an active user for a route.

    Note: This is functionally equivalent to require_user since is_active
    is already checked in get_optional_user. This dependency exists for
    semantic clarity in route definitions - use it when the route's logic
    specifically requires an active account status.

    Args:
        user: The authenticated user (already verified as active).

    Returns:
        The authenticated active User.
    """
    return user


async def require_verified_user(
    user: Annotated[User, Depends(require_user)],
) -> User:
    """Require a verified user for a route.

    Use this for routes that require email verification.

    Args:
        user: The authenticated user.

    Returns:
        The authenticated verified User.

    Raises:
        AuthorizationError: If user's email is not verified.
    """
    if not user.email_verified:
        raise AuthorizationError("Email verification required")
    return user


# Type aliases for JWT-based auth
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
RequiredUser = Annotated[User, Depends(require_user)]
ActiveUser = Annotated[User, Depends(require_active_user)]
VerifiedUser = Annotated[User, Depends(require_verified_user)]


# =============================================================================
# Subscription Validation
# =============================================================================
# These dependencies check subscription status and enforce tier-based limits.
# They build on top of JWT auth to add billing/subscription checks.


class SubscriptionError(HTTPException):
    """Raised when subscription check fails (402 Payment Required or 403)."""

    def __init__(self, detail: str, status_code: int = status.HTTP_403_FORBIDDEN):
        super().__init__(
            status_code=status_code,
            detail=detail,
        )


def get_user_tier(user: User) -> SubscriptionTier:
    """Get the subscription tier for a user.

    Args:
        user: The user to check.

    Returns:
        The user's subscription tier, defaulting to FREE.
    """
    if not user.subscription_tier:
        return SubscriptionTier.FREE
    try:
        return SubscriptionTier(user.subscription_tier)
    except ValueError:
        return SubscriptionTier.FREE


async def require_active_subscription(
    user: Annotated[User, Depends(require_user)],
) -> User:
    """Require an active subscription or free tier.

    This dependency allows:
    - Users with subscription_status = NONE (free tier)
    - Users with subscription_status = ACTIVE

    It rejects:
    - Users with PAST_DUE, CANCELED, or UNPAID subscriptions

    Args:
        user: The authenticated user.

    Returns:
        The user if subscription is valid.

    Raises:
        SubscriptionError: If subscription is in a bad state.
    """
    # Free tier (NONE) is always allowed
    if user.subscription_status == SubscriptionStatus.NONE:
        return user

    # Active subscriptions are allowed
    if user.subscription_status == SubscriptionStatus.ACTIVE:
        return user

    # All other statuses require action
    if user.subscription_status == SubscriptionStatus.PAST_DUE:
        raise SubscriptionError(
            "Your subscription payment is past due. Please update your payment method.",
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
        )
    elif user.subscription_status == SubscriptionStatus.CANCELED:
        raise SubscriptionError(
            "Your subscription has been canceled. Please resubscribe to continue.",
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
        )
    elif user.subscription_status == SubscriptionStatus.UNPAID:
        raise SubscriptionError(
            "Your subscription is unpaid. Please update your payment method.",
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
        )
    else:
        raise SubscriptionError("Invalid subscription status")

    return user


def require_tier(minimum_tier: SubscriptionTier):
    """Create a dependency that requires a minimum subscription tier.

    Use this factory to protect routes that require specific tier levels.

    Args:
        minimum_tier: The minimum tier required.

    Returns:
        A FastAPI dependency function.

    Usage:
        @app.post("/premium-feature")
        async def premium_feature(user: User = Depends(require_tier(SubscriptionTier.STARTER))):
            ...
    """
    tier_order = [
        SubscriptionTier.FREE,
        SubscriptionTier.STARTER,
        SubscriptionTier.PROFESSIONAL,
        SubscriptionTier.ENTERPRISE,
    ]

    async def tier_checker(
        user: Annotated[User, Depends(require_active_subscription)],
    ) -> User:
        """Check that the user has at least the minimum required tier."""
        user_tier = get_user_tier(user)

        user_tier_index = tier_order.index(user_tier)
        min_tier_index = tier_order.index(minimum_tier)

        if user_tier_index < min_tier_index:
            raise SubscriptionError(
                f"This feature requires a {minimum_tier.value} subscription or higher. "
                f"Your current tier is {user_tier.value}.",
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
            )
        return user

    return tier_checker


def require_feature(feature: str):
    """Create a dependency that requires a specific feature.

    Use this to check tier-based feature flags like:
    - can_use_premium_models
    - can_export_data
    - priority_support

    Args:
        feature: The feature name to check.

    Returns:
        A FastAPI dependency function.

    Usage:
        @app.post("/export")
        async def export_data(user: User = Depends(require_feature("can_export_data"))):
            ...
    """

    async def feature_checker(
        user: Annotated[User, Depends(require_active_subscription)],
    ) -> User:
        """Check that the user's tier has the required feature."""
        user_tier = get_user_tier(user)
        limits = get_tier_limits(user_tier)

        if not getattr(limits, feature, False):
            raise SubscriptionError(
                f"This feature requires an upgraded subscription. "
                f"Your current tier ({user_tier.value}) does not include {feature.replace('_', ' ')}.",
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
            )
        return user

    return feature_checker


# Type aliases for subscription-based auth
SubscribedUser = Annotated[User, Depends(require_active_subscription)]
