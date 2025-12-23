"""Tests for MCP server and tools.

These tests verify:
1. MCP tool scope definitions
2. Scope validation
3. MCP tools functionality with database integration

NOTE: Database integration tests require PostgreSQL because the models
use JSONB columns which are PostgreSQL-specific.
"""

import os
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ace_platform.core.api_keys import create_api_key_async
from ace_platform.db.models import (
    Base,
    Playbook,
    PlaybookSource,
    PlaybookStatus,
    PlaybookVersion,
    User,
)
from ace_platform.mcp.tools import (
    DEFAULT_SCOPES,
    SCOPE_DESCRIPTIONS,
    MCPScope,
    validate_scopes,
)

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
async def test_api_key(async_session: AsyncSession, test_user: User):
    """Create a test API key with default scopes."""
    result = await create_api_key_async(
        async_session,
        test_user.id,
        "Test MCP Key",
        scopes=["playbooks:read", "outcomes:write", "evolution:write"],
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


@pytestmark_integration
class TestMCPToolsE2E:
    """End-to-end tests for MCP workflow."""

    async def test_full_mcp_workflow(
        self, async_session: AsyncSession, test_playbook: Playbook, test_api_key
    ):
        """Test complete MCP workflow: list -> get -> record -> trigger."""
        from ace_platform.mcp.server import (
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
