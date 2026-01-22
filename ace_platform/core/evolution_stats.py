"""Evolution statistics and aggregation.

This module provides functions to aggregate evolution job data for the usage page.
It focuses on evolution runs as the primary metric for user activity.

Key functions:
- get_evolution_summary: Get aggregate evolution statistics
- get_evolution_by_day: Get daily evolution breakdown
- get_evolution_by_playbook: Get evolution stats grouped by playbook
- get_recent_evolutions: Get recent evolution runs across all playbooks
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.db.models import EvolutionJob, EvolutionJobStatus, Playbook, PlaybookVersion


@dataclass
class EvolutionSummary:
    """Summary of evolution activity for a time period."""

    user_id: UUID
    start_date: datetime
    end_date: datetime
    total_evolutions: int
    completed_evolutions: int
    failed_evolutions: int
    running_evolutions: int
    queued_evolutions: int
    success_rate: float
    total_outcomes_processed: int


@dataclass
class DailyEvolution:
    """Evolution activity for a single day."""

    date: datetime
    total_evolutions: int
    completed: int
    failed: int
    running: int
    queued: int


@dataclass
class PlaybookEvolutionStats:
    """Evolution statistics grouped by playbook."""

    playbook_id: UUID
    playbook_name: str
    total_evolutions: int
    completed: int
    failed: int
    success_rate: float
    last_evolution_at: datetime | None


@dataclass
class RecentEvolution:
    """Recent evolution run details."""

    id: UUID
    playbook_id: UUID
    playbook_name: str
    status: EvolutionJobStatus
    outcomes_processed: int
    from_version_number: int | None
    to_version_number: int | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None


async def get_evolution_summary(
    db: AsyncSession,
    user_id: UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> EvolutionSummary:
    """Get aggregated evolution summary for a user.

    Args:
        db: Database session.
        user_id: User ID to get stats for.
        start_date: Start of period (inclusive). Defaults to 30 days ago.
        end_date: End of period (inclusive). Defaults to now.

    Returns:
        EvolutionSummary with aggregated totals.
    """
    if end_date is None:
        end_date = datetime.now(UTC)
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    # Query evolution jobs joined with playbooks to filter by user
    query = (
        select(
            func.count(EvolutionJob.id).label("total_evolutions"),
            func.sum(
                func.cast(EvolutionJob.status == EvolutionJobStatus.COMPLETED, func.INTEGER())
            ).label("completed_evolutions"),
            func.sum(
                func.cast(EvolutionJob.status == EvolutionJobStatus.FAILED, func.INTEGER())
            ).label("failed_evolutions"),
            func.sum(
                func.cast(EvolutionJob.status == EvolutionJobStatus.RUNNING, func.INTEGER())
            ).label("running_evolutions"),
            func.sum(
                func.cast(EvolutionJob.status == EvolutionJobStatus.QUEUED, func.INTEGER())
            ).label("queued_evolutions"),
            func.coalesce(func.sum(EvolutionJob.outcomes_processed), 0).label(
                "total_outcomes_processed"
            ),
        )
        .select_from(EvolutionJob)
        .join(Playbook, EvolutionJob.playbook_id == Playbook.id)
        .where(
            Playbook.user_id == user_id,
            EvolutionJob.started_at >= start_date,
            EvolutionJob.started_at <= end_date,
        )
    )

    result = await db.execute(query)
    row = result.one()

    total = row.total_evolutions or 0
    completed = row.completed_evolutions or 0
    success_rate = (completed / total) if total > 0 else 0.0

    return EvolutionSummary(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        total_evolutions=total,
        completed_evolutions=completed,
        failed_evolutions=row.failed_evolutions or 0,
        running_evolutions=row.running_evolutions or 0,
        queued_evolutions=row.queued_evolutions or 0,
        success_rate=success_rate,
        total_outcomes_processed=row.total_outcomes_processed or 0,
    )


async def get_evolution_by_day(
    db: AsyncSession,
    user_id: UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[DailyEvolution]:
    """Get daily evolution breakdown for a user.

    Args:
        db: Database session.
        user_id: User ID to get stats for.
        start_date: Start of period (inclusive). Defaults to 30 days ago.
        end_date: End of period (inclusive). Defaults to now.

    Returns:
        List of DailyEvolution records, ordered by date ascending.
    """
    if end_date is None:
        end_date = datetime.now(UTC)
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    # Group by date (truncate to day)
    date_trunc = func.date_trunc("day", EvolutionJob.started_at)

    query = (
        select(
            date_trunc.label("date"),
            func.count(EvolutionJob.id).label("total_evolutions"),
            func.sum(
                func.cast(EvolutionJob.status == EvolutionJobStatus.COMPLETED, func.INTEGER())
            ).label("completed"),
            func.sum(
                func.cast(EvolutionJob.status == EvolutionJobStatus.FAILED, func.INTEGER())
            ).label("failed"),
            func.sum(
                func.cast(EvolutionJob.status == EvolutionJobStatus.RUNNING, func.INTEGER())
            ).label("running"),
            func.sum(
                func.cast(EvolutionJob.status == EvolutionJobStatus.QUEUED, func.INTEGER())
            ).label("queued"),
        )
        .select_from(EvolutionJob)
        .join(Playbook, EvolutionJob.playbook_id == Playbook.id)
        .where(
            Playbook.user_id == user_id,
            EvolutionJob.started_at >= start_date,
            EvolutionJob.started_at <= end_date,
        )
        .group_by(date_trunc)
        .order_by(date_trunc)
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        DailyEvolution(
            date=row.date,
            total_evolutions=row.total_evolutions or 0,
            completed=row.completed or 0,
            failed=row.failed or 0,
            running=row.running or 0,
            queued=row.queued or 0,
        )
        for row in rows
    ]


async def get_evolution_by_playbook(
    db: AsyncSession,
    user_id: UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = 10,
) -> list[PlaybookEvolutionStats]:
    """Get evolution statistics grouped by playbook.

    Args:
        db: Database session.
        user_id: User ID to get stats for.
        start_date: Start of period (inclusive). Defaults to 30 days ago.
        end_date: End of period (inclusive). Defaults to now.
        limit: Maximum number of playbooks to return.

    Returns:
        List of PlaybookEvolutionStats, ordered by total evolutions descending.
    """
    if end_date is None:
        end_date = datetime.now(UTC)
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    query = (
        select(
            Playbook.id.label("playbook_id"),
            Playbook.name.label("playbook_name"),
            func.count(EvolutionJob.id).label("total_evolutions"),
            func.sum(
                func.cast(EvolutionJob.status == EvolutionJobStatus.COMPLETED, func.INTEGER())
            ).label("completed"),
            func.sum(
                func.cast(EvolutionJob.status == EvolutionJobStatus.FAILED, func.INTEGER())
            ).label("failed"),
            func.max(EvolutionJob.started_at).label("last_evolution_at"),
        )
        .select_from(Playbook)
        .join(EvolutionJob, Playbook.id == EvolutionJob.playbook_id)
        .where(
            Playbook.user_id == user_id,
            EvolutionJob.started_at >= start_date,
            EvolutionJob.started_at <= end_date,
        )
        .group_by(Playbook.id, Playbook.name)
        .order_by(func.count(EvolutionJob.id).desc())
        .limit(limit)
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        PlaybookEvolutionStats(
            playbook_id=row.playbook_id,
            playbook_name=row.playbook_name,
            total_evolutions=row.total_evolutions or 0,
            completed=row.completed or 0,
            failed=row.failed or 0,
            success_rate=(
                (row.completed / row.total_evolutions) if row.total_evolutions > 0 else 0.0
            ),
            last_evolution_at=row.last_evolution_at,
        )
        for row in rows
    ]


async def get_recent_evolutions(
    db: AsyncSession,
    user_id: UUID,
    limit: int = 10,
) -> list[RecentEvolution]:
    """Get recent evolution runs across all playbooks.

    Args:
        db: Database session.
        user_id: User ID to get evolutions for.
        limit: Maximum number of evolutions to return.

    Returns:
        List of RecentEvolution records, ordered by started_at descending.
    """
    # Subquery to get version numbers
    from_version_subq = (
        select(PlaybookVersion.version_number)
        .where(PlaybookVersion.id == EvolutionJob.from_version_id)
        .scalar_subquery()
    )

    to_version_subq = (
        select(PlaybookVersion.version_number)
        .where(PlaybookVersion.id == EvolutionJob.to_version_id)
        .scalar_subquery()
    )

    query = (
        select(
            EvolutionJob.id,
            EvolutionJob.playbook_id,
            Playbook.name.label("playbook_name"),
            EvolutionJob.status,
            EvolutionJob.outcomes_processed,
            from_version_subq.label("from_version_number"),
            to_version_subq.label("to_version_number"),
            EvolutionJob.started_at,
            EvolutionJob.completed_at,
            EvolutionJob.error_message,
        )
        .select_from(EvolutionJob)
        .join(Playbook, EvolutionJob.playbook_id == Playbook.id)
        .where(Playbook.user_id == user_id)
        .order_by(EvolutionJob.started_at.desc().nullslast())
        .limit(limit)
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        RecentEvolution(
            id=row.id,
            playbook_id=row.playbook_id,
            playbook_name=row.playbook_name,
            status=row.status,
            outcomes_processed=row.outcomes_processed or 0,
            from_version_number=row.from_version_number,
            to_version_number=row.to_version_number,
            started_at=row.started_at,
            completed_at=row.completed_at,
            error_message=row.error_message,
        )
        for row in rows
    ]
