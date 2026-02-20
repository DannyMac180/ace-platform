"""Tests for MCP server and tools.

These tests verify:
1. MCP tool scope definitions
2. Scope validation
3. MCP tools functionality with database integration

NOTE: Database integration tests require PostgreSQL because the models
use JSONB columns which are PostgreSQL-specific.
"""

import os
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ace_platform.core.api_keys import create_api_key_async
from ace_platform.db.models import (
    Base,
    EvolutionJob,
    EvolutionJobStatus,
    Playbook,
    PlaybookSource,
    PlaybookStatus,
    PlaybookVersion,
    SubscriptionStatus,
    User,
)
from ace_platform.mcp.tools import (
    DEFAULT_SCOPES,
    SCOPE_DESCRIPTIONS,
    MCPScope,
    validate_scopes,
)


class _MockScalarResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _MockExecuteResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _MockScalarResult(self._items)


class _MockDB:
    def __init__(self, items):
        self._items = items
        self.commit_called = False

    async def execute(self, _query):
        return _MockExecuteResult(self._items)

    async def commit(self):
        self.commit_called = True


# PostgreSQL test database URL - requires running PostgreSQL
RUN_INTEGRATION_TESTS = os.environ.get("RUN_MCP_INTEGRATION_TESTS") == "1"
TEST_DATABASE_URL_ASYNC = os.environ.get(
    "TEST_DATABASE_URL_ASYNC",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/ace_platform_test",
)


class TestMCPScopes:
    """Tests for MCP scope definitions."""

    def test_scope_enum_values(self):
        """Test that scope enum has expected values."""
        assert MCPScope.PLAYBOOKS_READ.value == "playbooks:read"
        assert MCPScope.PLAYBOOKS_WRITE.value == "playbooks:write"
        assert MCPScope.OUTCOMES_READ.value == "outcomes:read"
        assert MCPScope.OUTCOMES_WRITE.value == "outcomes:write"
        assert MCPScope.EVOLUTION_READ.value == "evolution:read"
        assert MCPScope.EVOLUTION_WRITE.value == "evolution:write"
        assert MCPScope.ALL.value == "*"

    def test_all_scopes_have_descriptions(self):
        """Test that all scopes have descriptions."""
        for scope in MCPScope:
            assert scope in SCOPE_DESCRIPTIONS
            assert SCOPE_DESCRIPTIONS[scope]

    def test_default_scopes(self):
        """Test default scopes include read and outcomes:write."""
        assert MCPScope.PLAYBOOKS_READ.value in DEFAULT_SCOPES
        assert MCPScope.OUTCOMES_WRITE.value in DEFAULT_SCOPES


class TestValidateScopes:
    """Tests for scope validation."""

    def test_validate_exact_scopes(self):
        """Test validating exact scope matches."""
        scopes = ["playbooks:read", "outcomes:write"]
        result = validate_scopes(scopes)
        assert result == ["playbooks:read", "outcomes:write"]

    def test_validate_wildcard_all(self):
        """Test validating wildcard all scope."""
        result = validate_scopes(["*"])
        assert result == ["*"]

    def test_validate_wildcard_prefix(self):
        """Test validating wildcard prefix scope."""
        result = validate_scopes(["playbooks:*"])
        assert result == ["playbooks:*"]

    def test_validate_normalizes_case(self):
        """Test that validation normalizes case."""
        result = validate_scopes(["PLAYBOOKS:READ", "Outcomes:Write"])
        assert result == ["playbooks:read", "outcomes:write"]

    def test_validate_strips_whitespace(self):
        """Test that validation strips whitespace."""
        result = validate_scopes(["  playbooks:read  ", "outcomes:write "])
        assert result == ["playbooks:read", "outcomes:write"]

    def test_validate_invalid_scope_raises(self):
        """Test that invalid scope raises ValueError."""
        with pytest.raises(ValueError, match="Invalid scope"):
            validate_scopes(["invalid:scope"])

    def test_validate_invalid_wildcard_prefix_raises(self):
        """Test that invalid wildcard prefix raises ValueError."""
        with pytest.raises(ValueError, match="Invalid scope prefix"):
            validate_scopes(["invalid:*"])

    def test_validate_empty_list(self):
        """Test validating empty scope list."""
        result = validate_scopes([])
        assert result == []


class TestFlyReplayMiddleware:
    """Tests for Fly.io session affinity middleware."""

    @pytest.fixture
    def dummy_app(self):
        """ASGI app that records calls and returns configurable responses."""

        class DummyApp:
            def __init__(self):
                self.called = False
                self.status_code = 200
                self.body = b"OK"
                self.scope = None

            async def __call__(self, scope, receive, send):
                self.called = True
                self.scope = scope
                await send(
                    {
                        "type": "http.response.start",
                        "status": self.status_code,
                        "headers": [],
                    }
                )
                await send({"type": "http.response.body", "body": self.body})

        return DummyApp()

    @staticmethod
    async def _collect_response(app, scope, receive=None):
        """Call an ASGI app and collect the response parts."""
        parts = []

        async def send(message):
            parts.append(message)

        async def default_receive():
            return {"type": "http.request", "body": b""}

        await app(scope, receive or default_receive, send)
        return parts

    def test_noop_without_fly_machine_id(self, dummy_app):
        """Middleware passes through when FLY_MACHINE_ID is not set."""
        import asyncio

        from ace_platform.mcp.server import FlyReplayMiddleware

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FLY_MACHINE_ID", None)
            mw = FlyReplayMiddleware(dummy_app)

        scope = {"type": "http", "path": "/mcp/messages/", "query_string": b"session_id=abc"}
        asyncio.get_event_loop().run_until_complete(self._collect_response(mw, scope))
        assert dummy_app.called

    def test_noop_for_non_http(self, dummy_app):
        """Middleware passes through for non-HTTP scopes."""
        import asyncio

        from ace_platform.mcp.server import FlyReplayMiddleware

        with patch.dict(os.environ, {"FLY_MACHINE_ID": "machine-a"}):
            mw = FlyReplayMiddleware(dummy_app)

        scope = {"type": "lifespan"}
        asyncio.get_event_loop().run_until_complete(self._collect_response(mw, scope))
        assert dummy_app.called

    def test_messages_passthrough_same_instance(self, dummy_app):
        """POST to /messages/ with matching fly_instance passes through."""
        import asyncio

        from ace_platform.mcp.server import FlyReplayMiddleware

        with patch.dict(os.environ, {"FLY_MACHINE_ID": "machine-a"}):
            mw = FlyReplayMiddleware(dummy_app)

        scope = {
            "type": "http",
            "path": "/mcp/messages/",
            "query_string": b"session_id=abc&fly_instance=machine-a",
        }
        asyncio.get_event_loop().run_until_complete(self._collect_response(mw, scope))
        assert dummy_app.called

    def test_messages_replay_different_instance(self, dummy_app):
        """POST to /messages/ with different fly_instance returns fly-replay header."""
        import asyncio

        from ace_platform.mcp.server import FlyReplayMiddleware

        with patch.dict(os.environ, {"FLY_MACHINE_ID": "machine-a"}):
            mw = FlyReplayMiddleware(dummy_app)

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/mcp/messages/",
            "query_string": b"session_id=abc&fly_instance=machine-b",
            "headers": [],
        }
        parts = asyncio.get_event_loop().run_until_complete(self._collect_response(mw, scope))
        assert not dummy_app.called
        # Check for fly-replay header
        start = parts[0]
        assert start["status"] == 404
        headers = dict(start.get("headers", []))
        assert headers.get(b"fly-replay") == b"instance=machine-b"

    def test_messages_passthrough_no_fly_instance(self, dummy_app):
        """POST to /messages/ without fly_instance param passes through normally."""
        import asyncio

        from ace_platform.mcp.server import FlyReplayMiddleware

        with patch.dict(os.environ, {"FLY_MACHINE_ID": "machine-a"}):
            mw = FlyReplayMiddleware(dummy_app)

        scope = {
            "type": "http",
            "path": "/mcp/messages/",
            "query_string": b"session_id=abc",
        }
        asyncio.get_event_loop().run_until_complete(self._collect_response(mw, scope))
        assert dummy_app.called

    def test_sse_injects_fly_instance_on_endpoint_data_line(self, dummy_app):
        """SSE endpoint response has fly_instance appended to endpoint data URL."""
        import asyncio

        from ace_platform.mcp.server import FlyReplayMiddleware

        # Make the dummy app return an SSE-like body
        dummy_app.body = b"event: endpoint\r\ndata: /mcp/messages/?session_id=abc123\r\n\r\n"

        with patch.dict(os.environ, {"FLY_MACHINE_ID": "machine-a"}):
            mw = FlyReplayMiddleware(dummy_app)

        scope = {"type": "http", "path": "/mcp/sse", "query_string": b""}
        parts = asyncio.get_event_loop().run_until_complete(self._collect_response(mw, scope))
        body_part = next(p for p in parts if p.get("type") == "http.response.body")
        body_text = body_part["body"].decode("utf-8")
        assert "event: endpoint\r\n" in body_text
        assert "event: endpoint&fly_instance=machine-a" not in body_text
        assert "data: /mcp/messages/?session_id=abc123&fly_instance=machine-a\r\n" in body_text


# Integration tests require PostgreSQL
pytestmark_integration = pytest.mark.skipif(
    not RUN_INTEGRATION_TESTS,
    reason="Set RUN_MCP_INTEGRATION_TESTS=1 to run PostgreSQL integration tests.",
)


@pytest.fixture(scope="function")
async def async_engine():
    """Create async test database engine with fresh tables."""
    engine = create_async_engine(TEST_DATABASE_URL_ASYNC, echo=False)

    # Drop and recreate using raw SQL to handle circular FKs
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
        email="mcp_test@example.com",
        hashed_password="hashed_password_here",
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def test_playbook(async_session: AsyncSession, test_user: User):
    """Create a test playbook with a version."""
    playbook = Playbook(
        user_id=test_user.id,
        name="Test Playbook",
        description="A test playbook for MCP",
        status=PlaybookStatus.ACTIVE,
        source=PlaybookSource.USER_CREATED,
    )
    async_session.add(playbook)
    await async_session.flush()

    # Add a version
    version = PlaybookVersion(
        playbook_id=playbook.id,
        version_number=1,
        content="# Test Playbook\n\n- Step 1: Do something\n- Step 2: Do more",
        bullet_count=2,
    )
    async_session.add(version)
    await async_session.flush()

    # Set as current version
    playbook.current_version_id = version.id
    await async_session.commit()
    await async_session.refresh(playbook)

    return playbook


@pytest.fixture
async def test_playbook_with_versions(async_session: AsyncSession, test_user: User):
    """Create a test playbook with multiple versions."""
    playbook = Playbook(
        user_id=test_user.id,
        name="Multi-Version Playbook",
        description="A playbook with version history",
        status=PlaybookStatus.ACTIVE,
        source=PlaybookSource.USER_CREATED,
    )
    async_session.add(playbook)
    await async_session.flush()

    # Add version 1
    version1 = PlaybookVersion(
        playbook_id=playbook.id,
        version_number=1,
        content="""# Multi-Version Playbook

## Getting Started

- Step 1: Initial setup
- Step 2: Configure settings

## Advanced Topics

- Advanced topic 1
- Advanced topic 2
""",
        bullet_count=4,
    )
    async_session.add(version1)
    await async_session.flush()

    # Add version 2
    version2 = PlaybookVersion(
        playbook_id=playbook.id,
        version_number=2,
        content="""# Multi-Version Playbook

## Getting Started

- Step 1: Initial setup (updated)
- Step 2: Configure settings
- Step 3: New step added in v2

## Advanced Topics

- Advanced topic 1
- Advanced topic 2
- Advanced topic 3 (new)
""",
        bullet_count=6,
    )
    async_session.add(version2)
    await async_session.flush()

    # Set version 2 as current
    playbook.current_version_id = version2.id
    await async_session.commit()
    await async_session.refresh(playbook)

    return playbook


@pytest.fixture
async def test_api_key(async_session: AsyncSession, test_user: User):
    """Create a test API key with default scopes."""
    result = await create_api_key_async(
        async_session,
        test_user.id,
        "Test MCP Key",
        scopes=["playbooks:read", "outcomes:write", "evolution:write", "evolution:read"],
    )
    await async_session.commit()
    return result


@pytest.fixture
async def test_evolution_job(async_session: AsyncSession, test_playbook: Playbook):
    """Create a test evolution job."""
    from datetime import UTC, datetime

    job = EvolutionJob(
        playbook_id=test_playbook.id,
        status=EvolutionJobStatus.COMPLETED,
        outcomes_processed=5,
        started_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        completed_at=datetime(2024, 1, 1, 12, 5, 0, tzinfo=UTC),
    )
    async_session.add(job)
    await async_session.commit()
    await async_session.refresh(job)
    return job


@pytest.fixture
async def test_evolution_job_failed(async_session: AsyncSession, test_playbook: Playbook):
    """Create a failed evolution job."""
    from datetime import UTC, datetime

    job = EvolutionJob(
        playbook_id=test_playbook.id,
        status=EvolutionJobStatus.FAILED,
        outcomes_processed=3,
        started_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        completed_at=datetime(2024, 1, 1, 12, 2, 0, tzinfo=UTC),
        error_message="Evolution failed: Model rate limit exceeded",
    )
    async_session.add(job)
    await async_session.commit()
    await async_session.refresh(job)
    return job


class TestSSEDisconnectMiddleware:
    """Tests for SSEDisconnectMiddleware."""

    @pytest.fixture
    def dummy_app(self):
        """ASGI app that records calls."""

        class DummyApp:
            def __init__(self):
                self.called = False

            async def __call__(self, scope, receive, send):
                self.called = True
                await send({"type": "http.response.start", "status": 200, "headers": []})
                await send({"type": "http.response.body", "body": b"OK"})

        return DummyApp()

    @pytest.fixture
    def raising_app(self):
        """Factory for an ASGI app that raises a given exception."""

        def _make(exc):
            async def app(scope, receive, send):
                raise exc

            return app

        return _make

    @staticmethod
    async def _collect_response(app, scope):
        parts = []

        async def send(message):
            parts.append(message)

        async def receive():
            return {"type": "http.request", "body": b""}

        await app(scope, receive, send)
        return parts

    @pytest.mark.asyncio
    async def test_normal_passthrough(self, dummy_app):
        """Normal requests pass through without modification."""
        from ace_platform.mcp.server import SSEDisconnectMiddleware

        mw = SSEDisconnectMiddleware(dummy_app)
        scope = {"type": "http", "path": "/mcp/sse"}
        parts = await self._collect_response(mw, scope)
        assert dummy_app.called
        assert parts[0]["status"] == 200

    @pytest.mark.asyncio
    async def test_suppresses_closed_resource_error(self, raising_app):
        """ClosedResourceError is caught and suppressed."""
        from anyio import ClosedResourceError

        from ace_platform.mcp.server import SSEDisconnectMiddleware

        app = raising_app(ClosedResourceError())
        mw = SSEDisconnectMiddleware(app)
        scope = {"type": "http", "path": "/mcp/sse"}
        # Should not raise
        parts = await self._collect_response(mw, scope)
        assert parts == []

    @pytest.mark.asyncio
    async def test_suppresses_broken_resource_error(self, raising_app):
        """BrokenResourceError is caught and suppressed."""
        from anyio import BrokenResourceError

        from ace_platform.mcp.server import SSEDisconnectMiddleware

        app = raising_app(BrokenResourceError())
        mw = SSEDisconnectMiddleware(app)
        scope = {"type": "http", "path": "/mcp/sse"}
        parts = await self._collect_response(mw, scope)
        assert parts == []

    @pytest.mark.asyncio
    async def test_reraises_other_exceptions(self, raising_app):
        """Non-disconnect exceptions are re-raised."""
        from ace_platform.mcp.server import SSEDisconnectMiddleware

        app = raising_app(ValueError("real error"))
        mw = SSEDisconnectMiddleware(app)
        scope = {"type": "http", "path": "/mcp/sse"}
        with pytest.raises(ValueError, match="real error"):
            await self._collect_response(mw, scope)

    @pytest.mark.asyncio
    async def test_non_http_passthrough(self, dummy_app):
        """Non-HTTP scopes pass through."""
        from ace_platform.mcp.server import SSEDisconnectMiddleware

        mw = SSEDisconnectMiddleware(dummy_app)
        scope = {"type": "lifespan"}
        await self._collect_response(mw, scope)
        assert dummy_app.called


class TestGetApiKey:
    """Tests for get_api_key helper function."""

    def test_returns_none_when_no_key_provided(self, monkeypatch):
        """Test that None is returned when no API key is available."""
        from ace_platform.mcp.server import get_api_key

        monkeypatch.delenv("ACE_API_KEY", raising=False)
        result = get_api_key()
        assert result is None

    def test_returns_env_var_when_set(self, monkeypatch):
        """Test that env var is returned when set and no parameter passed."""
        from ace_platform.mcp.server import get_api_key

        monkeypatch.setenv("ACE_API_KEY", "ace_env_key_123")
        result = get_api_key()
        assert result == "ace_env_key_123"

    def test_returns_parameter_when_passed(self, monkeypatch):
        """Test that parameter is returned when passed."""
        from ace_platform.mcp.server import get_api_key

        monkeypatch.delenv("ACE_API_KEY", raising=False)
        result = get_api_key("ace_param_key_456")
        assert result == "ace_param_key_456"

    def test_parameter_takes_priority_over_env_var(self, monkeypatch):
        """Test that parameter takes priority when both are available."""
        from ace_platform.mcp.server import get_api_key

        monkeypatch.setenv("ACE_API_KEY", "ace_env_key_123")
        result = get_api_key("ace_param_key_456")
        assert result == "ace_param_key_456"

    def test_empty_string_parameter_falls_back_to_env_var(self, monkeypatch):
        """Test that empty string parameter falls back to env var."""
        from ace_platform.mcp.server import get_api_key

        monkeypatch.setenv("ACE_API_KEY", "ace_env_key_123")
        result = get_api_key("")
        assert result == "ace_env_key_123"

    def test_none_parameter_falls_back_to_env_var(self, monkeypatch):
        """Test that None parameter falls back to env var."""
        from ace_platform.mcp.server import get_api_key

        monkeypatch.setenv("ACE_API_KEY", "ace_env_key_123")
        result = get_api_key(None)
        assert result == "ace_env_key_123"


class TestHeaderAuthMiddleware:
    """Tests for HeaderAuthMiddleware ASGI middleware."""

    @pytest.fixture
    def mock_app(self):
        """Create a mock ASGI app that records the API key from context."""
        from ace_platform.mcp.server import _request_api_key

        async def app(scope, receive, send):
            # Store the API key seen during request handling
            app.seen_api_key = _request_api_key.get()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"OK"})

        app.seen_api_key = None
        return app

    @pytest.mark.asyncio
    async def test_extracts_x_api_key_header(self, mock_app):
        """Test that X-API-Key header is extracted and available via context."""
        from ace_platform.mcp.server import HeaderAuthMiddleware

        middleware = HeaderAuthMiddleware(mock_app)
        scope = {
            "type": "http",
            "headers": [(b"x-api-key", b"test_api_key_123")],
        }

        async def receive():
            return {"type": "http.request", "body": b""}

        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        await middleware(scope, receive, send)

        assert mock_app.seen_api_key == "test_api_key_123"

    @pytest.mark.asyncio
    async def test_extracts_authorization_bearer_header(self, mock_app):
        """Test that Authorization: Bearer header is extracted."""
        from ace_platform.mcp.server import HeaderAuthMiddleware

        middleware = HeaderAuthMiddleware(mock_app)
        scope = {
            "type": "http",
            "headers": [(b"authorization", b"Bearer bearer_token_456")],
        }

        async def receive():
            return {"type": "http.request", "body": b""}

        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        await middleware(scope, receive, send)

        assert mock_app.seen_api_key == "bearer_token_456"

    @pytest.mark.asyncio
    async def test_x_api_key_takes_priority_over_authorization(self, mock_app):
        """Test that X-API-Key header takes priority over Authorization."""
        from ace_platform.mcp.server import HeaderAuthMiddleware

        middleware = HeaderAuthMiddleware(mock_app)
        scope = {
            "type": "http",
            "headers": [
                (b"x-api-key", b"x_api_key_value"),
                (b"authorization", b"Bearer bearer_value"),
            ],
        }

        async def receive():
            return {"type": "http.request", "body": b""}

        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        await middleware(scope, receive, send)

        assert mock_app.seen_api_key == "x_api_key_value"

    @pytest.mark.asyncio
    async def test_no_headers_returns_none(self, mock_app):
        """Test that missing headers result in None API key."""
        from ace_platform.mcp.server import HeaderAuthMiddleware

        middleware = HeaderAuthMiddleware(mock_app)
        scope = {
            "type": "http",
            "headers": [],
        }

        async def receive():
            return {"type": "http.request", "body": b""}

        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        await middleware(scope, receive, send)

        assert mock_app.seen_api_key is None

    @pytest.mark.asyncio
    async def test_non_http_scope_passes_through(self, mock_app):
        """Test that non-HTTP scopes pass through without modification."""
        from ace_platform.mcp.server import HeaderAuthMiddleware

        middleware = HeaderAuthMiddleware(mock_app)
        scope = {
            "type": "websocket",
            "headers": [(b"x-api-key", b"should_not_be_set")],
        }

        async def receive():
            return {"type": "websocket.connect"}

        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        await middleware(scope, receive, send)

        # For non-HTTP, the context var should be None (default)
        assert mock_app.seen_api_key is None

    @pytest.mark.asyncio
    async def test_authorization_case_insensitive(self, mock_app):
        """Test that 'bearer' prefix is case-insensitive."""
        from ace_platform.mcp.server import HeaderAuthMiddleware

        middleware = HeaderAuthMiddleware(mock_app)
        scope = {
            "type": "http",
            "headers": [(b"authorization", b"BEARER uppercase_token")],
        }

        async def receive():
            return {"type": "http.request", "body": b""}

        sent_messages = []

        async def send(message):
            sent_messages.append(message)

        await middleware(scope, receive, send)

        assert mock_app.seen_api_key == "uppercase_token"

    @pytest.mark.asyncio
    async def test_context_var_reset_after_request(self):
        """Test that context variable is properly reset after request."""
        from ace_platform.mcp.server import HeaderAuthMiddleware, _request_api_key

        # Verify initial state is None
        assert _request_api_key.get() is None

        call_count = 0

        async def counting_app(scope, receive, send):
            nonlocal call_count
            call_count += 1
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"OK"})

        middleware = HeaderAuthMiddleware(counting_app)
        scope = {
            "type": "http",
            "headers": [(b"x-api-key", b"temp_key")],
        }

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(message):
            pass

        await middleware(scope, receive, send)

        # After request, context var should be reset to default
        assert _request_api_key.get() is None
        assert call_count == 1


class TestGetApiKeyWithHeaders:
    """Tests for get_api_key integration with HeaderAuthMiddleware."""

    def test_header_takes_priority_over_env_var(self, monkeypatch):
        """Test that header API key takes priority over env var."""
        from ace_platform.mcp.server import _request_api_key, get_api_key

        monkeypatch.setenv("ACE_API_KEY", "env_key")

        # Simulate header being set by middleware
        token = _request_api_key.set("header_key")
        try:
            result = get_api_key()
            assert result == "header_key"
        finally:
            _request_api_key.reset(token)

    def test_parameter_takes_priority_over_header(self, monkeypatch):
        """Test that explicit parameter takes priority over header."""
        from ace_platform.mcp.server import _request_api_key, get_api_key

        monkeypatch.setenv("ACE_API_KEY", "env_key")

        # Simulate header being set by middleware
        token = _request_api_key.set("header_key")
        try:
            result = get_api_key("param_key")
            assert result == "param_key"
        finally:
            _request_api_key.reset(token)

    def test_falls_back_to_env_when_no_header(self, monkeypatch):
        """Test fallback to env var when no header is set."""
        from ace_platform.mcp.server import get_api_key

        monkeypatch.setenv("ACE_API_KEY", "env_key")
        # No header set (context var is default None)
        result = get_api_key()
        assert result == "env_key"


class TestRequirePaidAccess:
    """Tests for _require_paid_access helper."""

    def test_admin_bypasses_paid_access(self):
        """Admin users should bypass paid access checks."""
        from ace_platform.mcp.server import _require_paid_access

        user = SimpleNamespace(
            is_admin=True,
            subscription_status=SubscriptionStatus.CANCELED,
            subscription_tier=None,
        )

        assert _require_paid_access(user) is None

    def test_non_admin_requires_paid_subscription(self):
        """Non-admin users without paid plans should be blocked."""
        from ace_platform.mcp.server import _require_paid_access

        user = SimpleNamespace(
            is_admin=False,
            subscription_status=SubscriptionStatus.NONE,
            subscription_tier=None,
        )

        error = _require_paid_access(user)
        assert error is not None
        assert "Start your free trial" in error


class TestExtractSection:
    """Tests for _extract_section helper function."""

    def test_extract_section_exact_match(self):
        """Test extracting section with exact heading match."""
        from ace_platform.mcp.server import _extract_section

        content = """# Main Title

Introduction text.

## Getting Started

Step 1: Do this
Step 2: Do that

## Advanced Topics

More complex stuff here.
"""
        result = _extract_section(content, "Getting Started")
        assert "## Getting Started" in result
        assert "Step 1: Do this" in result
        assert "Step 2: Do that" in result
        assert "Advanced Topics" not in result

    def test_extract_section_case_insensitive(self):
        """Test that section matching is case insensitive."""
        from ace_platform.mcp.server import _extract_section

        content = """# Title

## My Section

Content here.

## Other Section

Other content.
"""
        result = _extract_section(content, "MY SECTION")
        assert "## My Section" in result
        assert "Content here" in result
        assert "Other Section" not in result

    def test_extract_section_partial_match(self):
        """Test extracting section with partial heading match."""
        from ace_platform.mcp.server import _extract_section

        content = """# Title

## Error Handling Best Practices

Handle errors gracefully.

## Logging

Log everything.
"""
        result = _extract_section(content, "error handling")
        assert "## Error Handling Best Practices" in result
        assert "Handle errors gracefully" in result
        assert "Logging" not in result

    def test_extract_section_not_found(self):
        """Test that non-existent section returns empty string."""
        from ace_platform.mcp.server import _extract_section

        content = """# Title

## Section One

Content.
"""
        result = _extract_section(content, "Nonexistent Section")
        assert result == ""

    def test_extract_section_nested_headings(self):
        """Test that nested headings are included."""
        from ace_platform.mcp.server import _extract_section

        content = """# Title

## Parent Section

Intro text.

### Child Section

Child content.

### Another Child

More child content.

## Sibling Section

Different section.
"""
        result = _extract_section(content, "Parent Section")
        assert "## Parent Section" in result
        assert "### Child Section" in result
        assert "### Another Child" in result
        assert "Sibling Section" not in result


class TestPlaybookSemanticMatchingTools:
    """Unit tests for semantic playbook matching MCP tools."""

    @pytest.mark.asyncio
    async def test_find_playbook_returns_best_match(self, monkeypatch):
        """find_playbook should return the highest-scoring playbook."""
        import ace_platform.core.api_keys as api_keys
        from ace_platform.mcp import server as mcp_server

        user = User(
            id=uuid4(),
            email="matcher@example.com",
            hashed_password="hashed",
            subscription_tier="starter",
            subscription_status=SubscriptionStatus.ACTIVE,
        )

        pb_best = Playbook(
            id=uuid4(),
            user_id=user.id,
            name="Deploy Playbook",
            description="Deployment workflow",
            status=PlaybookStatus.ACTIVE,
            source=PlaybookSource.USER_CREATED,
            semantic_embedding=[1.0, 0.0],
            semantic_embedding_model="local-hash-v1",
        )
        pb_best.current_version = PlaybookVersion(
            id=uuid4(),
            playbook_id=pb_best.id,
            version_number=1,
            content="Deploy services and verify health checks",
            bullet_count=0,
        )

        pb_other = Playbook(
            id=uuid4(),
            user_id=user.id,
            name="Debug Playbook",
            description="Debugging workflow",
            status=PlaybookStatus.ACTIVE,
            source=PlaybookSource.USER_CREATED,
            semantic_embedding=[0.0, 1.0],
            semantic_embedding_model="local-hash-v1",
        )
        pb_other.current_version = PlaybookVersion(
            id=uuid4(),
            playbook_id=pb_other.id,
            version_number=1,
            content="Investigate logs and isolate flaky tests",
            bullet_count=0,
        )

        mock_db = _MockDB([pb_best, pb_other])
        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = mock_db

        async def fake_auth(_db, _key):
            return SimpleNamespace(scopes=["playbooks:read"]), user

        monkeypatch.setattr(mcp_server, "authenticate_api_key_async", fake_auth)
        monkeypatch.setattr(mcp_server, "generate_embedding", fake_generate_embedding)
        monkeypatch.setattr(mcp_server, "generate_local_embedding", lambda _text: [1.0, 0.0])
        monkeypatch.setattr(mcp_server.settings, "openai_api_key", "")
        monkeypatch.setattr(api_keys, "check_scope", lambda *_args: True)

        result = await mcp_server.find_playbook(
            task_description="Deploy a service to production",
            api_key="ace_test_key",
            ctx=mock_ctx,
        )

        assert "Best Playbook Match" in result
        assert str(pb_best.id) in result
        assert str(pb_other.id) in result  # Included as alternative

    @pytest.mark.asyncio
    async def test_list_playbooks_task_ranks_by_relevance(self, monkeypatch):
        """list_playbooks(task=...) should order output by relevance."""
        import ace_platform.core.api_keys as api_keys
        from ace_platform.mcp import server as mcp_server

        user = User(
            id=uuid4(),
            email="matcher2@example.com",
            hashed_password="hashed",
            subscription_tier="starter",
            subscription_status=SubscriptionStatus.ACTIVE,
        )

        pb_best = Playbook(
            id=uuid4(),
            user_id=user.id,
            name="Release Playbook",
            description="Release and deploy checklist",
            status=PlaybookStatus.ACTIVE,
            source=PlaybookSource.USER_CREATED,
            semantic_embedding=[1.0, 0.0],
            semantic_embedding_model="local-hash-v1",
        )
        pb_best.current_version = PlaybookVersion(
            id=uuid4(),
            playbook_id=pb_best.id,
            version_number=1,
            content="Release deployment rollout procedure",
            bullet_count=0,
        )

        pb_other = Playbook(
            id=uuid4(),
            user_id=user.id,
            name="Retrospective Playbook",
            description="Postmortem workflow",
            status=PlaybookStatus.ACTIVE,
            source=PlaybookSource.USER_CREATED,
            semantic_embedding=[0.0, 1.0],
            semantic_embedding_model="local-hash-v1",
        )
        pb_other.current_version = PlaybookVersion(
            id=uuid4(),
            playbook_id=pb_other.id,
            version_number=1,
            content="Run retrospective and gather action items",
            bullet_count=0,
        )

        mock_db = _MockDB([pb_best, pb_other])
        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = mock_db

        async def fake_auth(_db, _key):
            return SimpleNamespace(scopes=["playbooks:read"]), user

        monkeypatch.setattr(mcp_server, "authenticate_api_key_async", fake_auth)
        monkeypatch.setattr(mcp_server, "generate_embedding", fake_generate_embedding)
        monkeypatch.setattr(mcp_server, "generate_local_embedding", lambda _text: [1.0, 0.0])
        monkeypatch.setattr(mcp_server.settings, "openai_api_key", "")
        monkeypatch.setattr(api_keys, "check_scope", lambda *_args: True)

        result = await mcp_server.list_playbooks(
            api_key="ace_test_key",
            task="Deploy a release",
            ctx=mock_ctx,
        )

        assert "Ranked by Relevance" in result
        assert result.index("Release Playbook") < result.index("Retrospective Playbook")

    @pytest.mark.asyncio
    async def test_find_playbook_rejects_oversized_task_description(self, monkeypatch):
        """find_playbook should enforce max task_description length."""
        import ace_platform.core.api_keys as api_keys
        from ace_platform.mcp import server as mcp_server

        user = User(
            id=uuid4(),
            email="matcher3@example.com",
            hashed_password="hashed",
            subscription_tier="starter",
            subscription_status=SubscriptionStatus.ACTIVE,
        )
        mock_db = _MockDB([])
        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = mock_db

        async def fake_auth(_db, _key):
            return SimpleNamespace(scopes=["playbooks:read"]), user

        async def fail_if_called(*_args, **_kwargs):
            raise AssertionError("generate_embedding should not run for oversized task input")

        monkeypatch.setattr(mcp_server, "authenticate_api_key_async", fake_auth)
        monkeypatch.setattr(mcp_server, "generate_embedding", fail_if_called)
        monkeypatch.setattr(api_keys, "check_scope", lambda *_args: True)

        result = await mcp_server.find_playbook(
            task_description="x" * 10001,
            api_key="ace_test_key",
            ctx=mock_ctx,
        )

        assert "Task description exceeds maximum size" in result

    @pytest.mark.asyncio
    async def test_list_playbooks_task_rejects_oversized_input(self, monkeypatch):
        """list_playbooks(task=...) should enforce max task length."""
        import ace_platform.core.api_keys as api_keys
        from ace_platform.mcp import server as mcp_server

        user = User(
            id=uuid4(),
            email="matcher4@example.com",
            hashed_password="hashed",
            subscription_tier="starter",
            subscription_status=SubscriptionStatus.ACTIVE,
        )
        playbook = Playbook(
            id=uuid4(),
            user_id=user.id,
            name="Any Playbook",
            description="Any description",
            status=PlaybookStatus.ACTIVE,
            source=PlaybookSource.USER_CREATED,
        )
        playbook.current_version = PlaybookVersion(
            id=uuid4(),
            playbook_id=playbook.id,
            version_number=1,
            content="Some content",
            bullet_count=0,
        )

        mock_db = _MockDB([playbook])
        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = mock_db

        async def fake_auth(_db, _key):
            return SimpleNamespace(scopes=["playbooks:read"]), user

        async def fail_if_called(*_args, **_kwargs):
            raise AssertionError("generate_embedding should not run for oversized task input")

        monkeypatch.setattr(mcp_server, "authenticate_api_key_async", fake_auth)
        monkeypatch.setattr(mcp_server, "generate_embedding", fail_if_called)
        monkeypatch.setattr(api_keys, "check_scope", lambda *_args: True)

        result = await mcp_server.list_playbooks(
            api_key="ace_test_key",
            task="x" * 10001,
            ctx=mock_ctx,
        )

        assert "Task description exceeds maximum size" in result

    @pytest.mark.asyncio
    async def test_find_playbook_does_not_backfill_embeddings(self, monkeypatch):
        """find_playbook should remain read-only for playbooks:read keys."""
        import ace_platform.core.api_keys as api_keys
        from ace_platform.mcp import server as mcp_server

        user = User(
            id=uuid4(),
            email="matcher5@example.com",
            hashed_password="hashed",
            subscription_tier="starter",
            subscription_status=SubscriptionStatus.ACTIVE,
        )

        playbook = Playbook(
            id=uuid4(),
            user_id=user.id,
            name="Deploy Playbook",
            description="Deployment workflow",
            status=PlaybookStatus.ACTIVE,
            source=PlaybookSource.USER_CREATED,
        )
        playbook.current_version = PlaybookVersion(
            id=uuid4(),
            playbook_id=playbook.id,
            version_number=1,
            content="Deploy services and verify health checks",
            bullet_count=0,
        )

        mock_db = _MockDB([playbook])
        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = mock_db

        async def fake_auth(_db, _key):
            return SimpleNamespace(scopes=["playbooks:read"]), user

        async def fail_refresh(*_args, **_kwargs):
            raise AssertionError("refresh_playbook_embedding should not be called in read paths")

        monkeypatch.setattr(mcp_server, "authenticate_api_key_async", fake_auth)
        monkeypatch.setattr(mcp_server, "generate_embedding", fake_generate_embedding)
        monkeypatch.setattr(mcp_server, "generate_local_embedding", lambda _text: [1.0, 0.0])
        monkeypatch.setattr(mcp_server, "refresh_playbook_embedding", fail_refresh)
        monkeypatch.setattr(mcp_server.settings, "openai_api_key", "")
        monkeypatch.setattr(api_keys, "check_scope", lambda *_args: True)

        result = await mcp_server.find_playbook(
            task_description="Deploy a service to production",
            api_key="ace_test_key",
            ctx=mock_ctx,
        )

        assert "Best Playbook Match" in result
        assert not mock_db.commit_called
        assert playbook.semantic_embedding is None

    @pytest.mark.asyncio
    async def test_list_playbooks_task_does_not_backfill_embeddings(self, monkeypatch):
        """list_playbooks(task=...) should remain read-only for playbooks:read keys."""
        import ace_platform.core.api_keys as api_keys
        from ace_platform.mcp import server as mcp_server

        user = User(
            id=uuid4(),
            email="matcher6@example.com",
            hashed_password="hashed",
            subscription_tier="starter",
            subscription_status=SubscriptionStatus.ACTIVE,
        )

        playbook = Playbook(
            id=uuid4(),
            user_id=user.id,
            name="Release Playbook",
            description="Release workflow",
            status=PlaybookStatus.ACTIVE,
            source=PlaybookSource.USER_CREATED,
        )
        playbook.current_version = PlaybookVersion(
            id=uuid4(),
            playbook_id=playbook.id,
            version_number=1,
            content="Release and verify production rollout",
            bullet_count=0,
        )

        mock_db = _MockDB([playbook])
        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = mock_db

        async def fake_auth(_db, _key):
            return SimpleNamespace(scopes=["playbooks:read"]), user

        async def fail_refresh(*_args, **_kwargs):
            raise AssertionError("refresh_playbook_embedding should not be called in read paths")

        monkeypatch.setattr(mcp_server, "authenticate_api_key_async", fake_auth)
        monkeypatch.setattr(mcp_server, "generate_embedding", fake_generate_embedding)
        monkeypatch.setattr(mcp_server, "generate_local_embedding", lambda _text: [1.0, 0.0])
        monkeypatch.setattr(mcp_server, "refresh_playbook_embedding", fail_refresh)
        monkeypatch.setattr(mcp_server.settings, "openai_api_key", "")
        monkeypatch.setattr(api_keys, "check_scope", lambda *_args: True)

        result = await mcp_server.list_playbooks(
            api_key="ace_test_key",
            task="Deploy a release",
            ctx=mock_ctx,
        )

        assert "Ranked by Relevance" in result
        assert not mock_db.commit_called
        assert playbook.semantic_embedding is None


async def fake_generate_embedding(_task_description, settings=None):
    """Deterministic embedding for MCP unit tests."""
    return [1.0, 0.0], "local-hash-v1"


class TestMCPRateLimitHelpers:
    """Unit tests for MCP-specific rate limit helpers."""

    def test_format_rate_limit_window_hours(self):
        """Hour-based windows are rendered clearly."""
        from ace_platform.mcp.server import _format_rate_limit_window

        assert _format_rate_limit_window(3600) == "1 hour"
        assert _format_rate_limit_window(7200) == "2 hours"

    def test_format_rate_limit_window_minutes(self):
        """Minute-based windows are rendered clearly."""
        from ace_platform.mcp.server import _format_rate_limit_window

        assert _format_rate_limit_window(60) == "1 minute"
        assert _format_rate_limit_window(300) == "5 minutes"

    @pytest.mark.asyncio
    async def test_check_mcp_rate_limit_returns_none_when_action_missing(self):
        """Unknown rate-limit actions should fail open."""
        from ace_platform.mcp.server import _check_mcp_rate_limit

        with patch("ace_platform.mcp.server.get_rate_limiter") as mock_get_rate_limiter:
            result = await _check_mcp_rate_limit(
                action="unknown_action",
                identifier="user-123",
                tool_name="some_tool",
            )

            assert result is None
            mock_get_rate_limiter.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_mcp_rate_limit_returns_none_when_allowed(self):
        """Allowed requests should pass through with no error message."""
        from ace_platform.core.rate_limit import RateLimitResult
        from ace_platform.mcp.server import _check_mcp_rate_limit

        mock_result = RateLimitResult(
            allowed=True,
            remaining=99,
            reset_at=time.time() + 60,
            limit=100,
        )

        with patch("ace_platform.mcp.server.get_rate_limiter") as mock_get_rate_limiter:
            mock_limiter = MagicMock()
            mock_limiter.is_allowed = AsyncMock(return_value=mock_result)
            mock_get_rate_limiter.return_value = mock_limiter

            result = await _check_mcp_rate_limit(
                action="outcome",
                identifier="user-123",
                tool_name="record_outcome",
            )

            assert result is None

    @pytest.mark.asyncio
    async def test_check_mcp_rate_limit_returns_clear_error_when_exceeded(self):
        """Exceeded limits should return a user-friendly throttle message."""
        from ace_platform.core.rate_limit import RateLimitResult
        from ace_platform.mcp.server import _check_mcp_rate_limit

        mock_result = RateLimitResult(
            allowed=False,
            remaining=0,
            reset_at=time.time() + 120,
            limit=100,
        )

        with patch("ace_platform.mcp.server.get_rate_limiter") as mock_get_rate_limiter:
            mock_limiter = MagicMock()
            mock_limiter.is_allowed = AsyncMock(return_value=mock_result)
            mock_get_rate_limiter.return_value = mock_limiter

            result = await _check_mcp_rate_limit(
                action="outcome",
                identifier="user-123",
                tool_name="record_outcome",
            )

            assert result is not None
            assert "Error: Rate limit exceeded for record_outcome." in result
            assert "Maximum 100 requests per 1 hour." in result
            assert "Try again in" in result

    @pytest.mark.asyncio
    async def test_check_mcp_rate_limit_allows_when_redis_unavailable(self):
        """Redis failures should fail open (request allowed)."""
        from ace_platform.mcp.server import _check_mcp_rate_limit

        with patch("ace_platform.mcp.server.get_rate_limiter") as mock_get_rate_limiter:
            mock_limiter = MagicMock()
            mock_limiter.is_allowed = AsyncMock(side_effect=Exception("Redis unavailable"))
            mock_get_rate_limiter.return_value = mock_limiter

            result = await _check_mcp_rate_limit(
                action="outcome",
                identifier="user-123",
                tool_name="record_outcome",
            )

            assert result is None


@pytest.fixture
async def test_api_key_with_write(async_session: AsyncSession, test_user: User):
    """Create a test API key with playbooks:write scope."""
    result = await create_api_key_async(
        async_session,
        test_user.id,
        "Test MCP Key with Write",
        scopes=[
            "playbooks:read",
            "playbooks:write",
            "outcomes:write",
            "evolution:write",
            "evolution:read",
        ],
    )
    await async_session.commit()
    return result


@pytestmark_integration
class TestMCPToolsIntegration:
    """Integration tests for MCP tools with database."""

    async def test_get_playbook_success(
        self, async_session: AsyncSession, test_playbook: Playbook, test_api_key
    ):
        """Test getting a playbook with valid API key."""
        from ace_platform.mcp.server import get_playbook

        # Create a mock context
        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await get_playbook(
            playbook_id=str(test_playbook.id),
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
        )

        assert "Test Playbook" in result
        assert "Step 1: Do something" in result

    async def test_get_playbook_invalid_key(self, async_session: AsyncSession, test_playbook):
        """Test getting a playbook with invalid API key."""
        from ace_platform.mcp.server import get_playbook

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await get_playbook(
            playbook_id=str(test_playbook.id),
            api_key="ace_invalid_key",
            ctx=mock_ctx,
        )

        assert "Error: Invalid or revoked API key" in result

    async def test_get_playbook_not_found(self, async_session: AsyncSession, test_api_key):
        """Test getting a non-existent playbook."""
        from uuid import uuid4

        from ace_platform.mcp.server import get_playbook

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await get_playbook(
            playbook_id=str(uuid4()),
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
        )

        assert "Error: Playbook" in result
        assert "not found" in result

    async def test_get_playbook_specific_version(
        self, async_session: AsyncSession, test_playbook_with_versions: Playbook, test_api_key
    ):
        """Test getting a specific version of a playbook."""
        from ace_platform.mcp.server import get_playbook

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        # Get version 1 (older version)
        result = await get_playbook(
            playbook_id=str(test_playbook_with_versions.id),
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
            version=1,
        )

        assert "Multi-Version Playbook" in result
        assert "(v1)" in result
        assert "Step 1: Initial setup" in result
        # Version 1 should NOT have the v2 additions
        assert "New step added in v2" not in result

    async def test_get_playbook_version_not_found(
        self, async_session: AsyncSession, test_playbook_with_versions: Playbook, test_api_key
    ):
        """Test getting a non-existent version returns error."""
        from ace_platform.mcp.server import get_playbook

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await get_playbook(
            playbook_id=str(test_playbook_with_versions.id),
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
            version=99,
        )

        assert "Error: Version 99 not found" in result

    async def test_get_playbook_section_filter(
        self, async_session: AsyncSession, test_playbook_with_versions: Playbook, test_api_key
    ):
        """Test filtering playbook content to a specific section."""
        from ace_platform.mcp.server import get_playbook

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await get_playbook(
            playbook_id=str(test_playbook_with_versions.id),
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
            section="Getting Started",
        )

        assert "Multi-Version Playbook" in result
        assert "Getting Started" in result
        assert "Step 1" in result
        # Should NOT include other sections
        assert "Advanced Topics" not in result

    async def test_get_playbook_section_not_found(
        self, async_session: AsyncSession, test_playbook_with_versions: Playbook, test_api_key
    ):
        """Test that non-existent section returns error."""
        from ace_platform.mcp.server import get_playbook

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await get_playbook(
            playbook_id=str(test_playbook_with_versions.id),
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
            section="Nonexistent Section",
        )

        assert "Error: Section 'Nonexistent Section' not found" in result

    async def test_get_playbook_version_and_section_combined(
        self, async_session: AsyncSession, test_playbook_with_versions: Playbook, test_api_key
    ):
        """Test getting a specific version filtered to a section."""
        from ace_platform.mcp.server import get_playbook

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        # Get version 1's Getting Started section
        result = await get_playbook(
            playbook_id=str(test_playbook_with_versions.id),
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
            version=1,
            section="Getting Started",
        )

        assert "(v1)" in result
        assert "Getting Started" in result
        assert "Step 1: Initial setup" in result
        # Should not have v2 content
        assert "New step added in v2" not in result
        # Should not have other sections
        assert "Advanced Topics" not in result

    async def test_list_playbooks_success(
        self, async_session: AsyncSession, test_playbook: Playbook, test_api_key
    ):
        """Test listing playbooks with valid API key."""
        from ace_platform.mcp.server import list_playbooks

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await list_playbooks(
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
        )

        assert "Test Playbook" in result
        assert str(test_playbook.id) in result

    async def test_record_outcome_success(
        self, async_session: AsyncSession, test_playbook: Playbook, test_api_key
    ):
        """Test recording an outcome with valid API key."""
        from ace_platform.mcp.server import record_outcome

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await record_outcome(
            playbook_id=str(test_playbook.id),
            task_description="Completed a test task",
            outcome="success",
            api_key=test_api_key.full_key,
            notes="Test notes",
            ctx=mock_ctx,
        )

        assert "Outcome recorded successfully" in result
        assert "success" in result

    async def test_record_outcome_invalid_status(
        self, async_session: AsyncSession, test_playbook: Playbook, test_api_key
    ):
        """Test recording an outcome with invalid status."""
        from ace_platform.mcp.server import record_outcome

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await record_outcome(
            playbook_id=str(test_playbook.id),
            task_description="Test task",
            outcome="unknown",
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
        )

        assert "Error: Invalid outcome status" in result

    async def test_record_outcome_rate_limit_exceeded(
        self, async_session: AsyncSession, test_playbook: Playbook, test_api_key
    ):
        """Test record_outcome returns a clear error when throttled."""
        from ace_platform.core.rate_limit import RATE_LIMITS, RateLimitResult
        from ace_platform.mcp.server import _format_rate_limit_window, record_outcome

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        config = RATE_LIMITS["outcome"]
        rate_limit_result = RateLimitResult(
            allowed=False,
            remaining=0,
            reset_at=time.time() + 120,
            limit=config["limit"],
        )

        with patch("ace_platform.mcp.server.get_rate_limiter") as mock_get_rate_limiter:
            mock_limiter = MagicMock()
            mock_limiter.is_allowed = AsyncMock(return_value=rate_limit_result)
            mock_get_rate_limiter.return_value = mock_limiter

            result = await record_outcome(
                playbook_id=str(test_playbook.id),
                task_description="Completed a test task",
                outcome="success",
                api_key=test_api_key.full_key,
                notes="Test notes",
                ctx=mock_ctx,
            )

        window_label = _format_rate_limit_window(config["window_seconds"])
        assert "Error: Rate limit exceeded for record_outcome." in result
        assert f"Maximum {config['limit']} requests per {window_label}." in result
        assert "Try again in" in result

    async def test_trigger_evolution_success(
        self, async_session: AsyncSession, test_playbook: Playbook, test_api_key
    ):
        """Test triggering evolution with valid API key."""
        from ace_platform.mcp.server import trigger_evolution

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await trigger_evolution(
            playbook_id=str(test_playbook.id),
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
        )

        assert "Evolution job queued" in result or "Evolution already in progress" in result

    async def test_trigger_evolution_no_scope(
        self, async_session: AsyncSession, test_playbook: Playbook, test_user: User
    ):
        """Test triggering evolution without required scope."""
        from ace_platform.mcp.server import trigger_evolution

        # Create key without evolution scope
        key_result = await create_api_key_async(
            async_session,
            test_user.id,
            "Limited Key",
            scopes=["playbooks:read"],
        )
        await async_session.commit()

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await trigger_evolution(
            playbook_id=str(test_playbook.id),
            api_key=key_result.full_key,
            ctx=mock_ctx,
        )

        assert "Error: API key lacks 'evolution:write' scope" in result

    async def test_get_evolution_status_success(
        self,
        async_session: AsyncSession,
        test_evolution_job: EvolutionJob,
        test_api_key,
    ):
        """Test getting evolution status with valid API key."""
        from ace_platform.mcp.server import get_evolution_status

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await get_evolution_status(
            job_id=str(test_evolution_job.id),
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
        )

        assert "Evolution Job Status" in result
        assert str(test_evolution_job.id) in result
        assert "completed" in result
        assert "Outcomes Processed:** 5" in result

    async def test_get_evolution_status_failed_job(
        self,
        async_session: AsyncSession,
        test_evolution_job_failed: EvolutionJob,
        test_api_key,
    ):
        """Test getting status of a failed evolution job shows error."""
        from ace_platform.mcp.server import get_evolution_status

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await get_evolution_status(
            job_id=str(test_evolution_job_failed.id),
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
        )

        assert "failed" in result
        assert "## Error" in result
        assert "Model rate limit exceeded" in result

    async def test_get_evolution_status_invalid_key(
        self, async_session: AsyncSession, test_evolution_job: EvolutionJob
    ):
        """Test getting evolution status with invalid API key."""
        from ace_platform.mcp.server import get_evolution_status

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await get_evolution_status(
            job_id=str(test_evolution_job.id),
            api_key="ace_invalid_key",
            ctx=mock_ctx,
        )

        assert "Error: Invalid or revoked API key" in result

    async def test_get_evolution_status_no_scope(
        self,
        async_session: AsyncSession,
        test_evolution_job: EvolutionJob,
        test_user: User,
    ):
        """Test getting evolution status without required scope."""
        from ace_platform.mcp.server import get_evolution_status

        # Create key without evolution:read scope
        key_result = await create_api_key_async(
            async_session,
            test_user.id,
            "Limited Key",
            scopes=["playbooks:read"],
        )
        await async_session.commit()

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await get_evolution_status(
            job_id=str(test_evolution_job.id),
            api_key=key_result.full_key,
            ctx=mock_ctx,
        )

        assert "Error: API key lacks 'evolution:read' scope" in result

    async def test_get_evolution_status_not_found(self, async_session: AsyncSession, test_api_key):
        """Test getting status of non-existent job."""
        from uuid import uuid4

        from ace_platform.mcp.server import get_evolution_status

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await get_evolution_status(
            job_id=str(uuid4()),
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
        )

        assert "Error: Evolution job" in result
        assert "not found" in result

    async def test_get_evolution_status_invalid_uuid(
        self, async_session: AsyncSession, test_api_key
    ):
        """Test getting evolution status with invalid job ID format."""
        from ace_platform.mcp.server import get_evolution_status

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await get_evolution_status(
            job_id="not-a-valid-uuid",
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
        )

        assert "Error: Invalid job ID format" in result

    async def test_get_evolution_status_access_denied(
        self, async_session: AsyncSession, test_evolution_job: EvolutionJob
    ):
        """Test that users cannot access other users' evolution jobs."""
        from ace_platform.mcp.server import get_evolution_status

        # Create a different user and API key
        other_user = User(
            email="other_user@example.com",
            hashed_password="hashed_password_here",
        )
        async_session.add(other_user)
        await async_session.commit()
        await async_session.refresh(other_user)

        other_key = await create_api_key_async(
            async_session,
            other_user.id,
            "Other User Key",
            scopes=["evolution:read"],
        )
        await async_session.commit()

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await get_evolution_status(
            job_id=str(test_evolution_job.id),
            api_key=other_key.full_key,
            ctx=mock_ctx,
        )

        assert "Error: Access denied" in result

    async def test_create_playbook_success(
        self, async_session: AsyncSession, test_api_key_with_write
    ):
        """Test creating a playbook with valid API key."""
        from ace_platform.mcp.server import create_playbook

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await create_playbook(
            name="New Playbook via MCP",
            description="A playbook created via MCP tools",
            initial_content="# My Playbook\n\n- Step 1\n- Step 2",
            api_key=test_api_key_with_write.full_key,
            ctx=mock_ctx,
        )

        assert "Playbook created successfully" in result
        assert "with version 1" in result
        assert "ID:" in result

    async def test_create_playbook_rate_limit_exceeded(
        self, async_session: AsyncSession, test_api_key_with_write
    ):
        """Test create_playbook returns a clear error when throttled."""
        from ace_platform.core.rate_limit import RATE_LIMITS, RateLimitResult
        from ace_platform.mcp.server import _format_rate_limit_window, create_playbook

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        config = RATE_LIMITS["playbook_create"]
        rate_limit_result = RateLimitResult(
            allowed=False,
            remaining=0,
            reset_at=time.time() + 120,
            limit=config["limit"],
        )

        with patch("ace_platform.mcp.server.get_rate_limiter") as mock_get_rate_limiter:
            mock_limiter = MagicMock()
            mock_limiter.is_allowed = AsyncMock(return_value=rate_limit_result)
            mock_get_rate_limiter.return_value = mock_limiter

            result = await create_playbook(
                name="Rate Limited Playbook",
                api_key=test_api_key_with_write.full_key,
                ctx=mock_ctx,
            )

        window_label = _format_rate_limit_window(config["window_seconds"])
        assert "Error: Rate limit exceeded for create_playbook." in result
        assert f"Maximum {config['limit']} requests per {window_label}." in result
        assert "Try again in" in result

    async def test_create_playbook_without_initial_content(
        self, async_session: AsyncSession, test_api_key_with_write
    ):
        """Test creating a playbook without initial content."""
        from ace_platform.mcp.server import create_playbook

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await create_playbook(
            name="Empty Playbook",
            api_key=test_api_key_with_write.full_key,
            ctx=mock_ctx,
        )

        assert "Playbook created successfully" in result
        assert "with version" not in result  # No version should be created
        assert "ID:" in result

    async def test_create_playbook_no_scope(self, async_session: AsyncSession, test_api_key):
        """Test creating a playbook without write scope."""
        from ace_platform.mcp.server import create_playbook

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await create_playbook(
            name="Should Fail",
            api_key=test_api_key.full_key,  # This key has only read scope
            ctx=mock_ctx,
        )

        assert "Error: API key lacks 'playbooks:write' scope" in result

    async def test_create_playbook_empty_name(
        self, async_session: AsyncSession, test_api_key_with_write
    ):
        """Test creating a playbook with empty name."""
        from ace_platform.mcp.server import create_playbook

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await create_playbook(
            name="   ",  # Whitespace-only name
            api_key=test_api_key_with_write.full_key,
            ctx=mock_ctx,
        )

        assert "Error:" in result
        assert "required" in result.lower() or "empty" in result.lower()

    async def test_create_version_success(
        self, async_session: AsyncSession, test_playbook: Playbook, test_api_key_with_write
    ):
        """Test creating a new version with valid API key."""
        from ace_platform.mcp.server import create_version

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await create_version(
            playbook_id=str(test_playbook.id),
            content="# Updated Playbook\n\n- New Step 1\n- New Step 2\n- New Step 3",
            diff_summary="Added new step 3",
            api_key=test_api_key_with_write.full_key,
            ctx=mock_ctx,
        )

        assert "Version" in result
        assert "created successfully" in result
        assert "ID:" in result

    async def test_create_version_rate_limit_exceeded(
        self, async_session: AsyncSession, test_playbook: Playbook, test_api_key_with_write
    ):
        """Test create_version returns a clear error when throttled."""
        from ace_platform.core.rate_limit import RATE_LIMITS, RateLimitResult
        from ace_platform.mcp.server import _format_rate_limit_window, create_version

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        config = RATE_LIMITS["version_create"]
        rate_limit_result = RateLimitResult(
            allowed=False,
            remaining=0,
            reset_at=time.time() + 120,
            limit=config["limit"],
        )

        with patch("ace_platform.mcp.server.get_rate_limiter") as mock_get_rate_limiter:
            mock_limiter = MagicMock()
            mock_limiter.is_allowed = AsyncMock(return_value=rate_limit_result)
            mock_get_rate_limiter.return_value = mock_limiter

            result = await create_version(
                playbook_id=str(test_playbook.id),
                content="# Updated Playbook",
                api_key=test_api_key_with_write.full_key,
                ctx=mock_ctx,
            )

        window_label = _format_rate_limit_window(config["window_seconds"])
        assert "Error: Rate limit exceeded for create_version." in result
        assert f"Maximum {config['limit']} requests per {window_label}." in result
        assert "Try again in" in result

    async def test_create_version_no_scope(
        self, async_session: AsyncSession, test_playbook: Playbook, test_api_key
    ):
        """Test creating a version without write scope."""
        from ace_platform.mcp.server import create_version

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await create_version(
            playbook_id=str(test_playbook.id),
            content="# New Content",
            api_key=test_api_key.full_key,  # This key has only read scope
            ctx=mock_ctx,
        )

        assert "Error: API key lacks 'playbooks:write' scope" in result

    async def test_create_version_playbook_not_found(
        self, async_session: AsyncSession, test_api_key_with_write
    ):
        """Test creating a version for non-existent playbook."""
        from uuid import uuid4

        from ace_platform.mcp.server import create_version

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await create_version(
            playbook_id=str(uuid4()),
            content="# Some Content",
            api_key=test_api_key_with_write.full_key,
            ctx=mock_ctx,
        )

        assert "Error: Playbook" in result
        assert "not found" in result

    async def test_create_version_invalid_uuid(
        self, async_session: AsyncSession, test_api_key_with_write
    ):
        """Test creating a version with invalid playbook ID."""
        from ace_platform.mcp.server import create_version

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await create_version(
            playbook_id="not-a-valid-uuid",
            content="# Some Content",
            api_key=test_api_key_with_write.full_key,
            ctx=mock_ctx,
        )

        assert "Error: Invalid playbook ID format" in result

    async def test_create_version_empty_content(
        self, async_session: AsyncSession, test_playbook: Playbook, test_api_key_with_write
    ):
        """Test creating a version with empty content."""
        from ace_platform.mcp.server import create_version

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await create_version(
            playbook_id=str(test_playbook.id),
            content="   ",  # Whitespace-only content
            api_key=test_api_key_with_write.full_key,
            ctx=mock_ctx,
        )

        assert "Error:" in result
        assert "required" in result.lower() or "empty" in result.lower()

    async def test_create_version_access_denied(
        self, async_session: AsyncSession, test_playbook: Playbook
    ):
        """Test that users cannot create versions for other users' playbooks.

        For security, unauthorized access returns a generic 'not found' error
        to avoid confirming the playbook's existence.
        """
        from ace_platform.mcp.server import create_version

        # Create a different user and API key
        other_user = User(
            email="other_version_user@example.com",
            hashed_password="hashed_password_here",
        )
        async_session.add(other_user)
        await async_session.commit()
        await async_session.refresh(other_user)

        other_key = await create_api_key_async(
            async_session,
            other_user.id,
            "Other User Key",
            scopes=["playbooks:write"],
        )
        await async_session.commit()

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await create_version(
            playbook_id=str(test_playbook.id),
            content="# Trying to Update",
            api_key=other_key.full_key,
            ctx=mock_ctx,
        )

        # Returns generic "not found" to avoid confirming playbook existence
        assert "Error: Playbook" in result
        assert "not found" in result

    async def test_create_playbook_counts_ace_bullets(
        self, async_session: AsyncSession, test_api_key_with_write
    ):
        """Test that ACE-format bullets are counted correctly."""
        from ace_platform.mcp.server import create_playbook

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        ace_content = """# ACE Playbook

[1] helpful=5 harmful=0 :: Always verify user input
[2] helpful=3 harmful=1 :: Consider edge cases
[3] helpful=10 harmful=0 :: Write tests first
"""

        result = await create_playbook(
            name="ACE Format Playbook",
            initial_content=ace_content,
            api_key=test_api_key_with_write.full_key,
            ctx=mock_ctx,
        )

        assert "Playbook created successfully" in result
        assert "3 bullets" in result

    async def test_create_playbook_max_limit_exceeded(
        self, async_session: AsyncSession, test_user: User
    ):
        """Test that playbook creation fails when max_playbooks limit is reached."""
        from ace_platform.mcp.server import create_playbook

        # Create an API key with write scope for test_user
        key_result = await create_api_key_async(
            async_session,
            test_user.id,
            "Write Key for Limit Test",
            scopes=["playbooks:write"],
        )
        await async_session.commit()

        # test_user has FREE tier by default, which allows max 1 playbook
        # Create one playbook to hit the limit
        first_playbook = Playbook(
            user_id=test_user.id,
            name="First Playbook",
            status=PlaybookStatus.ACTIVE,
            source=PlaybookSource.USER_CREATED,
        )
        async_session.add(first_playbook)
        await async_session.commit()

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        # Try to create a second playbook - should fail
        result = await create_playbook(
            name="Second Playbook Should Fail",
            api_key=key_result.full_key,
            ctx=mock_ctx,
        )

        assert "Error:" in result
        assert "maximum number of playbooks" in result
        assert "free" in result.lower()


@pytestmark_integration
class TestMCPToolsE2E:
    """End-to-end tests for MCP workflow."""

    async def test_full_mcp_workflow(
        self, async_session: AsyncSession, test_playbook: Playbook, test_api_key
    ):
        """Test complete MCP workflow: list -> get -> record -> trigger -> status."""
        from ace_platform.mcp.server import (
            get_evolution_status,
            get_playbook,
            list_playbooks,
            record_outcome,
            trigger_evolution,
        )

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        # Step 1: List playbooks
        list_result = await list_playbooks(
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
        )
        assert "Test Playbook" in list_result

        # Step 2: Get playbook content
        get_result = await get_playbook(
            playbook_id=str(test_playbook.id),
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
        )
        assert "Step 1" in get_result

        # Step 3: Record outcomes
        for i in range(3):
            outcome_result = await record_outcome(
                playbook_id=str(test_playbook.id),
                task_description=f"Task {i + 1}",
                outcome="success",
                api_key=test_api_key.full_key,
                ctx=mock_ctx,
            )
            assert "Outcome recorded successfully" in outcome_result

        # Step 4: Trigger evolution
        evolution_result = await trigger_evolution(
            playbook_id=str(test_playbook.id),
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
        )
        assert (
            "Evolution job queued" in evolution_result
            or "Evolution already in progress" in evolution_result
        )

        # Step 5: Check evolution status (extract job ID from result)
        # The trigger result contains the job ID
        import re

        job_id_match = re.search(r"Job ID: ([a-f0-9-]+)", evolution_result)
        if job_id_match:
            job_id = job_id_match.group(1)
            status_result = await get_evolution_status(
                job_id=job_id,
                api_key=test_api_key.full_key,
                ctx=mock_ctx,
            )
            assert "Evolution Job Status" in status_result
            assert job_id in status_result
