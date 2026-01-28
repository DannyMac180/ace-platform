"""Tests for OAuth authentication.

These tests verify:
1. OAuth provider discovery endpoints
2. OAuth login/callback flow
3. Account linking and unlinking
4. Security: unverified email auto-link prevention
5. OAuth service business logic

Note: OAuth route tests use shared fixtures from conftest.py that disable
rate limiting (app_no_rate_limit, client_no_rate_limit, etc.) to prevent
rate limit interference between tests.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ace_platform.core.security import hash_password
from ace_platform.db.models import OAuthProvider, User, UserOAuthAccount

# =============================================================================
# OAuth Routes Tests
# =============================================================================


class TestOAuthProviders:
    """Tests for OAuth provider discovery endpoint."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_oauth_routes_registered(self, app):
        """Test that OAuth routes are registered."""
        routes = [route.path for route in app.routes]
        assert "/auth/oauth/providers" in routes
        assert "/auth/oauth/csrf-token" in routes
        assert "/auth/oauth/google/login" in routes
        assert "/auth/oauth/google/callback" in routes
        assert "/auth/oauth/github/login" in routes
        assert "/auth/oauth/github/callback" in routes
        assert "/auth/oauth/accounts" in routes
        assert "/auth/oauth/accounts/{provider}" in routes

    def test_get_providers_returns_status(self, client):
        """Test that providers endpoint returns provider status."""
        response = client.get("/auth/oauth/providers")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "google" in data
        assert "github" in data
        assert isinstance(data["google"], bool)
        assert isinstance(data["github"], bool)

    @patch("ace_platform.api.routes.oauth.is_google_oauth_enabled", return_value=True)
    @patch("ace_platform.api.routes.oauth.is_github_oauth_enabled", return_value=False)
    def test_get_providers_reflects_config(self, mock_github, mock_google, client):
        """Test that providers endpoint reflects actual configuration."""
        response = client.get("/auth/oauth/providers")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["google"] is True
        assert data["github"] is False


class TestOAuthCSRFToken:
    """Tests for OAuth CSRF token endpoint."""

    @pytest.fixture
    def client(self, client_no_rate_limit):
        """Use shared test client with rate limiting disabled."""
        return client_no_rate_limit

    def test_csrf_token_endpoint_returns_token(self, client):
        """Test CSRF token endpoint returns a token."""
        response = client.get("/auth/oauth/csrf-token")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "csrf_token" in data
        assert len(data["csrf_token"]) >= 40  # URL-safe base64 of 32 bytes

    def test_csrf_token_stored_in_session(self, client):
        """Test CSRF token is stored in session and consistent within same session."""
        # First request gets a token
        response1 = client.get("/auth/oauth/csrf-token")
        token1 = response1.json()["csrf_token"]

        # Second request with same session should get same token
        response2 = client.get("/auth/oauth/csrf-token")
        token2 = response2.json()["csrf_token"]

        assert token1 == token2

    @patch("ace_platform.api.routes.oauth.is_google_oauth_enabled", return_value=True)
    @patch("ace_platform.api.routes.oauth.oauth")
    def test_csrf_token_is_single_use_for_login(self, mock_oauth, mock_enabled, client):
        """Test CSRF token is invalidated after OAuth login validation."""
        mock_oauth.google.authorize_redirect = AsyncMock(
            return_value=MagicMock(
                status_code=302,
                headers={"location": "https://accounts.google.com/o/oauth2/auth"},
            )
        )

        # Get a CSRF token
        csrf_response = client.get("/auth/oauth/csrf-token")
        csrf_token = csrf_response.json()["csrf_token"]

        # Use it for OAuth login - this should consume the token
        client.get(f"/auth/oauth/google/login?csrf_token={csrf_token}")
        mock_oauth.google.authorize_redirect.assert_called_once()

        # Now trying to use the same token again should fail with CSRF error
        response = client.get(f"/auth/oauth/google/login?csrf_token={csrf_token}")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "CSRF" in response.json()["error"]["message"]


class TestGoogleOAuthLogin:
    """Tests for Google OAuth login flow."""

    @pytest.fixture
    def client(self, client_no_rate_limit_no_redirect):
        """Use shared test client with rate limiting disabled and no redirects."""
        return client_no_rate_limit_no_redirect

    @patch("ace_platform.api.routes.oauth.is_google_oauth_enabled", return_value=False)
    def test_google_login_disabled(self, mock_enabled, client):
        """Test Google login returns 400 when not configured."""
        response = client.get("/auth/oauth/google/login")
        # OAuth disabled check happens before CSRF validation
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "not configured" in response.json()["error"]["message"]

    @patch("ace_platform.api.routes.oauth.is_google_oauth_enabled", return_value=True)
    def test_google_login_requires_csrf(self, mock_enabled, client):
        """Test Google login requires CSRF token when OAuth is enabled."""
        response = client.get("/auth/oauth/google/login")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "CSRF" in response.json()["error"]["message"]

    @patch("ace_platform.api.routes.oauth.is_google_oauth_enabled", return_value=True)
    @patch("ace_platform.api.routes.oauth.oauth")
    def test_google_login_redirects(self, mock_oauth, mock_enabled, client):
        """Test Google login redirects to Google OAuth with valid CSRF token."""
        # Mock the authorize_redirect to return a redirect response
        mock_oauth.google.authorize_redirect = AsyncMock(
            return_value=MagicMock(
                status_code=302,
                headers={"location": "https://accounts.google.com/o/oauth2/auth"},
            )
        )

        # First get a CSRF token
        csrf_response = client.get("/auth/oauth/csrf-token")
        assert csrf_response.status_code == status.HTTP_200_OK
        csrf_token = csrf_response.json()["csrf_token"]

        # Now call login with CSRF token
        client.get(f"/auth/oauth/google/login?csrf_token={csrf_token}")
        # The actual redirect behavior depends on Authlib, but we verify the call was made
        mock_oauth.google.authorize_redirect.assert_called_once()


class TestGitHubOAuthLogin:
    """Tests for GitHub OAuth login flow."""

    @pytest.fixture
    def client(self, client_no_rate_limit_no_redirect):
        """Use shared test client with rate limiting disabled and no redirects."""
        return client_no_rate_limit_no_redirect

    @patch("ace_platform.api.routes.oauth.is_github_oauth_enabled", return_value=False)
    def test_github_login_disabled(self, mock_enabled, client):
        """Test GitHub login returns 400 when not configured."""
        response = client.get("/auth/oauth/github/login")
        # OAuth disabled check happens before CSRF validation
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "not configured" in response.json()["error"]["message"]

    @patch("ace_platform.api.routes.oauth.is_github_oauth_enabled", return_value=True)
    def test_github_login_requires_csrf(self, mock_enabled, client):
        """Test GitHub login requires CSRF token when OAuth is enabled."""
        response = client.get("/auth/oauth/github/login")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "CSRF" in response.json()["error"]["message"]

    @patch("ace_platform.api.routes.oauth.is_github_oauth_enabled", return_value=True)
    @patch("ace_platform.api.routes.oauth.oauth")
    def test_github_login_redirects(self, mock_oauth, mock_enabled, client):
        """Test GitHub login redirects to GitHub OAuth with valid CSRF token."""
        mock_oauth.github.authorize_redirect = AsyncMock(
            return_value=MagicMock(
                status_code=302,
                headers={"location": "https://github.com/login/oauth/authorize"},
            )
        )

        # First get a CSRF token
        csrf_response = client.get("/auth/oauth/csrf-token")
        assert csrf_response.status_code == status.HTTP_200_OK
        csrf_token = csrf_response.json()["csrf_token"]

        # Now call login with CSRF token
        client.get(f"/auth/oauth/github/login?csrf_token={csrf_token}")
        mock_oauth.github.authorize_redirect.assert_called_once()


class TestOAuthCallback:
    """Tests for OAuth callback handling."""

    @pytest.fixture
    def client(self, client_no_rate_limit_no_redirect):
        """Use shared test client with rate limiting disabled and no redirects."""
        return client_no_rate_limit_no_redirect

    @patch("ace_platform.api.routes.oauth.is_google_oauth_enabled", return_value=False)
    def test_google_callback_disabled(self, mock_enabled, client):
        """Test Google callback returns 400 when not configured."""
        response = client.get("/auth/oauth/google/callback")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    @patch("ace_platform.api.routes.oauth.is_github_oauth_enabled", return_value=False)
    def test_github_callback_disabled(self, mock_enabled, client):
        """Test GitHub callback returns 400 when not configured."""
        response = client.get("/auth/oauth/github/callback")
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestLinkedAccounts:
    """Tests for linked accounts endpoints."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_get_accounts_requires_auth(self, client):
        """Test that getting linked accounts requires authentication."""
        response = client.get("/auth/oauth/accounts")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unlink_account_requires_auth(self, client):
        """Test that unlinking account requires authentication."""
        response = client.delete("/auth/oauth/accounts/google")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.skip(reason="Requires test database - covered by integration tests")
    def test_unlink_invalid_provider_format(self, client):
        """Test that invalid provider returns error (400 or 401)."""
        from ace_platform.core.security import create_access_token

        user_id = uuid4()
        token = create_access_token(user_id)

        response = client.delete(
            "/auth/oauth/accounts/invalid_provider",
            headers={"Authorization": f"Bearer {token}"},
        )
        # Returns 401 because user doesn't exist in DB (token is valid but user not found)
        # In a real scenario with a valid user, it would return 400 for invalid provider
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
        ]


# =============================================================================
# OAuth Service Tests
# =============================================================================


class TestOAuthService:
    """Tests for OAuthService business logic."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock async database session."""
        db = AsyncMock()
        db.add = MagicMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.flush = AsyncMock()
        db.get = AsyncMock()
        db.execute = AsyncMock()
        db.delete = AsyncMock()
        return db

    @pytest.fixture
    def oauth_service(self, mock_db):
        """Create OAuthService instance with mock DB."""
        from ace_platform.core.oauth_service import OAuthService

        return OAuthService(mock_db)

    @pytest.fixture
    def mock_user(self):
        """Create a mock user."""
        now = datetime.now(timezone.utc)
        return User(
            id=uuid4(),
            email="test@example.com",
            hashed_password=hash_password("password123"),
            is_active=True,
            email_verified=True,
            created_at=now,
            updated_at=now,
        )

    @pytest.fixture
    def mock_unverified_user(self):
        """Create a mock user with unverified email."""
        now = datetime.now(timezone.utc)
        return User(
            id=uuid4(),
            email="unverified@example.com",
            hashed_password=hash_password("password123"),
            is_active=True,
            email_verified=False,
            created_at=now,
            updated_at=now,
        )

    @pytest.fixture
    def mock_oauth_account(self, mock_user):
        """Create a mock OAuth account."""
        now = datetime.now(timezone.utc)
        account = UserOAuthAccount(
            id=uuid4(),
            user_id=mock_user.id,
            provider=OAuthProvider.GOOGLE,
            provider_user_id="google-123",
            provider_email="test@example.com",
            created_at=now,
            updated_at=now,
        )
        account.user = mock_user
        return account

    @pytest.mark.asyncio
    async def test_get_or_create_returns_existing_oauth_user(
        self, oauth_service, mock_db, mock_oauth_account
    ):
        """Test that existing OAuth account returns the linked user."""
        # Mock finding existing OAuth account
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_oauth_account
        mock_db.execute.return_value = mock_result

        user, is_new = await oauth_service.get_or_create_user_from_oauth(
            provider=OAuthProvider.GOOGLE,
            provider_user_id="google-123",
            email="test@example.com",
            user_info={"sub": "google-123", "email": "test@example.com"},
        )

        assert user == mock_oauth_account.user
        assert is_new is False

    @pytest.mark.asyncio
    async def test_get_or_create_links_to_verified_email_user(
        self, oauth_service, mock_db, mock_user
    ):
        """Test that OAuth links to existing user with verified email."""
        # Mock: no existing OAuth account
        mock_oauth_result = MagicMock()
        mock_oauth_result.scalar_one_or_none.return_value = None

        # Mock: existing user with verified email
        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = mock_user

        mock_db.execute.side_effect = [mock_oauth_result, mock_user_result]

        user, is_new = await oauth_service.get_or_create_user_from_oauth(
            provider=OAuthProvider.GOOGLE,
            provider_user_id="google-123",
            email="test@example.com",
            user_info={"sub": "google-123", "email": "test@example.com"},
        )

        assert user == mock_user
        assert is_new is False
        # Verify OAuth account was added
        mock_db.add.assert_called()

    @pytest.mark.asyncio
    async def test_get_or_create_does_not_link_to_unverified_email(
        self, oauth_service, mock_db, mock_unverified_user
    ):
        """Test that OAuth does NOT link to user with unverified email (security)."""
        # Mock: no existing OAuth account
        mock_oauth_result = MagicMock()
        mock_oauth_result.scalar_one_or_none.return_value = None

        # Mock: existing user with UNVERIFIED email
        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = mock_unverified_user

        mock_db.execute.side_effect = [mock_oauth_result, mock_user_result]

        user, is_new = await oauth_service.get_or_create_user_from_oauth(
            provider=OAuthProvider.GOOGLE,
            provider_user_id="google-123",
            email="unverified@example.com",
            user_info={"sub": "google-123", "email": "unverified@example.com"},
        )

        # Should create NEW user, not link to unverified one
        assert is_new is True
        assert user.email == "unverified@example.com"
        # The user should NOT be the unverified user
        assert user.id != mock_unverified_user.id

    @pytest.mark.asyncio
    async def test_get_or_create_creates_new_user(self, oauth_service, mock_db):
        """Test that new user is created when no match found."""
        # Mock: no existing OAuth account
        mock_oauth_result = MagicMock()
        mock_oauth_result.scalar_one_or_none.return_value = None

        # Mock: no existing user
        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [mock_oauth_result, mock_user_result]

        user, is_new = await oauth_service.get_or_create_user_from_oauth(
            provider=OAuthProvider.GOOGLE,
            provider_user_id="google-123",
            email="new@example.com",
            user_info={"sub": "google-123", "email": "new@example.com"},
        )

        assert is_new is True
        assert user.email == "new@example.com"
        assert user.email_verified is True  # OAuth emails are verified
        assert user.hashed_password is None  # OAuth users have no password
        mock_db.add.assert_called()

    @pytest.mark.asyncio
    async def test_unlink_prevents_orphaning(self, oauth_service, mock_db, mock_user):
        """Test that unlinking is prevented when it's the only auth method."""
        # User has no password and only one OAuth account
        mock_user.hashed_password = None

        mock_db.get.return_value = mock_user

        # Mock: only one OAuth account
        mock_accounts_result = MagicMock()
        mock_oauth_account = MagicMock()
        mock_oauth_account.provider = OAuthProvider.GOOGLE
        mock_accounts_result.scalars.return_value.all.return_value = [mock_oauth_account]
        mock_db.execute.return_value = mock_accounts_result

        with pytest.raises(ValueError) as exc:
            await oauth_service.unlink_oauth_account(mock_user.id, OAuthProvider.GOOGLE)

        assert "only authentication method" in str(exc.value)

    @pytest.mark.asyncio
    async def test_unlink_allowed_with_password(self, oauth_service, mock_db, mock_user):
        """Test that unlinking is allowed when user has password."""
        # User has password
        mock_user.hashed_password = hash_password("password123")

        mock_db.get.return_value = mock_user

        # Mock: only one OAuth account
        now = datetime.now(timezone.utc)
        mock_oauth_account = UserOAuthAccount(
            id=uuid4(),
            user_id=mock_user.id,
            provider=OAuthProvider.GOOGLE,
            provider_user_id="google-123",
            provider_email="test@example.com",
            created_at=now,
            updated_at=now,
        )

        mock_accounts_result = MagicMock()
        mock_accounts_result.scalars.return_value.all.return_value = [mock_oauth_account]
        mock_db.execute.return_value = mock_accounts_result

        result = await oauth_service.unlink_oauth_account(mock_user.id, OAuthProvider.GOOGLE)

        assert result is True
        mock_db.delete.assert_called_once_with(mock_oauth_account)

    @pytest.mark.asyncio
    async def test_unlink_allowed_with_other_oauth(self, oauth_service, mock_db, mock_user):
        """Test that unlinking is allowed when user has another OAuth."""
        # User has no password but has two OAuth accounts
        mock_user.hashed_password = None

        mock_db.get.return_value = mock_user

        # Mock: two OAuth accounts
        now = datetime.now(timezone.utc)
        google_account = UserOAuthAccount(
            id=uuid4(),
            user_id=mock_user.id,
            provider=OAuthProvider.GOOGLE,
            provider_user_id="google-123",
            provider_email="test@example.com",
            created_at=now,
            updated_at=now,
        )
        github_account = UserOAuthAccount(
            id=uuid4(),
            user_id=mock_user.id,
            provider=OAuthProvider.GITHUB,
            provider_user_id="github-123",
            provider_email="test@example.com",
            created_at=now,
            updated_at=now,
        )

        mock_accounts_result = MagicMock()
        mock_accounts_result.scalars.return_value.all.return_value = [
            google_account,
            github_account,
        ]
        mock_db.execute.return_value = mock_accounts_result

        result = await oauth_service.unlink_oauth_account(mock_user.id, OAuthProvider.GOOGLE)

        assert result is True
        mock_db.delete.assert_called_once_with(google_account)


# =============================================================================
# OAuth Response Schema Tests
# =============================================================================


class TestOAuthSchemas:
    """Tests for OAuth Pydantic schemas."""

    def test_oauth_providers_response(self):
        """Test OAuthProvidersResponse schema."""
        from ace_platform.api.routes.oauth import OAuthProvidersResponse

        response = OAuthProvidersResponse(google=True, github=False)
        assert response.google is True
        assert response.github is False

    def test_linked_accounts_response(self):
        """Test LinkedAccountsResponse schema."""
        from ace_platform.api.routes.oauth import LinkedAccountsResponse

        response = LinkedAccountsResponse(
            google=True,
            github=False,
            has_password=True,
        )
        assert response.google is True
        assert response.github is False
        assert response.has_password is True

    def test_message_response(self):
        """Test MessageResponse schema."""
        from ace_platform.api.routes.oauth import MessageResponse

        response = MessageResponse(message="Account unlinked")
        assert response.message == "Account unlinked"


# =============================================================================
# OAuth Configuration Tests
# =============================================================================


class TestOAuthConfiguration:
    """Tests for OAuth configuration helpers."""

    @pytest.fixture(autouse=True)
    def reset_oauth_settings(self):
        """Reset the cached settings before each test."""
        import ace_platform.core.oauth as oauth_module

        # Clear the cached settings
        oauth_module._settings = None
        yield
        # Clear again after test
        oauth_module._settings = None

    @patch("ace_platform.core.oauth.get_settings")
    def test_google_oauth_enabled(self, mock_settings):
        """Test Google OAuth enabled check."""
        from ace_platform.core.oauth import is_google_oauth_enabled

        mock_settings.return_value.google_oauth_client_id = "client-id"
        mock_settings.return_value.google_oauth_client_secret = "client-secret"

        assert is_google_oauth_enabled() is True

    @patch("ace_platform.core.oauth.get_settings")
    def test_google_oauth_disabled_no_id(self, mock_settings):
        """Test Google OAuth disabled when no client ID."""
        from ace_platform.core.oauth import is_google_oauth_enabled

        mock_settings.return_value.google_oauth_client_id = ""
        mock_settings.return_value.google_oauth_client_secret = "client-secret"

        assert is_google_oauth_enabled() is False

    @patch("ace_platform.core.oauth.get_settings")
    def test_google_oauth_disabled_no_secret(self, mock_settings):
        """Test Google OAuth disabled when no client secret."""
        from ace_platform.core.oauth import is_google_oauth_enabled

        mock_settings.return_value.google_oauth_client_id = "client-id"
        mock_settings.return_value.google_oauth_client_secret = ""

        assert is_google_oauth_enabled() is False

    @patch("ace_platform.core.oauth.get_settings")
    def test_github_oauth_enabled(self, mock_settings):
        """Test GitHub OAuth enabled check."""
        from ace_platform.core.oauth import is_github_oauth_enabled

        mock_settings.return_value.github_oauth_client_id = "client-id"
        mock_settings.return_value.github_oauth_client_secret = "client-secret"

        assert is_github_oauth_enabled() is True

    @patch("ace_platform.core.oauth.get_settings")
    def test_github_oauth_disabled(self, mock_settings):
        """Test GitHub OAuth disabled check."""
        from ace_platform.core.oauth import is_github_oauth_enabled

        mock_settings.return_value.github_oauth_client_id = ""
        mock_settings.return_value.github_oauth_client_secret = ""

        assert is_github_oauth_enabled() is False


# =============================================================================
# OAuth Model Tests
# =============================================================================


class TestOAuthModels:
    """Tests for OAuth database models."""

    def test_oauth_provider_enum(self):
        """Test OAuthProvider enum values."""
        assert OAuthProvider.GOOGLE.value == "google"
        assert OAuthProvider.GITHUB.value == "github"

    def test_user_oauth_account_creation(self):
        """Test UserOAuthAccount model creation."""
        now = datetime.now(timezone.utc)
        user_id = uuid4()

        account = UserOAuthAccount(
            id=uuid4(),
            user_id=user_id,
            provider=OAuthProvider.GOOGLE,
            provider_user_id="google-123",
            provider_email="test@example.com",
            access_token="access-token",
            refresh_token="refresh-token",
            raw_user_info={"sub": "google-123", "email": "test@example.com"},
            created_at=now,
            updated_at=now,
        )

        assert account.provider == OAuthProvider.GOOGLE
        assert account.provider_user_id == "google-123"
        assert account.provider_email == "test@example.com"
        assert account.user_id == user_id

    def test_user_oauth_account_without_tokens(self):
        """Test UserOAuthAccount can be created without tokens."""
        now = datetime.now(timezone.utc)

        account = UserOAuthAccount(
            id=uuid4(),
            user_id=uuid4(),
            provider=OAuthProvider.GITHUB,
            provider_user_id="github-456",
            provider_email="user@example.com",
            created_at=now,
            updated_at=now,
        )

        assert account.access_token is None
        assert account.refresh_token is None
        assert account.token_expires_at is None
