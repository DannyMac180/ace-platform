"""Evolution job management service.

This module provides functions for triggering and managing evolution jobs
with idempotency guarantees - only one active job per playbook at a time.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ace_platform.db.models import (
    EvolutionJob,
    EvolutionJobStatus,
    Playbook,
)


@dataclass
class TriggerEvolutionResult:
    """Result of triggering an evolution job."""

    job_id: UUID
    is_new: bool
    status: EvolutionJobStatus

    @property
    def job_id_str(self) -> str:
        """Return job ID as string."""
        return str(self.job_id)


async def trigger_evolution_async(
    db: AsyncSession,
    playbook_id: UUID,
) -> TriggerEvolutionResult:
    """Trigger evolution for a playbook with idempotency.

    If an active job (queued or running) already exists for the playbook,
    returns that job instead of creating a new one.

    Args:
        db: Async database session.
        playbook_id: UUID of the playbook to evolve.

    Returns:
        TriggerEvolutionResult with job_id, is_new flag, and status.

    Raises:
        ValueError: If playbook doesn't exist.
    """
    # First, check if playbook exists
    playbook = await db.get(Playbook, playbook_id)
    if not playbook:
        raise ValueError(f"Playbook {playbook_id} not found")

    # Check for existing active job
    existing_job = await _get_active_job_async(db, playbook_id)
    if existing_job:
        return TriggerEvolutionResult(
            job_id=existing_job.id,
            is_new=False,
            status=existing_job.status,
        )

    # Get current version for from_version_id
    from_version_id = playbook.current_version_id

    # Try to create new job
    try:
        new_job = EvolutionJob(
            playbook_id=playbook_id,
            status=EvolutionJobStatus.QUEUED,
            from_version_id=from_version_id,
        )
        db.add(new_job)
        await db.flush()  # Get the ID without committing

        return TriggerEvolutionResult(
            job_id=new_job.id,
            is_new=True,
            status=new_job.status,
        )
    except IntegrityError:
        # Race condition: another job was created between our check and insert
        await db.rollback()

        # Fetch the existing job
        existing_job = await _get_active_job_async(db, playbook_id)
        if existing_job:
            return TriggerEvolutionResult(
                job_id=existing_job.id,
                is_new=False,
                status=existing_job.status,
            )

        # If we still can't find it, something unexpected happened
        raise ValueError(f"Failed to create or find evolution job for playbook {playbook_id}")


async def _get_active_job_async(
    db: AsyncSession,
    playbook_id: UUID,
) -> EvolutionJob | None:
    """Get active (queued or running) job for a playbook.

    Args:
        db: Async database session.
        playbook_id: UUID of the playbook.

    Returns:
        The active EvolutionJob if one exists, None otherwise.
    """
    result = await db.execute(
        select(EvolutionJob).where(
            EvolutionJob.playbook_id == playbook_id,
            EvolutionJob.status.in_(
                [
                    EvolutionJobStatus.QUEUED,
                    EvolutionJobStatus.RUNNING,
                ]
            ),
        )
    )
    return result.scalar_one_or_none()


def trigger_evolution_sync(
    db: Session,
    playbook_id: UUID,
) -> TriggerEvolutionResult:
    """Trigger evolution for a playbook with idempotency (sync version).

    If an active job (queued or running) already exists for the playbook,
    returns that job instead of creating a new one.

    Args:
        db: Sync database session.
        playbook_id: UUID of the playbook to evolve.

    Returns:
        TriggerEvolutionResult with job_id, is_new flag, and status.

    Raises:
        ValueError: If playbook doesn't exist.
    """
    # First, check if playbook exists
    playbook = db.get(Playbook, playbook_id)
    if not playbook:
        raise ValueError(f"Playbook {playbook_id} not found")

    # Check for existing active job
    existing_job = _get_active_job_sync(db, playbook_id)
    if existing_job:
        return TriggerEvolutionResult(
            job_id=existing_job.id,
            is_new=False,
            status=existing_job.status,
        )

    # Get current version for from_version_id
    from_version_id = playbook.current_version_id

    # Try to create new job
    try:
        new_job = EvolutionJob(
            playbook_id=playbook_id,
            status=EvolutionJobStatus.QUEUED,
            from_version_id=from_version_id,
        )
        db.add(new_job)
        db.flush()  # Get the ID without committing

        return TriggerEvolutionResult(
            job_id=new_job.id,
            is_new=True,
            status=new_job.status,
        )
    except IntegrityError:
        # Race condition: another job was created between our check and insert
        db.rollback()

        # Fetch the existing job
        existing_job = _get_active_job_sync(db, playbook_id)
        if existing_job:
            return TriggerEvolutionResult(
                job_id=existing_job.id,
                is_new=False,
                status=existing_job.status,
            )

        # If we still can't find it, something unexpected happened
        raise ValueError(f"Failed to create or find evolution job for playbook {playbook_id}")


def _get_active_job_sync(
    db: Session,
    playbook_id: UUID,
) -> EvolutionJob | None:
    """Get active (queued or running) job for a playbook (sync version).

    Args:
        db: Sync database session.
        playbook_id: UUID of the playbook.

    Returns:
        The active EvolutionJob if one exists, None otherwise.
    """
    return db.execute(
        select(EvolutionJob).where(
            EvolutionJob.playbook_id == playbook_id,
            EvolutionJob.status.in_(
                [
                    EvolutionJobStatus.QUEUED,
                    EvolutionJobStatus.RUNNING,
                ]
            ),
        )
    ).scalar_one_or_none()


async def get_job_status_async(
    db: AsyncSession,
    job_id: UUID,
) -> EvolutionJob | None:
    """Get evolution job by ID.

    Args:
        db: Async database session.
        job_id: UUID of the job.

    Returns:
        The EvolutionJob if found, None otherwise.
    """
    return await db.get(EvolutionJob, job_id)


async def update_job_status_async(
    db: AsyncSession,
    job_id: UUID,
    status: EvolutionJobStatus,
    error_message: str | None = None,
) -> EvolutionJob | None:
    """Update evolution job status.

    Args:
        db: Async database session.
        job_id: UUID of the job.
        status: New status.
        error_message: Optional error message (for failed jobs).

    Returns:
        The updated EvolutionJob if found, None otherwise.
    """
    job = await db.get(EvolutionJob, job_id)
    if not job:
        return None

    job.status = status
    if status == EvolutionJobStatus.RUNNING:
        job.started_at = datetime.now(UTC)
    elif status in (EvolutionJobStatus.COMPLETED, EvolutionJobStatus.FAILED):
        job.completed_at = datetime.now(UTC)

    if error_message:
        job.error_message = error_message

    await db.flush()
    return job


async def count_active_jobs_async(
    db: AsyncSession,
    playbook_id: UUID,
) -> int:
    """Count active jobs for a playbook.

    Used for testing to verify no duplicate jobs exist.

    Args:
        db: Async database session.
        playbook_id: UUID of the playbook.

    Returns:
        Count of active (queued or running) jobs.
    """
    from sqlalchemy import func

    result = await db.execute(
        select(func.count(EvolutionJob.id)).where(
            EvolutionJob.playbook_id == playbook_id,
            EvolutionJob.status.in_(
                [
                    EvolutionJobStatus.QUEUED,
                    EvolutionJobStatus.RUNNING,
                ]
            ),
        )
    )
    return result.scalar_one()
