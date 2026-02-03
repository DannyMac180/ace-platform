"""Evolution statistics API routes.

This module provides REST API endpoints for evolution statistics:
- GET /evolutions/summary - Get aggregate evolution statistics
- GET /evolutions/daily - Get daily evolution breakdown
- GET /evolutions/by-playbook - Get evolution stats grouped by playbook
- GET /evolutions/recent - Get recent evolution runs
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.api.auth import require_paid_access
from ace_platform.api.deps import get_db
from ace_platform.core.evolution_stats import (
    get_evolution_by_day,
    get_evolution_by_playbook,
    get_evolution_summary,
    get_recent_evolutions,
)
from ace_platform.db.models import EvolutionJobStatus, User

router = APIRouter(prefix="/evolutions", tags=["evolutions"])


# Pydantic Schemas


class EvolutionSummaryResponse(BaseModel):
    """Response schema for evolution summary."""

    start_date: datetime
    end_date: datetime
    total_evolutions: int
    completed_evolutions: int
    failed_evolutions: int
    running_evolutions: int
    queued_evolutions: int
    success_rate: float
    total_outcomes_processed: int

    model_config = {"from_attributes": True}


class DailyEvolutionResponse(BaseModel):
    """Response schema for daily evolution breakdown."""

    date: datetime
    total_evolutions: int
    completed: int
    failed: int
    running: int
    queued: int

    model_config = {"from_attributes": True}


class PlaybookEvolutionStatsResponse(BaseModel):
    """Response schema for playbook evolution statistics."""

    playbook_id: UUID
    playbook_name: str
    total_evolutions: int
    completed: int
    failed: int
    success_rate: float
    last_evolution_at: datetime | None

    model_config = {"from_attributes": True}


class RecentEvolutionResponse(BaseModel):
    """Response schema for recent evolution runs."""

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

    model_config = {"from_attributes": True}


# Dependency type aliases
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(require_paid_access)]


# Route handlers


@router.get("/summary", response_model=EvolutionSummaryResponse)
async def get_evolution_summary_endpoint(
    db: DbSession,
    current_user: CurrentUser,
    start_date: datetime | None = Query(None, description="Start date (defaults to 30 days ago)"),
    end_date: datetime | None = Query(None, description="End date (defaults to now)"),
) -> EvolutionSummaryResponse:
    """Get aggregate evolution statistics for the authenticated user.

    Returns total evolutions, success/failure counts, and success rate
    for the specified time period. Defaults to the last 30 days.
    """
    summary = await get_evolution_summary(db, current_user.id, start_date, end_date)

    return EvolutionSummaryResponse(
        start_date=summary.start_date,
        end_date=summary.end_date,
        total_evolutions=summary.total_evolutions,
        completed_evolutions=summary.completed_evolutions,
        failed_evolutions=summary.failed_evolutions,
        running_evolutions=summary.running_evolutions,
        queued_evolutions=summary.queued_evolutions,
        success_rate=summary.success_rate,
        total_outcomes_processed=summary.total_outcomes_processed,
    )


@router.get("/daily", response_model=list[DailyEvolutionResponse])
async def get_daily_evolution_endpoint(
    db: DbSession,
    current_user: CurrentUser,
    start_date: datetime | None = Query(None, description="Start date (defaults to 30 days ago)"),
    end_date: datetime | None = Query(None, description="End date (defaults to now)"),
) -> list[DailyEvolutionResponse]:
    """Get daily evolution breakdown for the authenticated user.

    Returns evolution counts grouped by day, ordered by date ascending.
    Defaults to the last 30 days if no dates specified.
    """
    daily = await get_evolution_by_day(db, current_user.id, start_date, end_date)

    return [
        DailyEvolutionResponse(
            date=d.date,
            total_evolutions=d.total_evolutions,
            completed=d.completed,
            failed=d.failed,
            running=d.running,
            queued=d.queued,
        )
        for d in daily
    ]


@router.get("/by-playbook", response_model=list[PlaybookEvolutionStatsResponse])
async def get_evolution_by_playbook_endpoint(
    db: DbSession,
    current_user: CurrentUser,
    start_date: datetime | None = Query(None, description="Start date (defaults to 30 days ago)"),
    end_date: datetime | None = Query(None, description="End date (defaults to now)"),
    limit: int = Query(10, ge=1, le=50, description="Maximum number of playbooks to return"),
) -> list[PlaybookEvolutionStatsResponse]:
    """Get evolution statistics grouped by playbook.

    Returns evolution counts and success rates for each playbook,
    ordered by total evolutions descending. Defaults to the last 30 days.
    """
    by_playbook = await get_evolution_by_playbook(db, current_user.id, start_date, end_date, limit)

    return [
        PlaybookEvolutionStatsResponse(
            playbook_id=p.playbook_id,
            playbook_name=p.playbook_name,
            total_evolutions=p.total_evolutions,
            completed=p.completed,
            failed=p.failed,
            success_rate=p.success_rate,
            last_evolution_at=p.last_evolution_at,
        )
        for p in by_playbook
    ]


@router.get("/recent", response_model=list[RecentEvolutionResponse])
async def get_recent_evolutions_endpoint(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(10, ge=1, le=50, description="Maximum number of evolutions to return"),
) -> list[RecentEvolutionResponse]:
    """Get recent evolution runs across all playbooks.

    Returns the most recent evolution runs for the authenticated user,
    ordered by start time descending.
    """
    recent = await get_recent_evolutions(db, current_user.id, limit)

    return [
        RecentEvolutionResponse(
            id=r.id,
            playbook_id=r.playbook_id,
            playbook_name=r.playbook_name,
            status=r.status,
            outcomes_processed=r.outcomes_processed,
            from_version_number=r.from_version_number,
            to_version_number=r.to_version_number,
            started_at=r.started_at,
            completed_at=r.completed_at,
            error_message=r.error_message,
        )
        for r in recent
    ]
