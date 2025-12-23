"""Tests for evolution job idempotency.

These tests verify that:
1. Only one active evolution job can exist per playbook
2. Triggering evolution while a job is queued/running returns the existing job
3. No duplicate jobs are created under concurrent conditions

NOTE: These tests require PostgreSQL because the models use JSONB columns
and partial unique indexes which are PostgreSQL-specific features.
"""

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from ace_platform.core.evolution_jobs import (
    count_active_jobs_async,
    trigger_evolution_async,
    trigger_evolution_sync,
    update_job_status_async,
)
from ace_platform.db.models import (
    Base,
    EvolutionJobStatus,
    Playbook,
    PlaybookSource,
    PlaybookStatus,
    User,
)

# PostgreSQL test database URL - requires running PostgreSQL
# Uses environment variable or defaults to test database
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

    # Drop and recreate using raw SQL to handle circular FKs
    async with engine.begin() as conn:
        # Drop all tables with CASCADE to handle circular dependencies
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

    # Drop and recreate using raw SQL to handle circular FKs
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
async def test_playbook(async_session: AsyncSession, test_user: User):
    """Create a test playbook."""
    playbook = Playbook(
        user_id=test_user.id,
        name="Test Playbook",
        description="A test playbook for evolution",
        status=PlaybookStatus.ACTIVE,
        source=PlaybookSource.USER_CREATED,
    )
    async_session.add(playbook)
    await async_session.commit()
    await async_session.refresh(playbook)
    return playbook


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


@pytest.fixture
def test_playbook_sync(sync_session: Session, test_user_sync: User):
    """Create a test playbook (sync version)."""
    playbook = Playbook(
        user_id=test_user_sync.id,
        name="Test Playbook",
        description="A test playbook for evolution",
        status=PlaybookStatus.ACTIVE,
        source=PlaybookSource.USER_CREATED,
    )
    sync_session.add(playbook)
    sync_session.commit()
    sync_session.refresh(playbook)
    return playbook


class TestTriggerEvolutionAsync:
    """Tests for async evolution triggering with idempotency."""

    async def test_trigger_creates_new_job(
        self, async_session: AsyncSession, test_playbook: Playbook
    ):
        """Test that triggering evolution creates a new job."""
        result = await trigger_evolution_async(async_session, test_playbook.id)
        await async_session.commit()

        assert result.is_new is True
        assert result.status == EvolutionJobStatus.QUEUED
        assert result.job_id is not None

    async def test_trigger_returns_existing_queued_job(
        self, async_session: AsyncSession, test_playbook: Playbook
    ):
        """Test that triggering again returns existing queued job."""
        # First trigger creates new job
        result1 = await trigger_evolution_async(async_session, test_playbook.id)
        await async_session.commit()

        # Second trigger should return same job
        result2 = await trigger_evolution_async(async_session, test_playbook.id)

        assert result2.is_new is False
        assert result2.job_id == result1.job_id
        assert result2.status == EvolutionJobStatus.QUEUED

    async def test_trigger_returns_existing_running_job(
        self, async_session: AsyncSession, test_playbook: Playbook
    ):
        """Test that triggering returns existing running job."""
        # Create and start a job
        result1 = await trigger_evolution_async(async_session, test_playbook.id)
        await async_session.commit()

        # Update to running status
        await update_job_status_async(async_session, result1.job_id, EvolutionJobStatus.RUNNING)
        await async_session.commit()

        # Trigger again should return same job
        result2 = await trigger_evolution_async(async_session, test_playbook.id)

        assert result2.is_new is False
        assert result2.job_id == result1.job_id
        assert result2.status == EvolutionJobStatus.RUNNING

    async def test_trigger_creates_new_after_completed(
        self, async_session: AsyncSession, test_playbook: Playbook
    ):
        """Test that a new job is created after previous completes."""
        # Create and complete a job
        result1 = await trigger_evolution_async(async_session, test_playbook.id)
        await async_session.commit()

        await update_job_status_async(async_session, result1.job_id, EvolutionJobStatus.COMPLETED)
        await async_session.commit()

        # Trigger again should create new job
        result2 = await trigger_evolution_async(async_session, test_playbook.id)
        await async_session.commit()

        assert result2.is_new is True
        assert result2.job_id != result1.job_id

    async def test_trigger_creates_new_after_failed(
        self, async_session: AsyncSession, test_playbook: Playbook
    ):
        """Test that a new job is created after previous fails."""
        # Create and fail a job
        result1 = await trigger_evolution_async(async_session, test_playbook.id)
        await async_session.commit()

        await update_job_status_async(
            async_session,
            result1.job_id,
            EvolutionJobStatus.FAILED,
            error_message="Test failure",
        )
        await async_session.commit()

        # Trigger again should create new job
        result2 = await trigger_evolution_async(async_session, test_playbook.id)
        await async_session.commit()

        assert result2.is_new is True
        assert result2.job_id != result1.job_id

    async def test_no_duplicate_jobs_created(
        self, async_session: AsyncSession, test_playbook: Playbook
    ):
        """Test that no duplicate active jobs are created."""
        # Trigger multiple times
        result1 = await trigger_evolution_async(async_session, test_playbook.id)
        await async_session.commit()

        result2 = await trigger_evolution_async(async_session, test_playbook.id)
        result3 = await trigger_evolution_async(async_session, test_playbook.id)

        # All should return same job
        assert result1.job_id == result2.job_id == result3.job_id

        # Only one active job should exist
        active_count = await count_active_jobs_async(async_session, test_playbook.id)
        assert active_count == 1

    async def test_trigger_nonexistent_playbook_raises(self, async_session: AsyncSession):
        """Test that triggering for nonexistent playbook raises error."""
        fake_playbook_id = uuid4()

        with pytest.raises(ValueError, match="not found"):
            await trigger_evolution_async(async_session, fake_playbook_id)


class TestTriggerEvolutionSync:
    """Tests for sync evolution triggering with idempotency."""

    def test_trigger_creates_new_job_sync(
        self, sync_session: Session, test_playbook_sync: Playbook
    ):
        """Test that triggering evolution creates a new job (sync)."""
        result = trigger_evolution_sync(sync_session, test_playbook_sync.id)
        sync_session.commit()

        assert result.is_new is True
        assert result.status == EvolutionJobStatus.QUEUED
        assert result.job_id is not None

    def test_trigger_returns_existing_job_sync(
        self, sync_session: Session, test_playbook_sync: Playbook
    ):
        """Test that triggering again returns existing job (sync)."""
        # First trigger creates new job
        result1 = trigger_evolution_sync(sync_session, test_playbook_sync.id)
        sync_session.commit()

        # Second trigger should return same job
        result2 = trigger_evolution_sync(sync_session, test_playbook_sync.id)

        assert result2.is_new is False
        assert result2.job_id == result1.job_id


class TestEvolutionIdempotencyE2E:
    """End-to-end tests for evolution idempotency.

    These tests simulate the full workflow described in ace-platform-87:
    1. Trigger evolution for a playbook
    2. While job is queued/running, trigger again
    3. Verify same job_id returned (is_new=false)
    4. Verify no duplicate jobs created
    """

    async def test_full_idempotency_workflow(
        self, async_session: AsyncSession, test_playbook: Playbook
    ):
        """Test the complete idempotency workflow from the issue."""
        # Step 1: Trigger evolution for a playbook
        result1 = await trigger_evolution_async(async_session, test_playbook.id)
        await async_session.commit()

        assert result1.is_new is True
        first_job_id = result1.job_id

        # Step 2: While job is queued, trigger again
        result2 = await trigger_evolution_async(async_session, test_playbook.id)

        # Step 3: Verify same job_id returned (is_new=false)
        assert result2.is_new is False
        assert result2.job_id == first_job_id

        # Simulate job moving to running state
        await update_job_status_async(async_session, first_job_id, EvolutionJobStatus.RUNNING)
        await async_session.commit()

        # Trigger again while running
        result3 = await trigger_evolution_async(async_session, test_playbook.id)
        assert result3.is_new is False
        assert result3.job_id == first_job_id

        # Step 4: Verify no duplicate jobs created
        active_count = await count_active_jobs_async(async_session, test_playbook.id)
        assert active_count == 1

        # Complete the job
        await update_job_status_async(async_session, first_job_id, EvolutionJobStatus.COMPLETED)
        await async_session.commit()

        # Now triggering should create a new job
        result4 = await trigger_evolution_async(async_session, test_playbook.id)
        await async_session.commit()

        assert result4.is_new is True
        assert result4.job_id != first_job_id

    async def test_multiple_playbooks_independent(
        self, async_session: AsyncSession, test_user: User
    ):
        """Test that different playbooks have independent job tracking."""
        # Create two playbooks
        playbook1 = Playbook(
            user_id=test_user.id,
            name="Playbook 1",
            status=PlaybookStatus.ACTIVE,
            source=PlaybookSource.USER_CREATED,
        )
        playbook2 = Playbook(
            user_id=test_user.id,
            name="Playbook 2",
            status=PlaybookStatus.ACTIVE,
            source=PlaybookSource.USER_CREATED,
        )
        async_session.add_all([playbook1, playbook2])
        await async_session.commit()

        # Trigger evolution for both
        result1 = await trigger_evolution_async(async_session, playbook1.id)
        result2 = await trigger_evolution_async(async_session, playbook2.id)
        await async_session.commit()

        # Both should be new jobs with different IDs
        assert result1.is_new is True
        assert result2.is_new is True
        assert result1.job_id != result2.job_id

        # Each should have exactly one active job
        assert await count_active_jobs_async(async_session, playbook1.id) == 1
        assert await count_active_jobs_async(async_session, playbook2.id) == 1
