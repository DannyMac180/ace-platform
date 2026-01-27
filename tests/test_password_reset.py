"""Tests for password reset functionality."""

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ace_platform.core.email import (
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS,
    generate_password_reset_token,
    hash_password_reset_token,
    verify_password_reset_token,
)
from ace_platform.core.security import hash_password
from ace_platform.db.models import Base, PasswordResetToken, User

# PostgreSQL test database URL
RUN_INTEGRATION_TESTS = os.environ.get("RUN_PASSWORD_RESET_INTEGRATION_TESTS") == "1"
TEST_DATABASE_URL_ASYNC = os.environ.get(
    "TEST_DATABASE_URL_ASYNC",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/ace_platform_test",
)


class TestPasswordResetTokenFunctions:
    """Tests for password reset token utility functions."""

    def test_generate_password_reset_token_returns_string(self):
        """Test that generate_password_reset_token returns a non-empty string."""
        token = generate_password_reset_token()
        assert isinstance(token, str)
        assert len(token) > 20  # URL-safe base64 of 32 bytes

    def test_generate_password_reset_token_unique(self):
        """Test that each generated token is unique."""
        tokens = [generate_password_reset_token() for _ in range(100)]
        assert len(set(tokens)) == 100

    def test_hash_password_reset_token_deterministic(self):
        """Test that hashing the same token produces the same hash."""
        token = "test-token-12345"
        hash1 = hash_password_reset_token(token)
        hash2 = hash_password_reset_token(token)
        assert hash1 == hash2

    def test_hash_password_reset_token_different_for_different_tokens(self):
        """Test that different tokens produce different hashes."""
        token1 = "test-token-1"
        token2 = "test-token-2"
        hash1 = hash_password_reset_token(token1)
        hash2 = hash_password_reset_token(token2)
        assert hash1 != hash2

    def test_verify_password_reset_token_correct(self):
        """Test that verify returns True for correct token."""
        token = generate_password_reset_token()
        token_hash = hash_password_reset_token(token)
        assert verify_password_reset_token(token, token_hash) is True

    def test_verify_password_reset_token_incorrect(self):
        """Test that verify returns False for incorrect token."""
        token = generate_password_reset_token()
        token_hash = hash_password_reset_token(token)
        assert verify_password_reset_token("wrong-token", token_hash) is False


class TestPasswordResetTokenModel:
    """Tests for PasswordResetToken model."""

    def test_is_valid_returns_true_for_unused_unexpired_token(self):
        """Test is_valid returns True when token is unused and not expired."""
        token = PasswordResetToken(
            id=uuid4(),
            user_id=uuid4(),
            token_hash=hash_password_reset_token("test-token"),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            used_at=None,
        )
        assert token.is_valid is True

    def test_is_valid_returns_false_for_used_token(self):
        """Test is_valid returns False when token has been used."""
        token = PasswordResetToken(
            id=uuid4(),
            user_id=uuid4(),
            token_hash=hash_password_reset_token("test-token"),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            used_at=datetime.now(UTC),
        )
        assert token.is_valid is False

    def test_is_valid_returns_false_for_expired_token(self):
        """Test is_valid returns False when token is expired."""
        token = PasswordResetToken(
            id=uuid4(),
            user_id=uuid4(),
            token_hash=hash_password_reset_token("test-token"),
            expires_at=datetime.now(UTC) - timedelta(hours=1),
            used_at=None,
        )
        assert token.is_valid is False


class TestPasswordResetEndpointsUnit:
    """Unit tests for password reset endpoints (no database)."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_forgot_password_route_exists(self, app):
        """Test that forgot-password route is registered."""
        routes = [route.path for route in app.routes]
        assert "/auth/forgot-password" in routes

    def test_reset_password_route_exists(self, app):
        """Test that reset-password route is registered."""
        routes = [route.path for route in app.routes]
        assert "/auth/reset-password" in routes

    def test_forgot_password_requires_email(self, client):
        """Test that forgot-password requires email field."""
        response = client.post("/auth/forgot-password", json={})
        assert response.status_code == 422

    def test_forgot_password_validates_email_format(self, client):
        """Test that forgot-password validates email format."""
        response = client.post("/auth/forgot-password", json={"email": "not-an-email"})
        assert response.status_code == 422

    def test_reset_password_requires_token(self, client):
        """Test that reset-password requires token field."""
        response = client.post(
            "/auth/reset-password",
            json={"new_password": "newpassword123"},
        )
        assert response.status_code == 422

    def test_reset_password_requires_new_password(self, client):
        """Test that reset-password requires new_password field."""
        response = client.post(
            "/auth/reset-password",
            json={"token": "some-token"},
        )
        assert response.status_code == 422

    def test_reset_password_validates_password_length(self, client):
        """Test that reset-password validates password minimum length."""
        response = client.post(
            "/auth/reset-password",
            json={"token": "some-token", "new_password": "short"},
        )
        assert response.status_code == 422


class TestPasswordResetRateLimit:
    """Tests for password reset rate limiting."""

    def test_rate_limit_config_exists(self):
        """Test that password reset rate limit configuration exists."""
        from ace_platform.core.rate_limit import RATE_LIMITS

        assert "password_reset" in RATE_LIMITS
        assert RATE_LIMITS["password_reset"]["limit"] == 3
        assert RATE_LIMITS["password_reset"]["window_seconds"] == 3600


@pytest.mark.skipif(
    not RUN_INTEGRATION_TESTS,
    reason="Set RUN_PASSWORD_RESET_INTEGRATION_TESTS=1 to run integration tests",
)
class TestPasswordResetIntegration:
    """Integration tests for password reset (requires PostgreSQL)."""

    @pytest.fixture(scope="function")
    async def async_engine(self):
        """Create async test database engine with fresh tables."""
        engine = create_async_engine(TEST_DATABASE_URL_ASYNC, echo=False)

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        yield engine

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

        await engine.dispose()

    @pytest.fixture(scope="function")
    async def async_session(self, async_engine):
        """Create async test session."""
        async_session_maker = async_sessionmaker(
            async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async with async_session_maker() as session:
            yield session

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    @pytest.fixture
    async def test_user(self, async_session: AsyncSession):
        """Create a test user."""
        user = User(
            email="test@example.com",
            hashed_password=hash_password("oldpassword123"),
            is_active=True,
            email_verified=True,
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        return user

    @pytest.fixture
    async def user_with_reset_token(self, async_session: AsyncSession, test_user):
        """Create a user with a valid reset token."""
        token = generate_password_reset_token()
        token_hash = hash_password_reset_token(token)

        reset_token = PasswordResetToken(
            user_id=test_user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(hours=PASSWORD_RESET_TOKEN_EXPIRE_HOURS),
        )
        async_session.add(reset_token)
        await async_session.commit()

        return test_user, token

    @pytest.mark.asyncio
    async def test_reset_password_success(
        self,
        client,
        async_session: AsyncSession,
        user_with_reset_token,
    ):
        """Test successful password reset."""
        user, token = user_with_reset_token

        # Mock the database session used by the endpoint
        with patch("ace_platform.api.deps.get_db") as mock_get_db:
            mock_get_db.return_value = async_session

            response = client.post(
                "/auth/reset-password",
                json={
                    "token": token,
                    "new_password": "newpassword456",
                },
            )

        assert response.status_code == 200
        assert "successfully" in response.json()["message"]

    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self, client):
        """Test reset password with invalid token."""
        response = client.post(
            "/auth/reset-password",
            json={
                "token": "invalid-token",
                "new_password": "newpassword456",
            },
        )

        assert response.status_code == 400
        assert "Invalid or expired" in response.json()["detail"]
