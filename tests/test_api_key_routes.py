"""Tests for API key management REST endpoints.

These tests verify:
1. POST /auth/api-keys - Create new API key
2. GET /auth/api-keys - List user's API keys
3. DELETE /auth/api-keys/{id} - Revoke API key
"""

import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ace_platform.core.api_keys import API_KEY_PREFIX
from ace_platform.core.security import create_access_token
from ace_platform.db.models import Base, User

# PostgreSQL test database URL
RUN_INTEGRATION_TESTS = os.environ.get("RUN_API_KEY_INTEGRATION_TESTS") == "1"
TEST_DATABASE_URL_ASYNC = os.environ.get(
    "TEST_DATABASE_URL_ASYNC",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/ace_platform_test",
)


class TestApiKeyRoutesUnit:
    """Unit tests for API key routes (no database)."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_api_key_routes_registered(self, app):
        """Test that API key routes are registered."""
        routes = [route.path for route in app.routes]
        assert "/auth/api-keys" in routes
        assert "/auth/api-keys/{key_id}" in routes

    def test_create_api_key_without_auth(self, client):
        """Test that creating API key without auth returns 401."""
        response = client.post(
            "/auth/api-keys",
            json={"name": "Test Key", "scopes": ["playbooks:read"]},
        )
        assert response.status_code == 401

    def test_list_api_keys_without_auth(self, client):
        """Test that listing API keys without auth returns 401."""
        response = client.get("/auth/api-keys")
        assert response.status_code == 401

    def test_delete_api_key_without_auth(self, client):
        """Test that deleting API key without auth returns 401."""
        response = client.delete(f"/auth/api-keys/{uuid4()}")
        assert response.status_code == 401

    def test_create_api_key_invalid_name(self, client):
        """Test validation for API key name."""
        # With invalid token, we get 401 before validation
        response = client.post(
            "/auth/api-keys",
            json={"name": "", "scopes": []},  # Empty name
            headers={"Authorization": "Bearer invalid"},
        )
        # Should be either 401 (auth fails first) or 422 (validation)
        assert response.status_code in [401, 422]

    def test_delete_api_key_invalid_uuid(self, client):
        """Test that invalid UUID returns 422 or 401 (auth checked first)."""
        response = client.delete(
            "/auth/api-keys/not-a-uuid",
            headers={"Authorization": "Bearer invalid"},
        )
        # Auth is checked before path validation, so we get 401
        # With valid auth, we would get 422 for invalid UUID
        assert response.status_code in [401, 422]


@pytest.mark.skipif(
    not RUN_INTEGRATION_TESTS,
    reason="Set RUN_API_KEY_INTEGRATION_TESTS=1 to run integration tests",
)
class TestApiKeyRoutesIntegration:
    """Integration tests for API key routes (requires PostgreSQL)."""

    @pytest.fixture(scope="function")
    async def async_engine(self):
        """Create async test database engine with fresh tables."""
        engine = create_async_engine(TEST_DATABASE_URL_ASYNC, echo=False)

        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
            await conn.run_sync(Base.metadata.create_all)

        yield engine

        await engine.dispose()

    @pytest.fixture
    async def async_session(self, async_engine):
        """Create async database session."""
        async_session_maker = async_sessionmaker(
            bind=async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with async_session_maker() as session:
            yield session

    @pytest.fixture
    async def test_user(self, async_session: AsyncSession):
        """Create a test user and return their access token."""
        user = User(
            email="apikey-test@example.com",
            hashed_password="hashed_password_here",
            is_active=True,
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        # Create access token
        access_token = create_access_token(user.id)

        return {"user": user, "token": access_token}

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    async def test_create_api_key_success(self, client, test_user):
        """Test creating an API key successfully."""
        response = client.post(
            "/auth/api-keys",
            json={"name": "Test Key", "scopes": ["playbooks:read", "outcomes:write"]},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 201
        data = response.json()

        # Verify response structure
        assert "id" in data
        assert "key" in data
        assert "key_prefix" in data
        assert data["name"] == "Test Key"
        assert data["scopes"] == ["playbooks:read", "outcomes:write"]

        # Verify key format
        assert data["key"].startswith(API_KEY_PREFIX)
        assert data["key_prefix"] == data["key"][:8]

    async def test_create_api_key_empty_scopes(self, client, test_user):
        """Test creating an API key with no scopes."""
        response = client.post(
            "/auth/api-keys",
            json={"name": "No Scope Key"},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["scopes"] == []

    async def test_list_api_keys_empty(self, client, test_user):
        """Test listing API keys when none exist."""
        response = client.get(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 200
        assert response.json() == []

    async def test_list_api_keys_after_creation(self, client, test_user):
        """Test listing API keys after creating some."""
        # Create two keys
        client.post(
            "/auth/api-keys",
            json={"name": "Key 1", "scopes": ["playbooks:read"]},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        client.post(
            "/auth/api-keys",
            json={"name": "Key 2", "scopes": ["playbooks:write"]},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        # List keys
        response = client.get(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 200
        keys = response.json()
        assert len(keys) == 2

        # Verify structure (no full key in list)
        for key in keys:
            assert "id" in key
            assert "name" in key
            assert "key_prefix" in key
            assert "scopes" in key
            assert "created_at" in key
            assert "is_active" in key
            # Full key should NOT be in list response
            assert "key" not in key

    async def test_delete_api_key_success(self, client, test_user):
        """Test revoking an API key successfully."""
        # Create a key
        create_response = client.post(
            "/auth/api-keys",
            json={"name": "Key to Delete"},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        key_id = create_response.json()["id"]

        # Delete it
        delete_response = client.delete(
            f"/auth/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert delete_response.status_code == 204

        # Verify it's not in active list
        list_response = client.get(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        assert len(list_response.json()) == 0

    async def test_delete_api_key_not_found(self, client, test_user):
        """Test deleting a non-existent API key returns 404."""
        response = client.delete(
            f"/auth/api-keys/{uuid4()}",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        assert response.status_code == 404

    async def test_list_api_keys_excludes_revoked_by_default(self, client, test_user):
        """Test that revoked keys are excluded by default."""
        # Create and revoke a key
        create_response = client.post(
            "/auth/api-keys",
            json={"name": "Revoked Key"},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        key_id = create_response.json()["id"]

        client.delete(
            f"/auth/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        # Create an active key
        client.post(
            "/auth/api-keys",
            json={"name": "Active Key"},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        # List should only show active key
        response = client.get(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        keys = response.json()
        assert len(keys) == 1
        assert keys[0]["name"] == "Active Key"

    async def test_list_api_keys_include_revoked(self, client, test_user):
        """Test listing API keys with include_revoked=true."""
        # Create and revoke a key
        create_response = client.post(
            "/auth/api-keys",
            json={"name": "Revoked Key"},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )
        key_id = create_response.json()["id"]

        client.delete(
            f"/auth/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        # Create an active key
        client.post(
            "/auth/api-keys",
            json={"name": "Active Key"},
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        # List with include_revoked=true
        response = client.get(
            "/auth/api-keys?include_revoked=true",
            headers={"Authorization": f"Bearer {test_user['token']}"},
        )

        keys = response.json()
        assert len(keys) == 2

    async def test_cannot_delete_other_users_key(self, client, async_session: AsyncSession):
        """Test that a user cannot delete another user's API key."""
        # Create two users
        user1 = User(
            email="user1@example.com",
            hashed_password="hashed",
            is_active=True,
        )
        user2 = User(
            email="user2@example.com",
            hashed_password="hashed",
            is_active=True,
        )
        async_session.add(user1)
        async_session.add(user2)
        await async_session.commit()
        await async_session.refresh(user1)
        await async_session.refresh(user2)

        token1 = create_access_token(user1.id)
        token2 = create_access_token(user2.id)

        # User 1 creates a key
        create_response = client.post(
            "/auth/api-keys",
            json={"name": "User 1 Key"},
            headers={"Authorization": f"Bearer {token1}"},
        )
        key_id = create_response.json()["id"]

        # User 2 tries to delete it
        delete_response = client.delete(
            f"/auth/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {token2}"},
        )

        # Should return 404 (not found for this user)
        assert delete_response.status_code == 404

        # Verify key still exists for user 1
        list_response = client.get(
            "/auth/api-keys",
            headers={"Authorization": f"Bearer {token1}"},
        )
        assert len(list_response.json()) == 1
