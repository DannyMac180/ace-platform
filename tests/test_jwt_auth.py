"""Tests for JWT authentication and security utilities."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from ace_platform.api.auth import (
    AuthenticationError,
    extract_bearer_token,
    get_optional_user,
    require_user,
    require_verified_user,
)
from ace_platform.core.security import (
    ACCESS_TOKEN_TYPE,
    REFRESH_TOKEN_TYPE,
    InvalidTokenError,
    TokenExpiredError,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    decode_token,
    get_token_user_id,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    """Tests for password hashing functions."""

    def test_hash_password_returns_string(self):
        """Test that hash_password returns a string."""
        hashed = hash_password("password123")
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_hash_password_is_different_from_input(self):
        """Test that hashed password differs from input."""
        password = "password123"
        hashed = hash_password(password)
        assert hashed != password

    def test_hash_password_produces_different_hashes(self):
        """Test that same password produces different hashes (salt)."""
        password = "password123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2  # bcrypt uses random salt

    def test_verify_password_correct(self):
        """Test that verify_password returns True for correct password."""
        password = "password123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test that verify_password returns False for wrong password."""
        password = "password123"
        hashed = hash_password(password)
        assert verify_password("wrongpassword", hashed) is False

    def test_verify_password_empty(self):
        """Test verification with empty password."""
        hashed = hash_password("password123")
        assert verify_password("", hashed) is False


class TestTokenCreation:
    """Tests for JWT token creation."""

    def test_create_access_token_returns_string(self):
        """Test that create_access_token returns a string."""
        user_id = uuid4()
        token = create_access_token(user_id)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_refresh_token_returns_string(self):
        """Test that create_refresh_token returns a string."""
        user_id = uuid4()
        token = create_refresh_token(user_id)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_access_and_refresh_tokens_are_different(self):
        """Test that access and refresh tokens are different."""
        user_id = uuid4()
        access = create_access_token(user_id)
        refresh = create_refresh_token(user_id)
        assert access != refresh

    def test_create_access_token_with_string_id(self):
        """Test creating access token with string user ID."""
        user_id = str(uuid4())
        token = create_access_token(user_id)
        assert isinstance(token, str)

    def test_create_token_with_additional_claims(self):
        """Test creating token with additional claims."""
        user_id = uuid4()
        token = create_access_token(user_id, additional_claims={"role": "admin"})
        payload = decode_token(token)
        assert payload.get("role") == "admin"

    def test_create_token_with_custom_expiration(self):
        """Test creating token with custom expiration."""
        user_id = uuid4()
        token = create_access_token(user_id, expires_delta=timedelta(hours=1))
        payload = decode_token(token)
        assert "exp" in payload


class TestTokenDecoding:
    """Tests for JWT token decoding."""

    def test_decode_access_token_valid(self):
        """Test decoding a valid access token."""
        user_id = uuid4()
        token = create_access_token(user_id)
        payload = decode_access_token(token)
        assert payload["sub"] == str(user_id)
        assert payload["type"] == ACCESS_TOKEN_TYPE

    def test_decode_refresh_token_valid(self):
        """Test decoding a valid refresh token."""
        user_id = uuid4()
        token = create_refresh_token(user_id)
        payload = decode_refresh_token(token)
        assert payload["sub"] == str(user_id)
        assert payload["type"] == REFRESH_TOKEN_TYPE

    def test_decode_access_token_wrong_type(self):
        """Test that decoding refresh token as access token fails."""
        user_id = uuid4()
        token = create_refresh_token(user_id)
        with pytest.raises(InvalidTokenError) as exc:
            decode_access_token(token)
        assert "Expected access token" in str(exc.value)

    def test_decode_refresh_token_wrong_type(self):
        """Test that decoding access token as refresh token fails."""
        user_id = uuid4()
        token = create_access_token(user_id)
        with pytest.raises(InvalidTokenError) as exc:
            decode_refresh_token(token)
        assert "Expected refresh token" in str(exc.value)

    def test_decode_invalid_token(self):
        """Test decoding an invalid token raises error."""
        with pytest.raises(InvalidTokenError):
            decode_token("invalid.token.here")

    def test_decode_expired_token(self):
        """Test that expired token raises TokenExpiredError."""
        user_id = uuid4()
        # Create token that's already expired
        token = create_access_token(user_id, expires_delta=timedelta(seconds=-1))
        with pytest.raises(TokenExpiredError):
            decode_token(token)

    def test_get_token_user_id(self):
        """Test extracting user ID from token."""
        user_id = uuid4()
        token = create_access_token(user_id)
        extracted_id = get_token_user_id(token)
        assert extracted_id == str(user_id)


class TestExtractBearerToken:
    """Tests for bearer token extraction."""

    def test_extract_with_bearer_prefix(self):
        """Test extracting token with Bearer prefix."""
        token = extract_bearer_token("Bearer abc123")
        assert token == "abc123"

    def test_extract_without_bearer_prefix(self):
        """Test that token without Bearer prefix returns None."""
        token = extract_bearer_token("abc123")
        assert token is None

    def test_extract_none_header(self):
        """Test extracting from None header."""
        token = extract_bearer_token(None)
        assert token is None

    def test_extract_empty_after_bearer(self):
        """Test extracting empty token after Bearer."""
        token = extract_bearer_token("Bearer ")
        assert token == ""


class TestAuthDependencies:
    """Tests for authentication dependencies."""

    @pytest.fixture
    def mock_user(self):
        """Create a mock user for testing.

        Note: We explicitly set created_at and updated_at because server_default
        only applies when persisting to the database, not when creating
        model instances directly.
        """
        from ace_platform.db.models import User

        now = datetime.now(timezone.utc)
        user = User(
            id=uuid4(),
            email="test@example.com",
            hashed_password=hash_password("password123"),
            is_active=True,
            email_verified=False,
            created_at=now,
            updated_at=now,
        )
        return user

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_get_optional_user_no_token(self, mock_db):
        """Test get_optional_user with no token returns None."""
        result = await get_optional_user(mock_db, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_optional_user_invalid_token(self, mock_db):
        """Test get_optional_user with invalid token raises error."""
        with pytest.raises(AuthenticationError) as exc:
            await get_optional_user(mock_db, "invalid.token")
        assert "Invalid token" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_get_optional_user_expired_token(self, mock_db):
        """Test get_optional_user with expired token raises error."""
        user_id = uuid4()
        token = create_access_token(user_id, expires_delta=timedelta(seconds=-1))
        with pytest.raises(AuthenticationError) as exc:
            await get_optional_user(mock_db, token)
        assert "expired" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_require_user_with_none(self):
        """Test require_user raises error when no user."""
        with pytest.raises(AuthenticationError) as exc:
            await require_user(None)
        assert "Authentication required" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_require_user_with_user(self, mock_user):
        """Test require_user returns user when provided."""
        result = await require_user(mock_user)
        assert result == mock_user

    @pytest.mark.asyncio
    async def test_require_verified_user_not_verified(self, mock_user):
        """Test require_verified_user raises error for unverified user."""
        mock_user.email_verified = False
        from ace_platform.api.auth import AuthorizationError

        with pytest.raises(AuthorizationError) as exc:
            await require_verified_user(mock_user)
        assert "Email verification required" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_require_verified_user_verified(self, mock_user):
        """Test require_verified_user returns verified user."""
        mock_user.email_verified = True
        result = await require_verified_user(mock_user)
        assert result == mock_user


class TestAuthRoutesIntegration:
    """Integration tests for auth routes."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app with auth routes."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_auth_routes_registered(self, app):
        """Test that auth routes are registered."""
        routes = [route.path for route in app.routes]
        assert "/auth/register" in routes
        assert "/auth/login" in routes
        assert "/auth/refresh" in routes
        assert "/auth/me" in routes

    def test_register_missing_fields(self, client):
        """Test registration with missing fields."""
        response = client.post("/auth/register", json={})
        assert response.status_code == 422

    def test_register_invalid_email(self, client):
        """Test registration with invalid email."""
        response = client.post(
            "/auth/register",
            json={"email": "not-an-email", "password": "password123"},
        )
        assert response.status_code == 422

    def test_register_short_password(self, client):
        """Test registration with too short password."""
        response = client.post(
            "/auth/register",
            json={"email": "test@example.com", "password": "short"},
        )
        assert response.status_code == 422

    def test_login_missing_fields(self, client):
        """Test login with missing fields."""
        response = client.post("/auth/login", json={})
        assert response.status_code == 422

    def test_me_without_auth(self, client):
        """Test /me endpoint without authentication."""
        response = client.get("/auth/me")
        assert response.status_code == 401

    def test_me_with_invalid_token(self, client):
        """Test /me endpoint with invalid token."""
        response = client.get(
            "/auth/me",
            headers={"Authorization": "Bearer invalid.token"},
        )
        assert response.status_code == 401

    def test_refresh_missing_token(self, client):
        """Test refresh without token."""
        response = client.post("/auth/refresh", json={})
        assert response.status_code == 422

    def test_refresh_invalid_token(self, client):
        """Test refresh with invalid token."""
        response = client.post(
            "/auth/refresh",
            json={"refresh_token": "invalid.token"},
        )
        assert response.status_code == 401
