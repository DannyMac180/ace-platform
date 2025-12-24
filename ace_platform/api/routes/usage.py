"""Usage reporting API routes.

This module provides REST API endpoints for usage reporting:
- GET /usage/summary - Get usage summary for the current user
- GET /usage/daily - Get daily usage breakdown
- GET /usage/by-playbook - Get usage grouped by playbook
- GET /usage/by-operation - Get usage grouped by operation
- GET /usage/by-model - Get usage grouped by model
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.api.auth import require_user
from ace_platform.api.deps import get_db
from ace_platform.core.metering import (
    get_usage_by_model,
    get_usage_by_operation,
    get_usage_by_playbook,
    get_user_usage_by_day,
    get_user_usage_summary,
)
from ace_platform.db.models import User

router = APIRouter(prefix="/usage", tags=["usage"])


# Pydantic Schemas


class UsageSummaryResponse(BaseModel):
    """Response schema for usage summary."""

    start_date: datetime
    end_date: datetime
    total_requests: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost_usd: Decimal

    model_config = {"from_attributes": True}


class DailyUsageResponse(BaseModel):
    """Response schema for daily usage."""

    date: datetime
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: Decimal

    model_config = {"from_attributes": True}


class PlaybookUsageResponse(BaseModel):
    """Response schema for usage by playbook."""

    playbook_id: UUID | None
    playbook_name: str | None
    request_count: int
    total_tokens: int
    cost_usd: Decimal

    model_config = {"from_attributes": True}


class OperationUsageResponse(BaseModel):
    """Response schema for usage by operation."""

    operation: str
    request_count: int
    total_tokens: int
    cost_usd: Decimal

    model_config = {"from_attributes": True}


class ModelUsageResponse(BaseModel):
    """Response schema for usage by model."""

    model: str
    request_count: int
    total_tokens: int
    cost_usd: Decimal


# Dependency type aliases
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(require_user)]


# Route handlers


@router.get("/summary", response_model=UsageSummaryResponse)
async def get_usage_summary(
    db: DbSession,
    current_user: CurrentUser,
    start_date: datetime | None = Query(None, description="Start date (defaults to 30 days ago)"),
    end_date: datetime | None = Query(None, description="End date (defaults to now)"),
) -> UsageSummaryResponse:
    """Get usage summary for the authenticated user.

    Returns aggregated usage totals for the specified time period.
    Defaults to the last 30 days if no dates specified.
    """
    summary = await get_user_usage_summary(db, current_user.id, start_date, end_date)

    return UsageSummaryResponse(
        start_date=summary.start_date,
        end_date=summary.end_date,
        total_requests=summary.total_requests,
        total_prompt_tokens=summary.total_prompt_tokens,
        total_completion_tokens=summary.total_completion_tokens,
        total_tokens=summary.total_tokens,
        total_cost_usd=summary.total_cost_usd,
    )


@router.get("/daily", response_model=list[DailyUsageResponse])
async def get_daily_usage(
    db: DbSession,
    current_user: CurrentUser,
    start_date: datetime | None = Query(None, description="Start date (defaults to 30 days ago)"),
    end_date: datetime | None = Query(None, description="End date (defaults to now)"),
) -> list[DailyUsageResponse]:
    """Get daily usage breakdown for the authenticated user.

    Returns usage data grouped by day, ordered by date ascending.
    Defaults to the last 30 days if no dates specified.
    """
    daily = await get_user_usage_by_day(db, current_user.id, start_date, end_date)

    return [
        DailyUsageResponse(
            date=d.date,
            request_count=d.request_count,
            prompt_tokens=d.prompt_tokens,
            completion_tokens=d.completion_tokens,
            total_tokens=d.total_tokens,
            cost_usd=d.cost_usd,
        )
        for d in daily
    ]


@router.get("/by-playbook", response_model=list[PlaybookUsageResponse])
async def get_usage_grouped_by_playbook(
    db: DbSession,
    current_user: CurrentUser,
    start_date: datetime | None = Query(None, description="Start date (defaults to 30 days ago)"),
    end_date: datetime | None = Query(None, description="End date (defaults to now)"),
) -> list[PlaybookUsageResponse]:
    """Get usage grouped by playbook.

    Returns usage data grouped by playbook, ordered by cost descending.
    Defaults to the last 30 days if no dates specified.
    """
    by_playbook = await get_usage_by_playbook(db, current_user.id, start_date, end_date)

    return [
        PlaybookUsageResponse(
            playbook_id=p.playbook_id,
            playbook_name=p.playbook_name,
            request_count=p.request_count,
            total_tokens=p.total_tokens,
            cost_usd=p.cost_usd,
        )
        for p in by_playbook
    ]


@router.get("/by-operation", response_model=list[OperationUsageResponse])
async def get_usage_grouped_by_operation(
    db: DbSession,
    current_user: CurrentUser,
    start_date: datetime | None = Query(None, description="Start date (defaults to 30 days ago)"),
    end_date: datetime | None = Query(None, description="End date (defaults to now)"),
) -> list[OperationUsageResponse]:
    """Get usage grouped by operation type.

    Returns usage data grouped by operation (e.g., evolution_generator,
    evolution_reflector, evolution_curator), ordered by cost descending.
    Defaults to the last 30 days if no dates specified.
    """
    by_operation = await get_usage_by_operation(db, current_user.id, start_date, end_date)

    return [
        OperationUsageResponse(
            operation=o.operation,
            request_count=o.request_count,
            total_tokens=o.total_tokens,
            cost_usd=o.cost_usd,
        )
        for o in by_operation
    ]


@router.get("/by-model", response_model=list[ModelUsageResponse])
async def get_usage_grouped_by_model(
    db: DbSession,
    current_user: CurrentUser,
    start_date: datetime | None = Query(None, description="Start date (defaults to 30 days ago)"),
    end_date: datetime | None = Query(None, description="End date (defaults to now)"),
) -> list[ModelUsageResponse]:
    """Get usage grouped by model.

    Returns usage data grouped by model (e.g., gpt-4o, gpt-4o-mini),
    ordered by cost descending.
    Defaults to the last 30 days if no dates specified.
    """
    by_model = await get_usage_by_model(db, current_user.id, start_date, end_date)

    return [
        ModelUsageResponse(
            model=m["model"],
            request_count=m["request_count"],
            total_tokens=m["total_tokens"],
            cost_usd=m["cost_usd"],
        )
        for m in by_model
    ]
