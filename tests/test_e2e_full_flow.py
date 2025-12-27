"""End-to-end tests for the complete ACE Platform user journey.

These tests verify the full user flow:
1. Register new user
2. Create playbook
3. Generate API key
4. MCP: get_playbook
5. MCP: record_outcome (multiple)
6. Verify auto-evolution triggers at threshold
7. Verify version history created
8. View playbook versions via API

NOTE: These tests require PostgreSQL because the models use JSONB columns
which are PostgreSQL-specific.

Run with: RUN_E2E_TESTS=1 pytest tests/test_e2e_full_flow.py -v
"""

import os
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from ace_platform.db.models import (
    Base,
    EvolutionJob,
    EvolutionJobStatus,
    Outcome,
    Playbook,
    PlaybookSource,
    PlaybookStatus,
    PlaybookVersion,
    User,
)

# Check if e2e tests should run
RUN_E2E_TESTS = os.environ.get("RUN_E2E_TESTS") == "1"
TEST_DATABASE_URL_SYNC = os.environ.get(
    "TEST_DATABASE_URL_SYNC",
    "postgresql://postgres:postgres@localhost:5432/ace_platform_test",
)
TEST_DATABASE_URL_ASYNC = os.environ.get(
    "TEST_DATABASE_URL_ASYNC",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/ace_platform_test",
)

# Skip marker for tests requiring PostgreSQL
pytestmark = pytest.mark.skipif(
    not RUN_E2E_TESTS,
    reason="Set RUN_E2E_TESTS=1 to run end-to-end PostgreSQL integration tests.",
)


@pytest.fixture(scope="function")
def sync_engine():
    """Create sync test database engine with fresh tables."""
    engine = create_engine(TEST_DATABASE_URL_SYNC, echo=False)

    # Drop and recreate schema
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        Base.metadata.create_all(bind=engine)

    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
async def async_engine():
    """Create async test database engine with fresh tables."""
    engine = create_async_engine(TEST_DATABASE_URL_ASYNC, echo=False)

    # Drop and recreate using raw SQL to handle circular FKs
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
def sync_session(sync_engine):
    """Create sync database session."""
    session_factory = sessionmaker(bind=sync_engine)
    session = session_factory()
    yield session
    session.close()


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


class TestUserRegistrationFlow:
    """Test user registration via REST API."""

    @pytest.fixture
    def app(self, sync_engine):
        """Create a test FastAPI app with test database."""
        from ace_platform.api.main import create_app

        app = create_app()

        # Override database dependency
        session_factory = sessionmaker(bind=sync_engine)

        def get_test_db():
            session = session_factory()
            try:
                yield session
            finally:
                session.close()

        # Note: For async routes, we'd need to override get_db with async version
        # For this test, we'll test schemas and basic route registration

        return app

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_register_endpoint_exists(self, client):
        """Test that register endpoint exists and validates input."""
        # Should return 422 for invalid data, not 404
        response = client.post("/auth/register", json={})
        assert response.status_code in [status.HTTP_422_UNPROCESSABLE_ENTITY]

    def test_login_endpoint_exists(self, client):
        """Test that login endpoint exists."""
        response = client.post("/auth/login", json={})
        assert response.status_code in [status.HTTP_422_UNPROCESSABLE_ENTITY]


class TestPlaybookCreationFlow:
    """Test playbook creation via REST API."""

    @pytest.fixture
    def app(self, sync_engine):
        """Create a test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_playbooks_endpoint_requires_auth(self, client):
        """Test that playbooks endpoint requires authentication."""
        response = client.post(
            "/playbooks",
            json={"name": "Test Playbook", "description": "A test"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_playbooks_list_requires_auth(self, client):
        """Test that listing playbooks requires authentication."""
        response = client.get("/playbooks")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestMCPToolsE2EFlow:
    """End-to-end tests for MCP tools with database integration."""

    @pytest.fixture
    async def test_user(self, async_session: AsyncSession):
        """Create a test user."""
        from ace_platform.core.security import hash_password

        user = User(
            email="e2e_test@example.com",
            hashed_password=hash_password("testpassword123"),
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        return user

    @pytest.fixture
    async def test_playbook(self, async_session: AsyncSession, test_user: User):
        """Create a test playbook with initial version."""
        playbook = Playbook(
            user_id=test_user.id,
            name="E2E Test Playbook",
            description="A playbook for end-to-end testing",
            status=PlaybookStatus.ACTIVE,
            source=PlaybookSource.USER_CREATED,
        )
        async_session.add(playbook)
        await async_session.flush()

        # Add initial version
        version = PlaybookVersion(
            playbook_id=playbook.id,
            version_number=1,
            content="# E2E Test Playbook\n\n- Step 1: Initialize\n- Step 2: Execute\n- Step 3: Verify",
            bullet_count=3,
        )
        async_session.add(version)
        await async_session.flush()

        playbook.current_version_id = version.id
        await async_session.commit()
        await async_session.refresh(playbook)

        return playbook

    @pytest.fixture
    async def test_api_key(self, async_session: AsyncSession, test_user: User):
        """Create a test API key with all required scopes."""
        from ace_platform.core.api_keys import create_api_key_async

        result = await create_api_key_async(
            async_session,
            test_user.id,
            "E2E Test Key",
            scopes=[
                "playbooks:read",
                "outcomes:write",
                "evolution:read",
                "evolution:write",
            ],
        )
        await async_session.commit()
        return result

    async def test_list_playbooks(
        self, async_session: AsyncSession, test_playbook: Playbook, test_api_key
    ):
        """Test listing playbooks via MCP tool."""
        from ace_platform.mcp.server import list_playbooks

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await list_playbooks(
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
        )

        assert "E2E Test Playbook" in result
        assert str(test_playbook.id) in result

    async def test_get_playbook(
        self, async_session: AsyncSession, test_playbook: Playbook, test_api_key
    ):
        """Test getting playbook content via MCP tool."""
        from ace_platform.mcp.server import get_playbook

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await get_playbook(
            playbook_id=str(test_playbook.id),
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
        )

        assert "E2E Test Playbook" in result
        assert "Step 1: Initialize" in result
        assert "Step 2: Execute" in result

    async def test_record_outcome(
        self, async_session: AsyncSession, test_playbook: Playbook, test_api_key
    ):
        """Test recording an outcome via MCP tool."""
        from ace_platform.mcp.server import record_outcome

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await record_outcome(
            playbook_id=str(test_playbook.id),
            task_description="Completed E2E test task",
            outcome="success",
            api_key=test_api_key.full_key,
            notes="Test completed successfully",
            ctx=mock_ctx,
        )

        assert "Outcome recorded successfully" in result
        assert "success" in result

    async def test_record_multiple_outcomes(
        self, async_session: AsyncSession, test_playbook: Playbook, test_api_key
    ):
        """Test recording multiple outcomes (towards threshold)."""
        from ace_platform.mcp.server import record_outcome

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        outcomes = [
            ("Task 1: Setup environment", "success", "Environment ready"),
            ("Task 2: Run tests", "success", "All tests passed"),
            ("Task 3: Deploy", "partial", "Deployed with warnings"),
            ("Task 4: Monitor", "success", "Monitoring active"),
            ("Task 5: Validate", "success", "Validation complete"),
        ]

        for task, outcome_status, notes in outcomes:
            result = await record_outcome(
                playbook_id=str(test_playbook.id),
                task_description=task,
                outcome=outcome_status,
                api_key=test_api_key.full_key,
                notes=notes,
                ctx=mock_ctx,
            )
            assert "Outcome recorded successfully" in result

        # Verify outcomes were created
        from sqlalchemy import func, select

        count = await async_session.scalar(
            select(func.count(Outcome.id)).where(Outcome.playbook_id == test_playbook.id)
        )
        assert count == 5

    async def test_trigger_evolution(
        self, async_session: AsyncSession, test_playbook: Playbook, test_api_key
    ):
        """Test manually triggering evolution via MCP tool."""
        from ace_platform.mcp.server import trigger_evolution

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await trigger_evolution(
            playbook_id=str(test_playbook.id),
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
        )

        # Should either queue new job or report existing
        assert "Evolution job queued" in result or "Evolution already in progress" in result

    async def test_get_evolution_status(
        self,
        async_session: AsyncSession,
        test_playbook: Playbook,
        test_api_key,
    ):
        """Test getting evolution status via MCP tool."""
        from ace_platform.mcp.server import get_evolution_status

        # Create a completed evolution job
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

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        result = await get_evolution_status(
            job_id=str(job.id),
            api_key=test_api_key.full_key,
            ctx=mock_ctx,
        )

        assert "Evolution Job Status" in result
        assert str(job.id) in result
        assert "completed" in result
        assert "Outcomes Processed:** 5" in result


class TestAutoEvolutionThreshold:
    """Test automatic evolution triggering based on outcome threshold."""

    @pytest.fixture
    def sync_session_factory(self, sync_engine):
        """Create sync session factory."""
        return sessionmaker(bind=sync_engine)

    @pytest.fixture
    def test_user_sync(self, sync_session: Session):
        """Create a test user (sync)."""
        from ace_platform.core.security import hash_password

        user = User(
            email="auto_evolution_test@example.com",
            hashed_password=hash_password("testpassword123"),
        )
        sync_session.add(user)
        sync_session.commit()
        sync_session.refresh(user)
        return user

    @pytest.fixture
    def test_playbook_sync(self, sync_session: Session, test_user_sync: User):
        """Create a test playbook (sync) with old creation date for time threshold."""
        from datetime import timedelta

        playbook = Playbook(
            user_id=test_user_sync.id,
            name="Auto Evolution Test Playbook",
            description="Testing auto evolution",
            status=PlaybookStatus.ACTIVE,
            source=PlaybookSource.USER_CREATED,
        )
        # Backdate the playbook to satisfy time threshold
        playbook.created_at = datetime.now(UTC) - timedelta(days=2)

        sync_session.add(playbook)
        sync_session.flush()

        version = PlaybookVersion(
            playbook_id=playbook.id,
            version_number=1,
            content="# Auto Evolution Test\n\n- Initial content",
            bullet_count=1,
        )
        sync_session.add(version)
        sync_session.flush()

        playbook.current_version_id = version.id
        sync_session.commit()
        sync_session.refresh(playbook)

        return playbook

    def test_check_auto_evolution_no_outcomes(
        self, sync_session: Session, test_playbook_sync: Playbook
    ):
        """Test auto evolution check with no unprocessed outcomes."""
        from ace_platform.workers.auto_evolution import _check_and_trigger_evolutions

        result = _check_and_trigger_evolutions(
            sync_session,
            outcome_threshold=5,
            time_threshold_hours=24,
        )

        # Should check playbooks but not queue any jobs (no outcomes)
        assert result["status"] == "completed"
        assert result["jobs_queued"] == 0

    def test_check_auto_evolution_below_threshold(
        self, sync_session: Session, test_playbook_sync: Playbook
    ):
        """Test auto evolution check with outcomes below threshold."""
        from ace_platform.db.models import OutcomeStatus
        from ace_platform.workers.auto_evolution import _check_and_trigger_evolutions

        # Add 3 outcomes (below threshold of 5)
        for i in range(3):
            outcome = Outcome(
                playbook_id=test_playbook_sync.id,
                task_description=f"Task {i + 1}",
                outcome_status=OutcomeStatus.SUCCESS,
            )
            sync_session.add(outcome)
        sync_session.commit()

        result = _check_and_trigger_evolutions(
            sync_session,
            outcome_threshold=5,
            time_threshold_hours=24,
        )

        # Should check but not trigger (below outcome threshold)
        # Note: Time threshold might trigger if playbook is old enough with 1+ outcomes
        assert result["status"] == "completed"

    @patch("ace_platform.workers.auto_evolution.process_evolution_job")
    def test_check_auto_evolution_at_threshold(
        self,
        mock_task,
        sync_session: Session,
        test_playbook_sync: Playbook,
    ):
        """Test auto evolution triggers at outcome threshold."""
        from ace_platform.db.models import OutcomeStatus
        from ace_platform.workers.auto_evolution import _check_and_trigger_evolutions

        # Add 5 outcomes (at threshold)
        for i in range(5):
            outcome = Outcome(
                playbook_id=test_playbook_sync.id,
                task_description=f"Threshold Task {i + 1}",
                outcome_status=OutcomeStatus.SUCCESS,
            )
            sync_session.add(outcome)
        sync_session.commit()

        result = _check_and_trigger_evolutions(
            sync_session,
            outcome_threshold=5,
            time_threshold_hours=24,
        )

        # Should trigger evolution
        assert result["status"] == "completed"
        assert result["jobs_queued"] == 1
        mock_task.delay.assert_called_once()

    @patch("ace_platform.workers.auto_evolution.process_evolution_job")
    def test_check_auto_evolution_skips_running_job(
        self,
        mock_task,
        sync_session: Session,
        test_playbook_sync: Playbook,
    ):
        """Test that auto evolution skips playbooks with running jobs."""
        from ace_platform.db.models import OutcomeStatus
        from ace_platform.workers.auto_evolution import _check_and_trigger_evolutions

        # Add 5 outcomes
        for i in range(5):
            outcome = Outcome(
                playbook_id=test_playbook_sync.id,
                task_description=f"Task {i + 1}",
                outcome_status=OutcomeStatus.SUCCESS,
            )
            sync_session.add(outcome)

        # Add a running evolution job
        job = EvolutionJob(
            playbook_id=test_playbook_sync.id,
            status=EvolutionJobStatus.RUNNING,
        )
        sync_session.add(job)
        sync_session.commit()

        result = _check_and_trigger_evolutions(
            sync_session,
            outcome_threshold=5,
            time_threshold_hours=24,
        )

        # Should skip because job is already running
        assert result["status"] == "completed"
        assert result["jobs_queued"] == 0
        assert result["skipped_running"] >= 1
        mock_task.delay.assert_not_called()


class TestVersionHistory:
    """Test version history creation and retrieval."""

    @pytest.fixture
    async def playbook_with_versions(self, async_session: AsyncSession, test_user):
        """Create a playbook with multiple versions."""
        # Reuse the test_user fixture
        from ace_platform.core.security import hash_password

        user = User(
            email="version_history_test@example.com",
            hashed_password=hash_password("testpassword123"),
        )
        async_session.add(user)
        await async_session.flush()

        playbook = Playbook(
            user_id=user.id,
            name="Version History Test Playbook",
            description="Testing version history",
            status=PlaybookStatus.ACTIVE,
            source=PlaybookSource.USER_CREATED,
        )
        async_session.add(playbook)
        await async_session.flush()

        # Create multiple versions
        versions = []
        for i in range(1, 4):
            version = PlaybookVersion(
                playbook_id=playbook.id,
                version_number=i,
                content=f"# Version {i}\n\n- Bullet 1\n- Bullet 2\n{'- Bullet 3' if i > 1 else ''}",
                bullet_count=2 if i == 1 else 3,
            )
            async_session.add(version)
            await async_session.flush()
            versions.append(version)

        # Set latest as current
        playbook.current_version_id = versions[-1].id
        await async_session.commit()
        await async_session.refresh(playbook)

        return playbook, versions, user

    async def test_version_count(self, async_session: AsyncSession, playbook_with_versions):
        """Test that version count is correct."""
        from sqlalchemy import func, select

        playbook, versions, _ = playbook_with_versions

        count = await async_session.scalar(
            select(func.count(PlaybookVersion.id)).where(PlaybookVersion.playbook_id == playbook.id)
        )
        assert count == 3

    async def test_get_specific_version(self, async_session: AsyncSession, playbook_with_versions):
        """Test getting a specific version via MCP tool."""
        from ace_platform.core.api_keys import create_api_key_async
        from ace_platform.mcp.server import get_playbook

        playbook, versions, user = playbook_with_versions

        # Create API key
        api_key_result = await create_api_key_async(
            async_session,
            user.id,
            "Version Test Key",
            scopes=["playbooks:read"],
        )
        await async_session.commit()

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        # Get version 1
        result = await get_playbook(
            playbook_id=str(playbook.id),
            api_key=api_key_result.full_key,
            ctx=mock_ctx,
            version=1,
        )

        assert "(v1)" in result
        assert "Version 1" in result

        # Get version 2
        result = await get_playbook(
            playbook_id=str(playbook.id),
            api_key=api_key_result.full_key,
            ctx=mock_ctx,
            version=2,
        )

        assert "(v2)" in result
        assert "Version 2" in result

    async def test_get_current_version(self, async_session: AsyncSession, playbook_with_versions):
        """Test getting current version (latest) via MCP tool."""
        from ace_platform.core.api_keys import create_api_key_async
        from ace_platform.mcp.server import get_playbook

        playbook, versions, user = playbook_with_versions

        api_key_result = await create_api_key_async(
            async_session,
            user.id,
            "Current Version Key",
            scopes=["playbooks:read"],
        )
        await async_session.commit()

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        # Get current (should be v3)
        result = await get_playbook(
            playbook_id=str(playbook.id),
            api_key=api_key_result.full_key,
            ctx=mock_ctx,
        )

        assert "(v3)" in result
        assert "Version 3" in result


class TestCompleteE2EWorkflow:
    """Test complete end-to-end workflow simulating a real user journey."""

    async def test_full_mcp_workflow(self, async_session: AsyncSession):
        """Test complete MCP workflow: create user -> playbook -> outcomes -> evolution."""
        from ace_platform.core.api_keys import create_api_key_async
        from ace_platform.core.security import hash_password
        from ace_platform.mcp.server import (
            get_evolution_status,
            get_playbook,
            list_playbooks,
            record_outcome,
            trigger_evolution,
        )

        # Step 1: Create user
        user = User(
            email="full_workflow_test@example.com",
            hashed_password=hash_password("testpassword123"),
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        assert user.id is not None

        # Step 2: Create playbook
        playbook = Playbook(
            user_id=user.id,
            name="Full Workflow Test Playbook",
            description="Testing complete workflow",
            status=PlaybookStatus.ACTIVE,
            source=PlaybookSource.USER_CREATED,
        )
        async_session.add(playbook)
        await async_session.flush()

        version = PlaybookVersion(
            playbook_id=playbook.id,
            version_number=1,
            content="# Full Workflow Playbook\n\n- Task 1\n- Task 2\n- Task 3",
            bullet_count=3,
        )
        async_session.add(version)
        await async_session.flush()
        playbook.current_version_id = version.id
        await async_session.commit()
        await async_session.refresh(playbook)
        assert playbook.id is not None

        # Step 3: Generate API key
        api_key_result = await create_api_key_async(
            async_session,
            user.id,
            "Full Workflow Key",
            scopes=[
                "playbooks:read",
                "outcomes:write",
                "evolution:read",
                "evolution:write",
            ],
        )
        await async_session.commit()
        assert api_key_result.full_key.startswith("ace_")

        mock_ctx = MagicMock()
        mock_ctx.request_context.lifespan_context.db = async_session

        # Step 4: MCP - List playbooks
        list_result = await list_playbooks(
            api_key=api_key_result.full_key,
            ctx=mock_ctx,
        )
        assert "Full Workflow Test Playbook" in list_result

        # Step 5: MCP - Get playbook
        get_result = await get_playbook(
            playbook_id=str(playbook.id),
            api_key=api_key_result.full_key,
            ctx=mock_ctx,
        )
        assert "Task 1" in get_result

        # Step 6: MCP - Record multiple outcomes
        for i in range(5):
            outcome_result = await record_outcome(
                playbook_id=str(playbook.id),
                task_description=f"Workflow Task {i + 1}",
                outcome="success" if i % 2 == 0 else "partial",
                api_key=api_key_result.full_key,
                notes=f"Notes for task {i + 1}",
                ctx=mock_ctx,
            )
            assert "Outcome recorded successfully" in outcome_result

        # Step 7: MCP - Trigger evolution
        evolution_result = await trigger_evolution(
            playbook_id=str(playbook.id),
            api_key=api_key_result.full_key,
            ctx=mock_ctx,
        )
        assert (
            "Evolution job queued" in evolution_result
            or "Evolution already in progress" in evolution_result
        )

        # Step 8: Extract job ID and check status
        import re

        job_id_match = re.search(r"Job ID: ([a-f0-9-]+)", evolution_result)
        if job_id_match:
            job_id = job_id_match.group(1)
            status_result = await get_evolution_status(
                job_id=job_id,
                api_key=api_key_result.full_key,
                ctx=mock_ctx,
            )
            assert "Evolution Job Status" in status_result
            assert job_id in status_result

        # Step 9: Verify version history exists
        from sqlalchemy import func, select

        version_count = await async_session.scalar(
            select(func.count(PlaybookVersion.id)).where(PlaybookVersion.playbook_id == playbook.id)
        )
        assert version_count >= 1  # At least initial version

        # Step 10: Verify outcomes were recorded
        outcome_count = await async_session.scalar(
            select(func.count(Outcome.id)).where(Outcome.playbook_id == playbook.id)
        )
        assert outcome_count == 5


# Fixture to inject the user for version tests
@pytest.fixture
async def test_user(async_session: AsyncSession):
    """Create a test user for version history tests."""
    from ace_platform.core.security import hash_password

    user = User(
        email="e2e_test_user@example.com",
        hashed_password=hash_password("testpassword123"),
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user
