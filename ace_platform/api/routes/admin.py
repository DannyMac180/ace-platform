"""Admin dashboard routes.

Read-only admin endpoints for viewing platform-wide user activity,
subscription distribution, signups over time, and usage data.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.api.auth import AdminUser
from ace_platform.api.deps import get_db
from ace_platform.core.metering import (
    get_platform_daily_summary,
    get_top_users_by_spend,
    get_user_usage_summary,
)
from ace_platform.db.models import AuditLog, Playbook, UsageRecord, User

router = APIRouter(prefix="/admin", tags=["Admin"])


# =============================================================================
# Response Schemas
# =============================================================================


class PlatformStatsResponse(BaseModel):
    """Platform overview statistics."""

    total_users: int
    active_users_today: int
    signups_this_week: int
    total_cost_today: str
    tier_distribution: dict[str, int]


class AdminUserItem(BaseModel):
    """User list item for admin view."""

    id: str
    email: str
    is_active: bool
    email_verified: bool
    is_admin: bool
    subscription_tier: str | None
    subscription_status: str
    playbook_count: int
    total_cost_usd: str
    created_at: datetime


class PaginatedAdminUsersResponse(BaseModel):
    """Paginated admin users response."""

    items: list[AdminUserItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class AdminUserDetailResponse(BaseModel):
    """Detailed user view for admin."""

    id: str
    email: str
    is_active: bool
    is_admin: bool
    email_verified: bool
    subscription_tier: str | None
    subscription_status: str
    has_used_trial: bool
    has_payment_method: bool
    created_at: datetime
    updated_at: datetime
    usage_summary: dict


class DailySignupResponse(BaseModel):
    """Daily signup count."""

    date: str
    count: int


class TopUserResponse(BaseModel):
    """Top user by spend."""

    user_id: str
    email: str
    subscription_tier: str | None
    total_cost_usd: str
    cost_limit_usd: str | None
    percent_of_limit: float | None


class AuditEventItem(BaseModel):
    """Audit event for admin view."""

    id: str
    user_id: str | None
    user_email: str | None
    event_type: str
    severity: str
    ip_address: str | None
    created_at: datetime
    details: dict | None


class PaginatedAuditEventsResponse(BaseModel):
    """Paginated audit events response."""

    items: list[AuditEventItem]
    total: int
    page: int
    page_size: int
    total_pages: int


# =============================================================================
# Routes
# =============================================================================


@router.get(
    "/stats",
    response_model=PlatformStatsResponse,
    summary="Platform overview statistics",
)
async def get_platform_stats(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PlatformStatsResponse:
    """Get platform-wide statistics: total users, signups, tier distribution, cost today."""
    now = datetime.now(UTC)

    # Total users
    total_users = await db.scalar(select(func.count(User.id))) or 0

    # Signups this week
    week_ago = now - timedelta(days=7)
    signups_this_week = (
        await db.scalar(select(func.count(User.id)).where(User.created_at >= week_ago)) or 0
    )

    # Tier distribution
    tier_expr = func.coalesce(User.subscription_tier, "free").label("tier")
    tier_rows = await db.execute(
        select(
            tier_expr,
            func.count(User.id).label("user_count"),
        ).group_by(tier_expr)
    )
    tier_distribution = {row.tier: row.user_count for row in tier_rows}

    # Platform daily summary (active users + cost today)
    daily_summary = await get_platform_daily_summary(db, now)

    return PlatformStatsResponse(
        total_users=total_users,
        active_users_today=daily_summary.total_users_active,
        signups_this_week=signups_this_week,
        total_cost_today=str(daily_summary.total_cost_usd),
        tier_distribution=tier_distribution,
    )


@router.get(
    "/users",
    response_model=PaginatedAdminUsersResponse,
    summary="List all users with search and filter",
)
async def list_users(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: str | None = Query(None, description="Search by email"),
    tier: str | None = Query(None, description="Filter by subscription tier"),
) -> PaginatedAdminUsersResponse:
    """Paginated user list with search and tier filter."""
    # Base query with playbook count subquery
    playbook_count_sq = (
        select(
            Playbook.user_id,
            func.count(Playbook.id).label("playbook_count"),
        )
        .group_by(Playbook.user_id)
        .subquery()
    )

    # Cost subquery (current month)
    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    cost_sq = (
        select(
            UsageRecord.user_id,
            func.coalesce(func.sum(UsageRecord.cost_usd), Decimal("0")).label("total_cost"),
        )
        .where(UsageRecord.created_at >= month_start)
        .group_by(UsageRecord.user_id)
        .subquery()
    )

    base_query = (
        select(
            User,
            func.coalesce(playbook_count_sq.c.playbook_count, 0).label("playbook_count"),
            func.coalesce(cost_sq.c.total_cost, Decimal("0")).label("total_cost"),
        )
        .outerjoin(playbook_count_sq, User.id == playbook_count_sq.c.user_id)
        .outerjoin(cost_sq, User.id == cost_sq.c.user_id)
    )

    if search:
        base_query = base_query.where(User.email.ilike(f"%{search}%"))

    if tier:
        if tier == "free":
            base_query = base_query.where(User.subscription_tier.is_(None))
        else:
            base_query = base_query.where(User.subscription_tier == tier)

    # Count total
    count_query = select(func.count()).select_from(base_query.with_only_columns(User.id).subquery())
    total = await db.scalar(count_query) or 0

    # Fetch page
    offset = (page - 1) * page_size
    results = await db.execute(
        base_query.order_by(User.created_at.desc()).offset(offset).limit(page_size)
    )
    rows = results.all()

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    items = [
        AdminUserItem(
            id=str(row.User.id),
            email=row.User.email,
            is_active=row.User.is_active,
            email_verified=row.User.email_verified,
            is_admin=row.User.is_admin,
            subscription_tier=row.User.subscription_tier,
            subscription_status=row.User.subscription_status.value,
            playbook_count=row.playbook_count,
            total_cost_usd=str(row.total_cost),
            created_at=row.User.created_at,
        )
        for row in rows
    ]

    return PaginatedAdminUsersResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/users/{user_id}",
    response_model=AdminUserDetailResponse,
    summary="Get detailed user information",
)
async def get_user_detail(
    user_id: UUID,
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminUserDetailResponse:
    """Get full user detail with usage summary."""
    from fastapi import HTTPException, status

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Get usage summary from metering
    usage = await get_user_usage_summary(db, user_id)

    return AdminUserDetailResponse(
        id=str(user.id),
        email=user.email,
        is_active=user.is_active,
        is_admin=user.is_admin,
        email_verified=user.email_verified,
        subscription_tier=user.subscription_tier,
        subscription_status=user.subscription_status.value,
        has_used_trial=user.has_used_trial,
        has_payment_method=user.has_payment_method,
        created_at=user.created_at,
        updated_at=user.updated_at,
        usage_summary={
            "total_requests": usage.total_requests,
            "total_tokens": usage.total_tokens,
            "total_cost_usd": str(usage.total_cost_usd),
            "start_date": usage.start_date.isoformat(),
            "end_date": usage.end_date.isoformat(),
        },
    )


@router.get(
    "/signups",
    response_model=list[DailySignupResponse],
    summary="Daily signup counts",
)
async def get_signups(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(30, ge=1, le=365),
) -> list[DailySignupResponse]:
    """Get daily signup counts for charting."""
    now = datetime.now(UTC)
    start = now - timedelta(days=days)

    date_trunc = func.date_trunc("day", User.created_at)
    results = await db.execute(
        select(
            date_trunc.label("signup_date"),
            func.count(User.id).label("signup_count"),
        )
        .where(User.created_at >= start)
        .group_by(date_trunc)
        .order_by(date_trunc)
    )

    return [
        DailySignupResponse(
            date=row.signup_date.strftime("%Y-%m-%d"),
            count=row.signup_count,
        )
        for row in results
    ]


@router.get(
    "/top-users",
    response_model=list[TopUserResponse],
    summary="Top users by spend",
)
async def get_top_users(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(10, ge=1, le=100),
) -> list[TopUserResponse]:
    """Get top users by spend this month."""
    summaries = await get_top_users_by_spend(db, limit=limit)

    return [
        TopUserResponse(
            user_id=str(s.user_id),
            email=s.email,
            subscription_tier=s.subscription_tier,
            total_cost_usd=str(s.total_cost_usd),
            cost_limit_usd=str(s.cost_limit_usd) if s.cost_limit_usd else None,
            percent_of_limit=s.percent_of_limit,
        )
        for s in summaries
    ]


@router.get(
    "/audit-events",
    response_model=PaginatedAuditEventsResponse,
    summary="Platform-wide audit events",
)
async def get_audit_events(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> PaginatedAuditEventsResponse:
    """Get platform-wide audit log (not filtered by user)."""
    base_query = select(AuditLog, User.email.label("user_email")).outerjoin(
        User, AuditLog.user_id == User.id
    )

    count_query = select(func.count(AuditLog.id))
    total = await db.scalar(count_query) or 0

    offset = (page - 1) * page_size
    results = await db.execute(
        base_query.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size)
    )
    rows = results.all()

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    items = [
        AuditEventItem(
            id=str(row.AuditLog.id),
            user_id=str(row.AuditLog.user_id) if row.AuditLog.user_id else None,
            user_email=row.user_email,
            event_type=row.AuditLog.event_type.value,
            severity=row.AuditLog.severity.value,
            ip_address=row.AuditLog.ip_address,
            created_at=row.AuditLog.created_at,
            details=row.AuditLog.details,
        )
        for row in rows
    ]

    return PaginatedAuditEventsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
