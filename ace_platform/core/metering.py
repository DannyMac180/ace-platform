"""Usage metering and aggregation for billing.

This module provides functions to aggregate usage records for billing
and analytics purposes. It works with UsageRecord data logged by the
MeteredLLMClient in llm_proxy.py.

Key functions:
- get_user_usage_summary: Get total usage for a user in a time period
- get_user_usage_by_day: Get daily usage breakdown
- get_usage_by_playbook: Get usage grouped by playbook
- get_usage_by_operation: Get usage grouped by operation type
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.db.models import Playbook, UsageRecord


@dataclass
class UsageSummary:
    """Summary of usage for a time period."""

    user_id: UUID
    start_date: datetime
    end_date: datetime
    total_requests: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost_usd: Decimal


@dataclass
class DailyUsage:
    """Usage for a single day."""

    date: datetime
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: Decimal


@dataclass
class PlaybookUsage:
    """Usage grouped by playbook."""

    playbook_id: UUID | None
    playbook_name: str | None
    request_count: int
    total_tokens: int
    cost_usd: Decimal


@dataclass
class OperationUsage:
    """Usage grouped by operation type."""

    operation: str
    request_count: int
    total_tokens: int
    cost_usd: Decimal


async def get_user_usage_summary(
    db: AsyncSession,
    user_id: UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> UsageSummary:
    """Get aggregated usage summary for a user.

    Args:
        db: Database session.
        user_id: User ID to get usage for.
        start_date: Start of period (inclusive). Defaults to 30 days ago.
        end_date: End of period (inclusive). Defaults to now.

    Returns:
        UsageSummary with aggregated totals.
    """
    if end_date is None:
        end_date = datetime.now(UTC)
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    query = select(
        func.count(UsageRecord.id).label("total_requests"),
        func.coalesce(func.sum(UsageRecord.prompt_tokens), 0).label("total_prompt_tokens"),
        func.coalesce(func.sum(UsageRecord.completion_tokens), 0).label("total_completion_tokens"),
        func.coalesce(func.sum(UsageRecord.total_tokens), 0).label("total_tokens"),
        func.coalesce(func.sum(UsageRecord.cost_usd), Decimal("0")).label("total_cost_usd"),
    ).where(
        UsageRecord.user_id == user_id,
        UsageRecord.created_at >= start_date,
        UsageRecord.created_at <= end_date,
    )

    result = await db.execute(query)
    row = result.one()

    return UsageSummary(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        total_requests=row.total_requests,
        total_prompt_tokens=row.total_prompt_tokens,
        total_completion_tokens=row.total_completion_tokens,
        total_tokens=row.total_tokens,
        total_cost_usd=row.total_cost_usd,
    )


async def get_user_usage_by_day(
    db: AsyncSession,
    user_id: UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[DailyUsage]:
    """Get daily usage breakdown for a user.

    Args:
        db: Database session.
        user_id: User ID to get usage for.
        start_date: Start of period (inclusive). Defaults to 30 days ago.
        end_date: End of period (inclusive). Defaults to now.

    Returns:
        List of DailyUsage records, ordered by date ascending.
    """
    if end_date is None:
        end_date = datetime.now(UTC)
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    # Group by date (truncate to day)
    date_trunc = func.date_trunc("day", UsageRecord.created_at)

    query = (
        select(
            date_trunc.label("date"),
            func.count(UsageRecord.id).label("request_count"),
            func.sum(UsageRecord.prompt_tokens).label("prompt_tokens"),
            func.sum(UsageRecord.completion_tokens).label("completion_tokens"),
            func.sum(UsageRecord.total_tokens).label("total_tokens"),
            func.sum(UsageRecord.cost_usd).label("cost_usd"),
        )
        .where(
            UsageRecord.user_id == user_id,
            UsageRecord.created_at >= start_date,
            UsageRecord.created_at <= end_date,
        )
        .group_by(date_trunc)
        .order_by(date_trunc)
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        DailyUsage(
            date=row.date,
            request_count=row.request_count,
            prompt_tokens=row.prompt_tokens or 0,
            completion_tokens=row.completion_tokens or 0,
            total_tokens=row.total_tokens or 0,
            cost_usd=row.cost_usd or Decimal("0"),
        )
        for row in rows
    ]


async def get_usage_by_playbook(
    db: AsyncSession,
    user_id: UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[PlaybookUsage]:
    """Get usage grouped by playbook.

    Args:
        db: Database session.
        user_id: User ID to get usage for.
        start_date: Start of period (inclusive). Defaults to 30 days ago.
        end_date: End of period (inclusive). Defaults to now.

    Returns:
        List of PlaybookUsage records, ordered by cost descending.
    """
    if end_date is None:
        end_date = datetime.now(UTC)
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    query = (
        select(
            UsageRecord.playbook_id,
            Playbook.name.label("playbook_name"),
            func.count(UsageRecord.id).label("request_count"),
            func.sum(UsageRecord.total_tokens).label("total_tokens"),
            func.sum(UsageRecord.cost_usd).label("cost_usd"),
        )
        .outerjoin(Playbook, UsageRecord.playbook_id == Playbook.id)
        .where(
            UsageRecord.user_id == user_id,
            UsageRecord.created_at >= start_date,
            UsageRecord.created_at <= end_date,
        )
        .group_by(UsageRecord.playbook_id, Playbook.name)
        .order_by(func.sum(UsageRecord.cost_usd).desc())
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        PlaybookUsage(
            playbook_id=row.playbook_id,
            playbook_name=row.playbook_name,
            request_count=row.request_count,
            total_tokens=row.total_tokens or 0,
            cost_usd=row.cost_usd or Decimal("0"),
        )
        for row in rows
    ]


async def get_usage_by_operation(
    db: AsyncSession,
    user_id: UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[OperationUsage]:
    """Get usage grouped by operation type.

    Args:
        db: Database session.
        user_id: User ID to get usage for.
        start_date: Start of period (inclusive). Defaults to 30 days ago.
        end_date: End of period (inclusive). Defaults to now.

    Returns:
        List of OperationUsage records, ordered by cost descending.
    """
    if end_date is None:
        end_date = datetime.now(UTC)
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    query = (
        select(
            UsageRecord.operation,
            func.count(UsageRecord.id).label("request_count"),
            func.sum(UsageRecord.total_tokens).label("total_tokens"),
            func.sum(UsageRecord.cost_usd).label("cost_usd"),
        )
        .where(
            UsageRecord.user_id == user_id,
            UsageRecord.created_at >= start_date,
            UsageRecord.created_at <= end_date,
        )
        .group_by(UsageRecord.operation)
        .order_by(func.sum(UsageRecord.cost_usd).desc())
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        OperationUsage(
            operation=row.operation,
            request_count=row.request_count,
            total_tokens=row.total_tokens or 0,
            cost_usd=row.cost_usd or Decimal("0"),
        )
        for row in rows
    ]


async def get_usage_by_model(
    db: AsyncSession,
    user_id: UUID,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[dict]:
    """Get usage grouped by model.

    Args:
        db: Database session.
        user_id: User ID to get usage for.
        start_date: Start of period (inclusive). Defaults to 30 days ago.
        end_date: End of period (inclusive). Defaults to now.

    Returns:
        List of dicts with model, request_count, total_tokens, cost_usd.
    """
    if end_date is None:
        end_date = datetime.now(UTC)
    if start_date is None:
        start_date = end_date - timedelta(days=30)

    query = (
        select(
            UsageRecord.model,
            func.count(UsageRecord.id).label("request_count"),
            func.sum(UsageRecord.total_tokens).label("total_tokens"),
            func.sum(UsageRecord.cost_usd).label("cost_usd"),
        )
        .where(
            UsageRecord.user_id == user_id,
            UsageRecord.created_at >= start_date,
            UsageRecord.created_at <= end_date,
        )
        .group_by(UsageRecord.model)
        .order_by(func.sum(UsageRecord.cost_usd).desc())
    )

    result = await db.execute(query)
    rows = result.all()

    return [
        {
            "model": row.model,
            "request_count": row.request_count,
            "total_tokens": row.total_tokens or 0,
            "cost_usd": row.cost_usd or Decimal("0"),
        }
        for row in rows
    ]


async def get_billing_period_usage(
    db: AsyncSession,
    user_id: UUID,
    billing_period_start: datetime,
    billing_period_end: datetime,
) -> dict:
    """Get comprehensive usage data for a billing period.

    This is a convenience function that returns all usage data needed
    for generating a billing invoice or usage report.

    Args:
        db: Database session.
        user_id: User ID to get usage for.
        billing_period_start: Start of billing period.
        billing_period_end: End of billing period.

    Returns:
        Dict with summary, daily breakdown, and grouped usage data.
    """
    summary = await get_user_usage_summary(db, user_id, billing_period_start, billing_period_end)
    daily = await get_user_usage_by_day(db, user_id, billing_period_start, billing_period_end)
    by_playbook = await get_usage_by_playbook(db, user_id, billing_period_start, billing_period_end)
    by_operation = await get_usage_by_operation(
        db, user_id, billing_period_start, billing_period_end
    )
    by_model = await get_usage_by_model(db, user_id, billing_period_start, billing_period_end)

    return {
        "summary": summary,
        "daily": daily,
        "by_playbook": by_playbook,
        "by_operation": by_operation,
        "by_model": by_model,
    }
