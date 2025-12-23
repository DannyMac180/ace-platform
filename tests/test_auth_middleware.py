"""Tests for authentication middleware and dependencies.

These tests verify:
1. FastAPI auth dependencies (401/403 responses)
2. MCP auth helpers (structured auth results)
3. Scope checking and authorization
4. API key extraction from headers

NOTE: Integration tests require PostgreSQL because the models
use JSONB columns which are PostgreSQL-specific.
"""

import os
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ace_platform.api.auth import (
    AuthContext,
    AuthenticationError,
    AuthorizationError,
    extract_api_key,
    require_any_scope,
    require_auth,
    require_scope,
)
from ace_platform.core.api_keys import create_api_key_async
from ace_platform.db.models import (
    Base,
    Playbook,
    PlaybookSource,
    PlaybookStatus,
    User,
)
from ace_platform.mcp.auth import (
    MCPAuthErrorCode,
    MCPAuthResult,
    authenticate_mcp_request,
    require_playbook_access,
)

# PostgreSQL test database URL
RUN_INTEGRATION_TESTS = os.environ.get("RUN_AUTH_INTEGRATION_TESTS") == "1"
TEST_DATABASE_URL_ASYNC = os.environ.get(
    "TEST_DATABASE_URL_ASYNC",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/ace_platform_test",
)


class TestExtractApiKey:
    """Tests for API key extraction from headers."""

    def test_extract_from_x_api_key_header(self):
        """Test extracting key from X-API-Key header."""
        key = extract_api_key(x_api_key="ace_test123", authorization=None)
        assert key == "ace_test123"

    def test_extract_from_authorization_bearer(self):
        """Test extracting key from Authorization: Bearer header."""
        key = extract_api_key(x_api_key=None, authorization="Bearer ace_test456")
        assert key == "ace_test456"

    def test_x_api_key_takes_precedence(self):
        """Test that X-API-Key header takes precedence over Authorization."""
        key = extract_api_key(
            x_api_key="ace_primary",
            authorization="Bearer ace_secondary",
        )
        assert key == "ace_primary"

    def test_returns_none_when_no_headers(self):
        """Test that None is returned when no auth headers are present."""
        key = extract_api_key(x_api_key=None, authorization=None)
        assert key is None

    def test_returns_none_for_non_bearer_authorization(self):
        """Test that non-Bearer Authorization headers are ignored."""
        key = extract_api_key(x_api_key=None, authorization="Basic dXNlcjpwYXNz")
        assert key is None


class TestAuthenticationError:
    """Tests for AuthenticationError exception."""

    def test_default_message(self):
        """Test default error message."""
        error = AuthenticationError()
        assert error.status_code == 401
        assert "Invalid or missing API key" in error.detail
        assert error.headers == {"WWW-Authenticate": "Bearer"}

    def test_custom_message(self):
        """Test custom error message."""
        error = AuthenticationError(detail="Custom error")
        assert error.detail == "Custom error"


class TestAuthorizationError:
    """Tests for AuthorizationError exception."""

    def test_default_message(self):
        """Test default error message."""
        error = AuthorizationError()
        assert error.status_code == 403
        assert "Insufficient permissions" in error.detail

    def test_custom_message(self):
        """Test custom error message."""
        error = AuthorizationError(detail="Missing scope: admin")
        assert error.detail == "Missing scope: admin"


class TestMCPAuthResult:
    """Tests for MCPAuthResult dataclass."""

    def test_success_result(self):
        """Test successful auth result."""
        user = MagicMock()
        api_key = MagicMock()
        api_key.scopes = ["playbooks:read"]

        result = MCPAuthResult(success=True, user=user, api_key=api_key)

        assert result.success is True
        assert result.error is False
        assert result.http_status == 200
        assert result.user == user
        assert result.api_key == api_key

    def test_error_result(self):
        """Test failed auth result."""
        result = MCPAuthResult(
            success=False,
            error_code=MCPAuthErrorCode.INVALID_KEY,
            error_message="Error: Invalid key",
        )

        assert result.success is False
        assert result.error is True
        assert result.http_status == 401
        assert result.error_code == MCPAuthErrorCode.INVALID_KEY

    def test_insufficient_scope_is_403(self):
        """Test that insufficient scope returns 403."""
        result = MCPAuthResult(
            success=False,
            error_code=MCPAuthErrorCode.INSUFFICIENT_SCOPE,
            error_message="Error: Missing scope",
        )

        assert result.http_status == 403


class TestMCPAuthErrorCodes:
    """Tests for MCP auth error codes."""

    def test_all_error_codes_exist(self):
        """Test that all expected error codes are defined."""
        assert MCPAuthErrorCode.INVALID_KEY
        assert MCPAuthErrorCode.REVOKED_KEY
        assert MCPAuthErrorCode.INACTIVE_USER
        assert MCPAuthErrorCode.INSUFFICIENT_SCOPE
        assert MCPAuthErrorCode.MISSING_KEY

    def test_error_code_values(self):
        """Test error code string values."""
        assert MCPAuthErrorCode.INVALID_KEY.value == "invalid_key"
        assert MCPAuthErrorCode.INSUFFICIENT_SCOPE.value == "insufficient_scope"


# Integration tests require PostgreSQL
pytestmark_integration = pytest.mark.skipif(
    not RUN_INTEGRATION_TESTS,
    reason="Set RUN_AUTH_INTEGRATION_TESTS=1 to run PostgreSQL integration tests.",
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


@pytest.fixture
async def test_user(async_session: AsyncSession):
    """Create a test user."""
    user = User(
        email="auth_test@example.com",
        hashed_password="hashed_password_here",
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def test_api_key(async_session: AsyncSession, test_user: User):
    """Create a test API key with common scopes."""
    result = await create_api_key_async(
        async_session,
        test_user.id,
        "Test Auth Key",
        scopes=["playbooks:read", "outcomes:write"],
    )
    await async_session.commit()
    return result


@pytest.fixture
async def test_playbook(async_session: AsyncSession, test_user: User):
    """Create a test playbook."""
    playbook = Playbook(
        user_id=test_user.id,
        name="Auth Test Playbook",
        status=PlaybookStatus.ACTIVE,
        source=PlaybookSource.USER_CREATED,
    )
    async_session.add(playbook)
    await async_session.commit()
    await async_session.refresh(playbook)
    return playbook


@pytestmark_integration
class TestAuthenticateMcpRequest:
    """Integration tests for authenticate_mcp_request."""

    async def test_valid_key_authenticates(self, async_session: AsyncSession, test_api_key):
        """Test that a valid API key authenticates successfully."""
        result = await authenticate_mcp_request(async_session, test_api_key.full_key)

        assert result.success is True
        assert result.user is not None
        assert result.api_key is not None
        assert result.error is False

    async def test_missing_key_fails(self, async_session: AsyncSession):
        """Test that missing API key returns error."""
        result = await authenticate_mcp_request(async_session, None)

        assert result.success is False
        assert result.error_code == MCPAuthErrorCode.MISSING_KEY
        assert "required" in result.error_message.lower()

    async def test_invalid_key_fails(self, async_session: AsyncSession):
        """Test that invalid API key returns error."""
        result = await authenticate_mcp_request(async_session, "ace_invalid_key")

        assert result.success is False
        assert result.error_code == MCPAuthErrorCode.INVALID_KEY

    async def test_scope_check_passes(self, async_session: AsyncSession, test_api_key):
        """Test that required scope is checked."""
        result = await authenticate_mcp_request(
            async_session, test_api_key.full_key, required_scope="playbooks:read"
        )

        assert result.success is True

    async def test_scope_check_fails(self, async_session: AsyncSession, test_api_key):
        """Test that missing scope returns error."""
        result = await authenticate_mcp_request(
            async_session, test_api_key.full_key, required_scope="admin:write"
        )

        assert result.success is False
        assert result.error_code == MCPAuthErrorCode.INSUFFICIENT_SCOPE
        assert result.http_status == 403


@pytestmark_integration
class TestRequirePlaybookAccess:
    """Integration tests for require_playbook_access."""

    async def test_owner_can_access_playbook(
        self,
        async_session: AsyncSession,
        test_api_key,
        test_playbook: Playbook,
    ):
        """Test that owner can access their playbook."""
        result = await require_playbook_access(
            async_session,
            test_api_key.full_key,
            test_playbook.id,
            "playbooks:read",
        )

        assert result.success is True

    async def test_nonexistent_playbook_fails(self, async_session: AsyncSession, test_api_key):
        """Test that accessing nonexistent playbook fails."""
        result = await require_playbook_access(
            async_session,
            test_api_key.full_key,
            uuid4(),  # Random UUID
            "playbooks:read",
        )

        assert result.success is False
        assert "not found" in result.error_message.lower()

    async def test_invalid_playbook_id_fails(self, async_session: AsyncSession, test_api_key):
        """Test that invalid playbook ID format fails."""
        result = await require_playbook_access(
            async_session,
            test_api_key.full_key,
            "not-a-uuid",
            "playbooks:read",
        )

        assert result.success is False
        assert "invalid" in result.error_message.lower()

    async def test_other_users_playbook_denied(
        self, async_session: AsyncSession, test_playbook: Playbook
    ):
        """Test that accessing another user's playbook is denied."""
        # Create another user and API key
        other_user = User(
            email="other@example.com",
            hashed_password="hashed",
        )
        async_session.add(other_user)
        await async_session.flush()

        other_key = await create_api_key_async(
            async_session,
            other_user.id,
            "Other Key",
            scopes=["playbooks:read"],
        )
        await async_session.commit()

        # Try to access test_playbook (owned by test_user) with other_key
        result = await require_playbook_access(
            async_session,
            other_key.full_key,
            test_playbook.id,
            "playbooks:read",
        )

        assert result.success is False
        assert result.error_code == MCPAuthErrorCode.INSUFFICIENT_SCOPE
        assert "another user" in result.error_message.lower()


@pytestmark_integration
class TestFastAPIAuthDependencies:
    """Integration tests for FastAPI auth dependencies."""

    async def test_require_auth_with_valid_key(
        self, async_session: AsyncSession, test_user: User, test_api_key
    ):
        """Test require_auth dependency with valid key."""
        # Create a mock for get_optional_auth that returns an AuthContext
        auth_context = AuthContext(user=test_user, api_key=MagicMock(scopes=["*"]))

        result = await require_auth(auth_context)

        assert result == auth_context
        assert result.user == test_user

    async def test_require_auth_without_key_raises(self):
        """Test require_auth raises when no key provided."""
        with pytest.raises(AuthenticationError):
            await require_auth(None)

    async def test_require_scope_with_matching_scope(self, test_user: User):
        """Test require_scope passes with matching scope."""
        api_key = MagicMock()
        api_key.scopes = ["playbooks:read", "outcomes:write"]

        auth_context = AuthContext(user=test_user, api_key=api_key)
        scope_checker = require_scope("playbooks:read")

        result = await scope_checker(auth_context)

        assert result == auth_context

    async def test_require_scope_without_scope_raises(self, test_user: User):
        """Test require_scope raises when scope missing."""
        api_key = MagicMock()
        api_key.scopes = ["playbooks:read"]

        auth_context = AuthContext(user=test_user, api_key=api_key)
        scope_checker = require_scope("admin:write")

        with pytest.raises(AuthorizationError) as exc_info:
            await scope_checker(auth_context)

        assert "admin:write" in str(exc_info.value.detail)

    async def test_require_any_scope_passes_with_one(self, test_user: User):
        """Test require_any_scope passes when one scope matches."""
        api_key = MagicMock()
        api_key.scopes = ["outcomes:write"]

        auth_context = AuthContext(user=test_user, api_key=api_key)
        scope_checker = require_any_scope("playbooks:read", "outcomes:write")

        result = await scope_checker(auth_context)

        assert result == auth_context

    async def test_require_any_scope_fails_with_none(self, test_user: User):
        """Test require_any_scope fails when no scopes match."""
        api_key = MagicMock()
        api_key.scopes = ["other:scope"]

        auth_context = AuthContext(user=test_user, api_key=api_key)
        scope_checker = require_any_scope("playbooks:read", "outcomes:write")

        with pytest.raises(AuthorizationError):
            await scope_checker(auth_context)


@pytestmark_integration
class TestAuthE2E:
    """End-to-end tests for authentication flow."""

    async def test_full_mcp_auth_flow(
        self,
        async_session: AsyncSession,
        test_api_key,
        test_playbook: Playbook,
    ):
        """Test complete MCP authentication flow."""
        # Step 1: Authenticate with valid key
        auth = await authenticate_mcp_request(
            async_session, test_api_key.full_key, "playbooks:read"
        )
        assert auth.success is True

        # Step 2: Check scope
        assert auth.has_scope("playbooks:read") is True
        assert auth.has_scope("admin:write") is False

        # Step 3: Access playbook
        access = await require_playbook_access(
            async_session,
            test_api_key.full_key,
            test_playbook.id,
            "playbooks:read",
        )
        assert access.success is True
        assert access.user.id == test_playbook.user_id
