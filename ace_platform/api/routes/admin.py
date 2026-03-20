"""Admin dashboard routes.

Includes platform analytics plus hosted-personal backup/restore tooling.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.api.auth import AdminUser
from ace_platform.api.deps import get_db
from ace_platform.config import get_settings
from ace_platform.core import workspace_backups as workspace_backup_service
from ace_platform.core.managed_inference import MANAGED_INFERENCE_OPERATION
from ace_platform.core.metering import (
    get_platform_daily_summary,
    get_top_users_by_spend,
    get_user_usage_summary,
)
from ace_platform.db.models import (
    AcquisitionEvent,
    AcquisitionEventType,
    AuditLog,
    EvolutionJob,
    EvolutionJobStatus,
    Membership,
    Playbook,
    SubscriptionStatus,
    UsageRecord,
    User,
    Workspace,
    WorkspaceDeploymentMode,
    WorkspaceEntitlement,
    WorkspacePlan,
    WorkspaceSyncTombstone,
)

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


class SyncHealthResponse(BaseModel):
    """Hosted sync rollout health snapshot."""

    status: str
    enabled_workspaces: int
    active_workspaces_24h: int
    sync_events_24h: int
    last_activity_at: datetime | None


class JobQueueHealthResponse(BaseModel):
    """Hosted job queue health snapshot."""

    status: str
    queued_jobs: int
    running_jobs: int
    failed_jobs_24h: int
    jobs_observed_24h: int
    oldest_queued_at: datetime | None
    last_completed_at: datetime | None


class InferenceGatewayHealthResponse(BaseModel):
    """Managed inference rollout health snapshot."""

    status: str
    enabled_workspaces: int
    configured_providers: list[str]
    requests_24h: int
    total_tokens_24h: int
    total_cost_usd_24h: str
    last_request_at: datetime | None


class OperationalHealthResponse(BaseModel):
    """Cloud operational health surfaces for rollout monitoring."""

    generated_at: datetime
    sync: SyncHealthResponse
    job_queue: JobQueueHealthResponse
    inference_gateway: InferenceGatewayHealthResponse


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


class ConversionFunnelResponse(BaseModel):
    """Signup to paid conversion funnel."""

    days: int
    start_date: datetime
    end_date: datetime
    landing_views: int
    register_starts: int
    register_completes: int
    signups: int
    trial_checkout_intent: int
    trial_started: int
    first_playbook_created: int
    paid_active_non_trial: int
    conversion_landing_to_register_start_pct: float
    conversion_register_start_to_register_complete_pct: float
    conversion_landing_to_register_complete_pct: float
    conversion_signup_to_checkout_intent_pct: float
    conversion_checkout_intent_to_trial_started_pct: float
    conversion_trial_started_to_first_playbook_pct: float
    conversion_first_playbook_to_paid_active_non_trial_pct: float
    conversion_signup_to_trial_started_pct: float
    conversion_signup_to_paid_active_non_trial_pct: float


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


class WorkspaceBackupItem(BaseModel):
    """Admin-visible metadata for one hosted workspace backup."""

    id: str
    workspace_id: str
    owner_user_id: str | None
    trigger_source: str
    created_at: datetime
    restored_at: datetime | None
    backup_size_bytes: int
    playbook_count: int


class WorkspaceBackupRestoreResponse(BaseModel):
    """Response returned after a hosted workspace restore."""

    backup_id: str
    workspace_id: str
    restored_playbooks: int
    restored_usage_records: int
    restored_api_keys: int
    restored_oauth_accounts: int


# =============================================================================
# Routes
# =============================================================================


def _conversion_pct(source_count: int, target_count: int) -> float:
    """Calculate a conversion percentage with divide-by-zero safety."""
    if source_count <= 0:
        return 0.0
    return round((target_count / source_count) * 100, 2)


def _sync_health_status(
    *,
    enabled_workspaces: int,
    active_workspaces_24h: int,
    last_activity_at: datetime | None,
    now: datetime,
) -> str:
    """Classify sync rollout health from recent hosted sync activity."""
    if enabled_workspaces == 0:
        return "idle"
    if last_activity_at is None or active_workspaces_24h == 0:
        return "attention"
    if last_activity_at < now - timedelta(days=1):
        return "attention"
    return "healthy"


def _job_queue_health_status(
    *,
    queued_jobs: int,
    running_jobs: int,
    failed_jobs_24h: int,
    oldest_queued_at: datetime | None,
    now: datetime,
) -> str:
    """Classify queue health from backlog and recent failures."""
    if queued_jobs == 0 and running_jobs == 0 and failed_jobs_24h == 0:
        return "idle"
    if failed_jobs_24h > 0:
        return "attention"
    if oldest_queued_at is not None and oldest_queued_at < now - timedelta(minutes=15):
        return "degraded"
    if queued_jobs > 0:
        return "attention"
    return "healthy"


def _inference_gateway_health_status(
    *,
    enabled_workspaces: int,
    configured_providers: list[str],
    requests_24h: int,
) -> str:
    """Classify inference gateway health from readiness and recent traffic."""
    if not configured_providers:
        return "degraded" if enabled_workspaces > 0 else "idle"
    if requests_24h == 0:
        return "idle"
    return "healthy"


async def get_sync_health_snapshot(
    db: AsyncSession,
    *,
    now: datetime,
) -> SyncHealthResponse:
    """Summarize hosted cloud-sync rollout activity for the admin dashboard."""
    window_start = now - timedelta(days=1)
    workspace_rows = (
        await db.execute(
            select(Workspace.id, Membership.user_id)
            .join(WorkspaceEntitlement, WorkspaceEntitlement.workspace_id == Workspace.id)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .where(
                Workspace.plan == WorkspacePlan.PERSONAL,
                Workspace.deployment_mode == WorkspaceDeploymentMode.CLOUD,
                WorkspaceEntitlement.cloud_sync.is_(True),
            )
        )
    ).all()

    workspace_ids = {row.id for row in workspace_rows}
    user_to_workspaces: dict[UUID, set[UUID]] = {}
    for row in workspace_rows:
        user_to_workspaces.setdefault(row.user_id, set()).add(row.id)

    playbook_rows = []
    if user_to_workspaces:
        playbook_rows = (
            await db.execute(
                select(
                    Playbook.user_id,
                    func.count(Playbook.id).label("event_count"),
                    func.max(Playbook.updated_at).label("last_activity_at"),
                )
                .where(
                    Playbook.user_id.in_(list(user_to_workspaces.keys())),
                    Playbook.updated_at >= window_start,
                )
                .group_by(Playbook.user_id)
            )
        ).all()

    tombstone_rows = []
    if workspace_ids:
        tombstone_rows = (
            await db.execute(
                select(
                    WorkspaceSyncTombstone.workspace_id,
                    func.count(WorkspaceSyncTombstone.entity_id).label("event_count"),
                    func.max(WorkspaceSyncTombstone.deleted_at).label("last_activity_at"),
                )
                .where(
                    WorkspaceSyncTombstone.workspace_id.in_(list(workspace_ids)),
                    WorkspaceSyncTombstone.deleted_at >= window_start,
                )
                .group_by(WorkspaceSyncTombstone.workspace_id)
            )
        ).all()

    active_workspace_ids: set[UUID] = set()
    for row in playbook_rows:
        active_workspace_ids.update(user_to_workspaces.get(row.user_id, set()))
    active_workspace_ids.update(row.workspace_id for row in tombstone_rows)

    last_activity_at = None
    activity_candidates = [
        row.last_activity_at for row in playbook_rows if row.last_activity_at is not None
    ]
    activity_candidates.extend(
        row.last_activity_at for row in tombstone_rows if row.last_activity_at is not None
    )
    if activity_candidates:
        last_activity_at = max(activity_candidates)

    sync_events_24h = sum(int(row.event_count or 0) for row in playbook_rows)
    sync_events_24h += sum(int(row.event_count or 0) for row in tombstone_rows)

    return SyncHealthResponse(
        status=_sync_health_status(
            enabled_workspaces=len(workspace_ids),
            active_workspaces_24h=len(active_workspace_ids),
            last_activity_at=last_activity_at,
            now=now,
        ),
        enabled_workspaces=len(workspace_ids),
        active_workspaces_24h=len(active_workspace_ids),
        sync_events_24h=sync_events_24h,
        last_activity_at=last_activity_at,
    )


async def get_job_queue_health_snapshot(
    db: AsyncSession,
    *,
    now: datetime,
) -> JobQueueHealthResponse:
    """Summarize hosted background queue activity for the admin dashboard."""
    window_start = now - timedelta(days=1)
    completion_at = func.coalesce(
        EvolutionJob.completed_at, EvolutionJob.started_at, EvolutionJob.created_at
    )

    row = (
        await db.execute(
            select(
                func.count(EvolutionJob.id)
                .filter(EvolutionJob.status == EvolutionJobStatus.QUEUED)
                .label("queued_jobs"),
                func.count(EvolutionJob.id)
                .filter(EvolutionJob.status == EvolutionJobStatus.RUNNING)
                .label("running_jobs"),
                func.count(EvolutionJob.id)
                .filter(
                    EvolutionJob.status == EvolutionJobStatus.FAILED,
                    completion_at >= window_start,
                )
                .label("failed_jobs_24h"),
                func.count(EvolutionJob.id)
                .filter(completion_at >= window_start)
                .label("jobs_observed_24h"),
                func.min(EvolutionJob.created_at)
                .filter(EvolutionJob.status == EvolutionJobStatus.QUEUED)
                .label("oldest_queued_at"),
                func.max(EvolutionJob.completed_at)
                .filter(EvolutionJob.status == EvolutionJobStatus.COMPLETED)
                .label("last_completed_at"),
            )
        )
    ).one()

    queued_jobs = int(row.queued_jobs or 0)
    running_jobs = int(row.running_jobs or 0)
    failed_jobs_24h = int(row.failed_jobs_24h or 0)

    return JobQueueHealthResponse(
        status=_job_queue_health_status(
            queued_jobs=queued_jobs,
            running_jobs=running_jobs,
            failed_jobs_24h=failed_jobs_24h,
            oldest_queued_at=row.oldest_queued_at,
            now=now,
        ),
        queued_jobs=queued_jobs,
        running_jobs=running_jobs,
        failed_jobs_24h=failed_jobs_24h,
        jobs_observed_24h=int(row.jobs_observed_24h or 0),
        oldest_queued_at=row.oldest_queued_at,
        last_completed_at=row.last_completed_at,
    )


async def get_inference_gateway_health_snapshot(
    db: AsyncSession,
    *,
    now: datetime,
) -> InferenceGatewayHealthResponse:
    """Summarize managed inference readiness and recent usage."""
    window_start = now - timedelta(days=1)
    settings = get_settings()
    configured_providers = []
    if settings.openai_api_key:
        configured_providers.append("openai")
    if settings.anthropic_api_key:
        configured_providers.append("anthropic")

    enabled_workspaces = (
        await db.scalar(
            select(func.count(Workspace.id))
            .join(WorkspaceEntitlement, WorkspaceEntitlement.workspace_id == Workspace.id)
            .where(
                Workspace.deployment_mode == WorkspaceDeploymentMode.CLOUD,
                WorkspaceEntitlement.managed_inference.is_(True),
            )
        )
    ) or 0

    usage_row = (
        await db.execute(
            select(
                func.count(UsageRecord.id).label("requests_24h"),
                func.coalesce(func.sum(UsageRecord.total_tokens), 0).label("total_tokens_24h"),
                func.coalesce(func.sum(UsageRecord.cost_usd), Decimal("0")).label(
                    "total_cost_usd_24h"
                ),
                func.max(UsageRecord.created_at).label("last_request_at"),
            ).where(
                UsageRecord.operation == MANAGED_INFERENCE_OPERATION,
                UsageRecord.created_at >= window_start,
            )
        )
    ).one()

    requests_24h = int(usage_row.requests_24h or 0)

    return InferenceGatewayHealthResponse(
        status=_inference_gateway_health_status(
            enabled_workspaces=int(enabled_workspaces),
            configured_providers=configured_providers,
            requests_24h=requests_24h,
        ),
        enabled_workspaces=int(enabled_workspaces),
        configured_providers=configured_providers,
        requests_24h=requests_24h,
        total_tokens_24h=int(usage_row.total_tokens_24h or 0),
        total_cost_usd_24h=str(usage_row.total_cost_usd_24h),
        last_request_at=usage_row.last_request_at,
    )


def build_conversion_funnel_response(
    *,
    days: int,
    start_date: datetime,
    end_date: datetime,
    landing_views: int,
    register_starts: int,
    register_completes: int,
    signups: int,
    trial_checkout_intent: int,
    trial_started: int,
    first_playbook_created: int,
    paid_active_non_trial: int,
) -> ConversionFunnelResponse:
    """Build conversion funnel response with step-to-step percentages."""
    return ConversionFunnelResponse(
        days=days,
        start_date=start_date,
        end_date=end_date,
        landing_views=landing_views,
        register_starts=register_starts,
        register_completes=register_completes,
        signups=signups,
        trial_checkout_intent=trial_checkout_intent,
        trial_started=trial_started,
        first_playbook_created=first_playbook_created,
        paid_active_non_trial=paid_active_non_trial,
        conversion_landing_to_register_start_pct=_conversion_pct(landing_views, register_starts),
        conversion_register_start_to_register_complete_pct=_conversion_pct(
            register_starts, register_completes
        ),
        conversion_landing_to_register_complete_pct=_conversion_pct(
            landing_views, register_completes
        ),
        conversion_signup_to_checkout_intent_pct=_conversion_pct(signups, trial_checkout_intent),
        conversion_checkout_intent_to_trial_started_pct=_conversion_pct(
            trial_checkout_intent, trial_started
        ),
        conversion_trial_started_to_first_playbook_pct=_conversion_pct(
            trial_started, first_playbook_created
        ),
        conversion_first_playbook_to_paid_active_non_trial_pct=_conversion_pct(
            first_playbook_created, paid_active_non_trial
        ),
        conversion_signup_to_trial_started_pct=_conversion_pct(signups, trial_started),
        conversion_signup_to_paid_active_non_trial_pct=_conversion_pct(
            signups, paid_active_non_trial
        ),
    )


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
    tier_expr = func.coalesce(User.subscription_tier, "free")
    tier_rows = await db.execute(
        select(
            tier_expr.label("tier"),
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
    "/operational-health",
    response_model=OperationalHealthResponse,
    summary="Operational health for hosted cloud rollout services",
)
async def get_operational_health(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OperationalHealthResponse:
    """Return rollout-oriented cloud health snapshots for hosted services."""
    now = datetime.now(UTC)
    sync = await get_sync_health_snapshot(db, now=now)
    job_queue = await get_job_queue_health_snapshot(db, now=now)
    inference_gateway = await get_inference_gateway_health_snapshot(db, now=now)
    return OperationalHealthResponse(
        generated_at=now,
        sync=sync,
        job_queue=job_queue,
        inference_gateway=inference_gateway,
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
    "/workspaces/{workspace_id}/backups",
    response_model=list[WorkspaceBackupItem],
    summary="List hosted workspace backups",
)
async def list_workspace_backups(
    workspace_id: UUID,
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[WorkspaceBackupItem]:
    """List durable hosted backups for one workspace."""
    workspace = await workspace_backup_service.get_restoreable_personal_workspace(db, workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hosted personal workspace not found",
        )

    backups = await workspace_backup_service.list_workspace_backups(db, workspace.id)
    return [
        WorkspaceBackupItem(
            id=str(item.id),
            workspace_id=str(item.workspace_id),
            owner_user_id=str(item.owner_user_id) if item.owner_user_id else None,
            trigger_source=item.trigger_source,
            created_at=item.created_at,
            restored_at=item.restored_at,
            backup_size_bytes=item.backup_size_bytes,
            playbook_count=len(item.payload["account_export"]["playbooks"]),
        )
        for item in backups
    ]


@router.post(
    "/workspaces/{workspace_id}/backups",
    response_model=WorkspaceBackupItem,
    status_code=status.HTTP_201_CREATED,
    summary="Create a hosted workspace backup",
)
async def create_workspace_backup(
    workspace_id: UUID,
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceBackupItem:
    """Create a durable hosted backup for one workspace."""
    workspace = await workspace_backup_service.get_restoreable_personal_workspace(db, workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hosted personal workspace not found",
        )

    try:
        backup = await workspace_backup_service.create_workspace_backup_snapshot(
            db,
            workspace,
            trigger_source="admin_manual",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return WorkspaceBackupItem(
        id=str(backup.id),
        workspace_id=str(backup.workspace_id),
        owner_user_id=str(backup.owner_user_id) if backup.owner_user_id else None,
        trigger_source=backup.trigger_source,
        created_at=backup.created_at,
        restored_at=backup.restored_at,
        backup_size_bytes=backup.backup_size_bytes,
        playbook_count=len(backup.payload["account_export"]["playbooks"]),
    )


@router.post(
    "/workspaces/{workspace_id}/backups/{backup_id}/restore",
    response_model=WorkspaceBackupRestoreResponse,
    summary="Restore a hosted workspace backup",
)
async def restore_workspace_backup(
    workspace_id: UUID,
    backup_id: UUID,
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceBackupRestoreResponse:
    """Restore one hosted workspace from a durable backup snapshot."""
    backup = await workspace_backup_service.get_workspace_backup(db, workspace_id, backup_id)
    if backup is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace backup not found",
        )

    try:
        result = await workspace_backup_service.restore_workspace_backup(db, backup)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return WorkspaceBackupRestoreResponse(
        backup_id=result["backup_id"],
        workspace_id=result["workspace_id"],
        restored_playbooks=result["restored_playbooks"],
        restored_usage_records=result["restored_usage_records"],
        restored_api_keys=result["restored_api_keys"],
        restored_oauth_accounts=result["restored_oauth_accounts"],
    )


@router.get(
    "/funnel",
    response_model=ConversionFunnelResponse,
    summary="Signup conversion funnel",
)
async def get_conversion_funnel(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(30, ge=1, le=365),
    source: Annotated[
        str | None,
        Query(description="Filter by canonical signup source"),
    ] = None,
    experiment_variant: Annotated[
        str | None,
        Query(description="Filter by signup experiment variant"),
    ] = None,
) -> ConversionFunnelResponse:
    """Get conversion funnel metrics for recent signups."""
    now = datetime.now(UTC)
    start = now - timedelta(days=days)

    user_filters = [User.created_at >= start]
    if source:
        user_filters.append(User.signup_source == source.lower())
    if experiment_variant:
        user_filters.append(User.signup_variant == experiment_variant)

    event_filters = [AcquisitionEvent.created_at >= start]
    if source:
        event_filters.append(AcquisitionEvent.source == source.lower())
    if experiment_variant:
        event_filters.append(AcquisitionEvent.experiment_variant == experiment_variant)

    landing_views = (
        await db.scalar(
            select(func.count(AcquisitionEvent.id)).where(
                *event_filters,
                AcquisitionEvent.event_type == AcquisitionEventType.LANDING_VIEW,
            )
        )
        or 0
    )

    register_starts = (
        await db.scalar(
            select(func.count(AcquisitionEvent.id)).where(
                *event_filters,
                AcquisitionEvent.event_type == AcquisitionEventType.REGISTER_START,
            )
        )
        or 0
    )

    register_completes_events = (
        await db.scalar(
            select(func.count(AcquisitionEvent.id)).where(
                *event_filters,
                AcquisitionEvent.event_type == AcquisitionEventType.REGISTER_SUCCESS,
            )
        )
        or 0
    )

    signups = await db.scalar(select(func.count(User.id)).where(*user_filters)) or 0
    register_completes = int(register_completes_events or signups)

    trial_checkout_intent = (
        await db.scalar(
            select(func.count(User.id)).where(
                *user_filters,
                User.stripe_customer_id.is_not(None),
            )
        )
        or 0
    )

    trial_started = (
        await db.scalar(
            select(func.count(User.id)).where(
                *user_filters,
                (User.has_used_trial.is_(True))
                | ((User.trial_ends_at.is_not(None)) & (User.trial_ends_at > now)),
            )
        )
        or 0
    )

    # Keep funnel stages as strict subsets so step conversion math is always valid.
    trial_started_filter = (User.has_used_trial.is_(True)) | (
        (User.trial_ends_at.is_not(None)) & (User.trial_ends_at > now)
    )
    has_any_playbook = select(Playbook.id).where(Playbook.user_id == User.id).exists()

    first_playbook_created = (
        await db.scalar(
            select(func.count(User.id)).where(
                *user_filters,
                trial_started_filter,
                has_any_playbook,
            )
        )
        or 0
    )

    paid_active_non_trial = (
        await db.scalar(
            select(func.count(User.id)).where(
                *user_filters,
                trial_started_filter,
                has_any_playbook,
                User.subscription_status == SubscriptionStatus.ACTIVE,
                User.subscription_tier.is_not(None),
                User.subscription_tier != "free",
                (User.trial_ends_at.is_(None)) | (User.trial_ends_at <= now),
            )
        )
        or 0
    )

    return build_conversion_funnel_response(
        days=days,
        start_date=start,
        end_date=now,
        landing_views=int(landing_views),
        register_starts=int(register_starts),
        register_completes=int(register_completes),
        signups=int(signups),
        trial_checkout_intent=int(trial_checkout_intent),
        trial_started=int(trial_started),
        first_playbook_created=int(first_playbook_created),
        paid_active_non_trial=int(paid_active_non_trial),
    )


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
