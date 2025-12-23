"""Tests for API key authentication.

These tests verify the API key authentication flow:
1. Create API key, verify full key returned once
2. List keys, verify only prefix shown
3. Use key for MCP auth, verify access granted
4. Revoke key, verify access denied
5. Test scope enforcement
"""

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from ace_platform.core.api_keys import (
    API_KEY_PREFIX,
    ApiKeyInfo,
    CreateApiKeyResult,
    authenticate_api_key_async,
    authenticate_api_key_sync,
    check_scope,
    create_api_key_async,
    create_api_key_sync,
    generate_api_key,
    hash_api_key,
    list_api_keys_async,
    revoke_api_key_async,
    revoke_api_key_sync,
)
from ace_platform.db.models import ApiKey, Base, User

# PostgreSQL test database URL
TEST_DATABASE_URL_ASYNC = os.environ.get(
    "TEST_DATABASE_URL_ASYNC",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/ace_platform_test",
)
TEST_DATABASE_URL_SYNC = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/ace_platform_test",
)


@pytest.fixture(scope="function")
async def async_engine():
    """Create async test database engine with fresh tables."""
    engine = create_async_engine(TEST_DATABASE_URL_ASYNC, echo=False)

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
async def async_session(async_engine):
    """Create async database session."""
    async_session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with async_session_maker() as session:
        yield session


@pytest.fixture(scope="function")
def sync_engine():
    """Create sync test database engine with fresh tables."""
    engine = create_engine(TEST_DATABASE_URL_SYNC, echo=False)

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(bind=engine)

    yield engine

    engine.dispose()


@pytest.fixture
def sync_session(sync_engine):
    """Create sync database session."""
    session_factory = sessionmaker(bind=sync_engine, expire_on_commit=False)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
async def test_user(async_session: AsyncSession):
    """Create a test user."""
    user = User(
        email="test@example.com",
        hashed_password="hashed_password_here",
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
def test_user_sync(sync_session: Session):
    """Create a test user (sync version)."""
    user = User(
        email="test@example.com",
        hashed_password="hashed_password_here",
    )
    sync_session.add(user)
    sync_session.commit()
    sync_session.refresh(user)
    return user


class TestGenerateApiKey:
    """Tests for API key generation."""

    def test_generate_key_format(self):
        """Test that generated keys have correct format."""
        full_key, prefix = generate_api_key()

        assert full_key.startswith(API_KEY_PREFIX)
        assert len(full_key) == len(API_KEY_PREFIX) + 32
        assert prefix == full_key[:8]

    def test_generate_key_unique(self):
        """Test that each generated key is unique."""
        keys = [generate_api_key()[0] for _ in range(100)]
        assert len(set(keys)) == 100

    def test_hash_key_deterministic(self):
        """Test that hashing is deterministic."""
        key = "ace_test123456789"
        hash1 = hash_api_key(key)
        hash2 = hash_api_key(key)
        assert hash1 == hash2

    def test_hash_key_different_for_different_keys(self):
        """Test that different keys produce different hashes."""
        key1, _ = generate_api_key()
        key2, _ = generate_api_key()
        assert hash_api_key(key1) != hash_api_key(key2)


class TestCreateApiKey:
    """Tests for API key creation."""

    async def test_create_key_returns_full_key(self, async_session: AsyncSession, test_user: User):
        """Test that creating a key returns the full key once."""
        result = await create_api_key_async(
            async_session,
            user_id=test_user.id,
            name="Test Key",
            scopes=["read", "write"],
        )
        await async_session.commit()

        assert isinstance(result, CreateApiKeyResult)
        assert result.full_key.startswith(API_KEY_PREFIX)
        assert result.key_prefix == result.full_key[:8]
        assert result.name == "Test Key"
        assert result.scopes == ["read", "write"]
        assert result.key_id is not None

    async def test_create_key_stores_hash_not_plain(
        self, async_session: AsyncSession, test_user: User
    ):
        """Test that the key is stored as a hash, not plaintext."""
        result = await create_api_key_async(
            async_session,
            user_id=test_user.id,
            name="Test Key",
        )
        await async_session.commit()

        # Fetch the key from database
        key = await async_session.get(ApiKey, result.key_id)
        assert key is not None

        # Verify it's a hash, not the plaintext key
        assert key.hashed_key != result.full_key
        assert key.hashed_key == hash_api_key(result.full_key)

    async def test_create_key_for_nonexistent_user_raises(self, async_session: AsyncSession):
        """Test that creating key for nonexistent user raises error."""
        with pytest.raises(ValueError, match="not found"):
            await create_api_key_async(
                async_session,
                user_id=uuid4(),
                name="Test Key",
            )

    def test_create_key_sync(self, sync_session: Session, test_user_sync: User):
        """Test sync version of key creation."""
        result = create_api_key_sync(
            sync_session,
            user_id=test_user_sync.id,
            name="Sync Test Key",
        )
        sync_session.commit()

        assert result.full_key.startswith(API_KEY_PREFIX)
        assert result.name == "Sync Test Key"


class TestListApiKeys:
    """Tests for listing API keys."""

    async def test_list_keys_returns_prefix_only(
        self, async_session: AsyncSession, test_user: User
    ):
        """Test that listing keys only returns prefix, not full key."""
        # Create a key
        create_result = await create_api_key_async(
            async_session,
            user_id=test_user.id,
            name="Test Key",
        )
        await async_session.commit()

        # List keys
        keys = await list_api_keys_async(async_session, test_user.id)

        assert len(keys) == 1
        assert isinstance(keys[0], ApiKeyInfo)
        assert keys[0].key_prefix == create_result.key_prefix
        # Verify full key is NOT in the result
        assert not hasattr(keys[0], "full_key")
        assert keys[0].name == "Test Key"

    async def test_list_keys_excludes_revoked_by_default(
        self, async_session: AsyncSession, test_user: User
    ):
        """Test that revoked keys are excluded by default."""
        # Create two keys
        result1 = await create_api_key_async(async_session, test_user.id, "Key 1")
        await create_api_key_async(async_session, test_user.id, "Key 2")
        await async_session.commit()

        # Revoke one
        await revoke_api_key_async(async_session, result1.key_id, test_user.id)
        await async_session.commit()

        # List should only show one
        keys = await list_api_keys_async(async_session, test_user.id)
        assert len(keys) == 1
        assert keys[0].name == "Key 2"

    async def test_list_keys_includes_revoked_when_requested(
        self, async_session: AsyncSession, test_user: User
    ):
        """Test that revoked keys can be included."""
        result1 = await create_api_key_async(async_session, test_user.id, "Key 1")
        await create_api_key_async(async_session, test_user.id, "Key 2")
        await async_session.commit()

        await revoke_api_key_async(async_session, result1.key_id, test_user.id)
        await async_session.commit()

        keys = await list_api_keys_async(async_session, test_user.id, include_revoked=True)
        assert len(keys) == 2


class TestAuthenticateApiKey:
    """Tests for API key authentication."""

    async def test_authenticate_valid_key(self, async_session: AsyncSession, test_user: User):
        """Test that a valid key grants access."""
        result = await create_api_key_async(async_session, test_user.id, "Test Key")
        await async_session.commit()

        # Authenticate
        auth_result = await authenticate_api_key_async(async_session, result.full_key)

        assert auth_result is not None
        key, user = auth_result
        assert key.id == result.key_id
        assert user.id == test_user.id

    async def test_authenticate_updates_last_used(
        self, async_session: AsyncSession, test_user: User
    ):
        """Test that authentication updates last_used_at."""
        result = await create_api_key_async(async_session, test_user.id, "Test Key")
        await async_session.commit()

        # Check initial state
        key = await async_session.get(ApiKey, result.key_id)
        assert key.last_used_at is None

        # Authenticate
        await authenticate_api_key_async(async_session, result.full_key)
        await async_session.commit()

        # Check last_used_at is set
        await async_session.refresh(key)
        assert key.last_used_at is not None

    async def test_authenticate_invalid_key_denied(self, async_session: AsyncSession):
        """Test that an invalid key is denied."""
        result = await authenticate_api_key_async(
            async_session, "ace_invalidkey12345678901234567890"
        )
        assert result is None

    async def test_authenticate_wrong_prefix_denied(self, async_session: AsyncSession):
        """Test that a key without correct prefix is denied."""
        result = await authenticate_api_key_async(async_session, "wrong_prefix12345678901234567890")
        assert result is None

    async def test_authenticate_empty_key_denied(self, async_session: AsyncSession):
        """Test that an empty key is denied."""
        result = await authenticate_api_key_async(async_session, "")
        assert result is None

        result = await authenticate_api_key_async(async_session, None)
        assert result is None

    def test_authenticate_sync(self, sync_session: Session, test_user_sync: User):
        """Test sync authentication."""
        result = create_api_key_sync(sync_session, test_user_sync.id, "Test Key")
        sync_session.commit()

        auth_result = authenticate_api_key_sync(sync_session, result.full_key)

        assert auth_result is not None
        key, user = auth_result
        assert key.id == result.key_id


class TestRevokeApiKey:
    """Tests for revoking API keys."""

    async def test_revoke_key_denies_access(self, async_session: AsyncSession, test_user: User):
        """Test that a revoked key is denied access."""
        result = await create_api_key_async(async_session, test_user.id, "Test Key")
        await async_session.commit()

        # Key works before revocation
        auth_result = await authenticate_api_key_async(async_session, result.full_key)
        assert auth_result is not None

        # Revoke the key
        revoked = await revoke_api_key_async(async_session, result.key_id, test_user.id)
        await async_session.commit()
        assert revoked is True

        # Key should now be denied
        auth_result = await authenticate_api_key_async(async_session, result.full_key)
        assert auth_result is None

    async def test_revoke_returns_false_for_already_revoked(
        self, async_session: AsyncSession, test_user: User
    ):
        """Test that revoking an already revoked key returns False."""
        result = await create_api_key_async(async_session, test_user.id, "Test Key")
        await async_session.commit()

        # First revocation succeeds
        assert await revoke_api_key_async(async_session, result.key_id, test_user.id)
        await async_session.commit()

        # Second revocation returns False
        assert not await revoke_api_key_async(async_session, result.key_id, test_user.id)

    async def test_revoke_wrong_user_fails(self, async_session: AsyncSession, test_user: User):
        """Test that a user cannot revoke another user's key."""
        result = await create_api_key_async(async_session, test_user.id, "Test Key")
        await async_session.commit()

        # Try to revoke with different user ID
        revoked = await revoke_api_key_async(async_session, result.key_id, uuid4())
        assert revoked is False

    def test_revoke_sync(self, sync_session: Session, test_user_sync: User):
        """Test sync revocation."""
        result = create_api_key_sync(sync_session, test_user_sync.id, "Test Key")
        sync_session.commit()

        revoked = revoke_api_key_sync(sync_session, result.key_id, test_user_sync.id)
        sync_session.commit()
        assert revoked is True

        # Verify access denied
        auth_result = authenticate_api_key_sync(sync_session, result.full_key)
        assert auth_result is None


class TestScopeEnforcement:
    """Tests for scope enforcement."""

    async def test_empty_scopes_allows_all(self, async_session: AsyncSession, test_user: User):
        """Test that empty scopes allows all access."""
        result = await create_api_key_async(async_session, test_user.id, "Test Key", scopes=[])
        await async_session.commit()

        key = await async_session.get(ApiKey, result.key_id)
        assert check_scope(key, "any:scope") is True
        assert check_scope(key, "read") is True
        assert check_scope(key, "write") is True

    async def test_wildcard_scope_allows_all(self, async_session: AsyncSession, test_user: User):
        """Test that '*' scope allows all access."""
        result = await create_api_key_async(async_session, test_user.id, "Test Key", scopes=["*"])
        await async_session.commit()

        key = await async_session.get(ApiKey, result.key_id)
        assert check_scope(key, "any:scope") is True
        assert check_scope(key, "read") is True

    async def test_exact_scope_match(self, async_session: AsyncSession, test_user: User):
        """Test exact scope matching."""
        result = await create_api_key_async(
            async_session,
            test_user.id,
            "Test Key",
            scopes=["playbooks:read", "playbooks:write"],
        )
        await async_session.commit()

        key = await async_session.get(ApiKey, result.key_id)
        assert check_scope(key, "playbooks:read") is True
        assert check_scope(key, "playbooks:write") is True
        assert check_scope(key, "playbooks:delete") is False
        assert check_scope(key, "users:read") is False

    async def test_wildcard_suffix_scope(self, async_session: AsyncSession, test_user: User):
        """Test scope with wildcard suffix (e.g., 'playbooks:*')."""
        result = await create_api_key_async(
            async_session,
            test_user.id,
            "Test Key",
            scopes=["playbooks:*"],
        )
        await async_session.commit()

        key = await async_session.get(ApiKey, result.key_id)
        assert check_scope(key, "playbooks:read") is True
        assert check_scope(key, "playbooks:write") is True
        assert check_scope(key, "playbooks:delete") is True
        assert check_scope(key, "users:read") is False


class TestApiKeyAuthE2E:
    """End-to-end tests for API key authentication flow."""

    async def test_full_auth_workflow(self, async_session: AsyncSession, test_user: User):
        """Test the complete authentication workflow from ace-platform-88."""
        # Step 1: Create API key, verify full key returned once
        create_result = await create_api_key_async(
            async_session,
            test_user.id,
            "MCP Integration Key",
            scopes=["playbooks:read", "evolution:trigger"],
        )
        await async_session.commit()

        assert create_result.full_key.startswith(API_KEY_PREFIX)
        full_key = create_result.full_key  # Save this - won't get it again!

        # Step 2: List keys, verify only prefix shown
        keys = await list_api_keys_async(async_session, test_user.id)
        assert len(keys) == 1
        assert keys[0].key_prefix == create_result.key_prefix
        # Full key should NOT be accessible
        assert not hasattr(keys[0], "full_key")

        # Step 3: Use key for MCP auth, verify access granted
        auth_result = await authenticate_api_key_async(async_session, full_key)
        assert auth_result is not None
        key, user = auth_result
        assert user.id == test_user.id

        # Step 4: Revoke key, verify access denied
        revoked = await revoke_api_key_async(async_session, create_result.key_id, test_user.id)
        await async_session.commit()
        assert revoked is True

        auth_result = await authenticate_api_key_async(async_session, full_key)
        assert auth_result is None

        # Step 5: Test scope enforcement (create new key for this)
        scoped_result = await create_api_key_async(
            async_session,
            test_user.id,
            "Scoped Key",
            scopes=["playbooks:read"],
        )
        await async_session.commit()

        auth_result = await authenticate_api_key_async(async_session, scoped_result.full_key)
        key, _ = auth_result

        assert check_scope(key, "playbooks:read") is True
        assert check_scope(key, "playbooks:write") is False
        assert check_scope(key, "evolution:trigger") is False
