"""Workspace entitlement resolution built on current user billing data."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.core.limits import (
    SubscriptionTier,
    UsageStatus,
    get_billing_period_start,
    get_effective_tier_for_limits,
    get_user_usage_status,
    is_user_trialing,
)
from ace_platform.core.metering import UsageCounterSummary, get_usage_counter_summary
from ace_platform.core.subscription_service import get_subscription_tier_for_plan_code
from ace_platform.core.workspaces import DEFAULT_TEAM_WORKSPACE_SEAT_LIMIT
from ace_platform.db.models import SubscriptionStatus, User, Workspace

WorkspacePlan = Literal["personal", "team", "enterprise"]
UsageCounterStatus = Literal["ok", "warning", "blocked"]


@dataclass(frozen=True, slots=True)
class WorkspaceFeatureAccess:
    """Boolean feature gates for one workspace."""

    cloud_sync: bool
    hosted_backups: bool
    managed_inference: bool
    hosted_evals: bool
    invite_members: bool
    shared_workspace: bool
    approvals: bool
    rbac: bool
    sso: bool
    audit_logs: bool


@dataclass(frozen=True, slots=True)
class WorkspaceUsageCounter:
    """One counter with optional soft and hard thresholds."""

    current: int
    soft_limit: int | None
    hard_limit: int | None
    remaining_soft: int | None
    remaining_hard: int | None
    status: UsageCounterStatus


@dataclass(frozen=True, slots=True)
class WorkspaceUsageLimits:
    """Current limits and usage envelope for one workspace."""

    monthly_evolution_runs: int | None
    current_evolution_runs: int
    remaining_evolution_runs: int | None
    monthly_cost_limit_usd: Decimal | None
    current_cost_usd: Decimal
    remaining_cost_usd: Decimal | None
    current_total_tokens: int
    max_playbooks: int | None
    storage_bytes: WorkspaceUsageCounter
    hosted_eval_runs: WorkspaceUsageCounter
    managed_inference_requests: WorkspaceUsageCounter
    managed_inference_tokens: WorkspaceUsageCounter
    warning_fields: tuple[str, ...]
    blocked_fields: tuple[str, ...]
    is_within_limits: bool
    limit_exceeded: str | None


@dataclass(frozen=True, slots=True)
class WorkspaceEntitlementsSnapshot:
    """Authoritative entitlement response for one cloud workspace."""

    workspace_id: str
    plan: WorkspacePlan
    deployment_mode: Literal["cloud", "self_hosted"]
    seat_limit: int | None
    entitlements: WorkspaceFeatureAccess
    enabled_features: tuple[str, ...]
    access: WorkspaceAccessState
    usage_limits: WorkspaceUsageLimits


@dataclass(frozen=True, slots=True)
class WorkspaceAccessState:
    """Subscription-derived access state for one workspace."""

    subscription_tier: SubscriptionTier
    subscription_status: SubscriptionStatus
    effective_tier: SubscriptionTier
    has_feature_access: bool
    is_trialing: bool


def get_workspace_id(user: User, workspace: Workspace | None = None) -> str:
    """Use the current user id as the temporary single-user workspace id."""

    if workspace is not None:
        return str(workspace.id)
    return str(user.id)


def normalize_workspace_plan(user: User, workspace: Workspace | None = None) -> WorkspacePlan:
    """Map the current billing model into the workspace plans from the spec."""

    if workspace is not None:
        return workspace.plan.value

    if getattr(user, "is_admin", False):
        return "enterprise"

    try:
        tier = SubscriptionTier(user.subscription_tier) if user.subscription_tier else None
    except ValueError:
        tier = None

    if tier == SubscriptionTier.ENTERPRISE:
        return "enterprise"

    # The current hosted product only has single-user subscriptions. Until the
    # workspace service exists, every non-enterprise account maps to Personal.
    return "personal"


def get_subscription_tier(
    user: User,
    workspace: Workspace | None = None,
) -> SubscriptionTier:
    """Return the caller's subscription tier with sane fallbacks."""

    if getattr(user, "is_admin", False):
        return SubscriptionTier.ENTERPRISE

    workspace_subscription = (
        getattr(workspace, "subscription", None) if workspace is not None else None
    )
    if workspace_subscription is not None:
        workspace_tier = get_subscription_tier_for_plan_code(workspace_subscription.plan_code)
        if workspace_tier is not None:
            return workspace_tier

    try:
        return (
            SubscriptionTier(user.subscription_tier)
            if user.subscription_tier
            else SubscriptionTier.FREE
        )
    except ValueError:
        return SubscriptionTier.FREE


def has_feature_access(
    user: User,
    subscription_tier: SubscriptionTier,
    workspace: Workspace | None = None,
) -> bool:
    """Return whether the caller currently has paid feature access."""

    if getattr(user, "is_admin", False):
        return True

    workspace_subscription = (
        getattr(workspace, "subscription", None) if workspace is not None else None
    )
    if workspace_subscription is not None:
        return (
            workspace_subscription.status.value in {"active", "trialing"}
            and subscription_tier != SubscriptionTier.FREE
        )

    return (
        getattr(user, "subscription_status", SubscriptionStatus.NONE) == SubscriptionStatus.ACTIVE
        and subscription_tier != SubscriptionTier.FREE
    )


def get_seat_limit(plan: WorkspacePlan) -> int | None:
    """Return the seat limit implied by the normalized workspace plan."""

    if plan == "personal":
        return 1
    if plan == "team":
        return DEFAULT_TEAM_WORKSPACE_SEAT_LIMIT
    return None


def get_plan_entitlements(
    plan: WorkspacePlan,
    feature_access_enabled: bool = True,
) -> WorkspaceFeatureAccess:
    """Return feature access flags for the normalized workspace plan."""

    collaboration_enabled = plan in {"team", "enterprise"}
    governance_enabled = plan == "enterprise"
    convenience_enabled = feature_access_enabled

    return WorkspaceFeatureAccess(
        cloud_sync=convenience_enabled,
        hosted_backups=convenience_enabled,
        managed_inference=convenience_enabled,
        hosted_evals=convenience_enabled,
        invite_members=feature_access_enabled and collaboration_enabled,
        shared_workspace=feature_access_enabled and collaboration_enabled,
        approvals=feature_access_enabled and collaboration_enabled,
        rbac=feature_access_enabled and governance_enabled,
        sso=feature_access_enabled and governance_enabled,
        audit_logs=feature_access_enabled and governance_enabled,
    )


def _coerce_int(value: object) -> int | None:
    """Convert configured limit values into integers when possible."""

    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _read_workspace_usage_config(workspace: Workspace | None) -> dict:
    """Return the workspace usage-limits config payload, if any."""

    raw = getattr(workspace, "usage_limits", None)
    return raw if isinstance(raw, dict) else {}


def _resolve_counter_thresholds(
    workspace: Workspace | None,
    key: str,
    *,
    default_hard: int | None = None,
    aliases: tuple[str, ...] = (),
) -> tuple[int | None, int | None]:
    """Resolve soft and hard thresholds for one usage counter."""

    config = _read_workspace_usage_config(workspace)
    soft_limit = None
    hard_limit = default_hard

    for candidate in (key, *aliases):
        raw_value = config.get(candidate)
        if raw_value is None:
            continue

        if isinstance(raw_value, dict):
            candidate_soft = _coerce_int(
                raw_value.get("soft_limit", raw_value.get("warning_limit"))
            )
            candidate_hard = _coerce_int(raw_value.get("hard_limit"))
            shared_limit = _coerce_int(raw_value.get("limit"))
            if candidate_soft is None and candidate_hard is None and shared_limit is not None:
                if default_hard is None:
                    candidate_soft = shared_limit
                else:
                    candidate_hard = shared_limit
            if candidate_soft is not None:
                soft_limit = candidate_soft
            if candidate_hard is not None:
                hard_limit = candidate_hard
            break

        candidate_limit = _coerce_int(raw_value)
        if candidate_limit is not None:
            hard_limit = candidate_limit
            break

    if default_hard is not None and hard_limit is not None:
        hard_limit = min(default_hard, hard_limit)

    return soft_limit, hard_limit


def _build_usage_counter(
    *,
    current: int,
    soft_limit: int | None,
    hard_limit: int | None,
) -> WorkspaceUsageCounter:
    """Construct one counter with derived status and remaining values."""

    status: UsageCounterStatus = "ok"
    if hard_limit is not None and current >= hard_limit:
        status = "blocked"
    elif soft_limit is not None and current >= soft_limit:
        status = "warning"

    return WorkspaceUsageCounter(
        current=current,
        soft_limit=soft_limit,
        hard_limit=hard_limit,
        remaining_soft=None if soft_limit is None else max(0, soft_limit - current),
        remaining_hard=None if hard_limit is None else max(0, hard_limit - current),
        status=status,
    )


async def get_workspace_usage_limits(
    db: AsyncSession,
    user: User,
    *,
    workspace: Workspace | None = None,
    usage_status: UsageStatus | None = None,
    include_storage: bool = True,
) -> WorkspaceUsageLimits:
    """Build workspace-scoped usage counters and effective limit states."""

    limits_tier = get_effective_tier_for_limits(user)
    usage_status = usage_status or await get_user_usage_status(db, user.id, limits_tier)

    storage_bytes = usage_status.current_storage_bytes if include_storage else 0
    managed_inference = UsageCounterSummary(
        request_count=usage_status.current_managed_inference_requests,
        total_tokens=usage_status.current_managed_inference_tokens,
        total_cost_usd=usage_status.current_managed_inference_cost_usd,
    )

    storage_soft_limit, storage_hard_limit = _resolve_counter_thresholds(
        workspace,
        "storage_bytes",
        default_hard=usage_status.limits.storage_limit_bytes,
    )
    eval_soft_limit, eval_hard_limit = _resolve_counter_thresholds(
        workspace,
        "hosted_eval_runs",
        default_hard=usage_status.limits.monthly_hosted_eval_runs,
        aliases=("monthly_evolution_runs", "eval_runs"),
    )
    mi_request_soft_limit, mi_request_hard_limit = _resolve_counter_thresholds(
        workspace,
        "managed_inference_requests",
    )
    mi_token_soft_limit, mi_token_hard_limit = _resolve_counter_thresholds(
        workspace,
        "managed_inference_tokens",
    )

    storage_counter = _build_usage_counter(
        current=storage_bytes,
        soft_limit=storage_soft_limit,
        hard_limit=storage_hard_limit,
    )
    hosted_eval_counter = _build_usage_counter(
        current=usage_status.current_hosted_eval_runs,
        soft_limit=eval_soft_limit,
        hard_limit=eval_hard_limit,
    )
    managed_inference_request_counter = _build_usage_counter(
        current=managed_inference.request_count,
        soft_limit=mi_request_soft_limit,
        hard_limit=mi_request_hard_limit,
    )
    managed_inference_token_counter = _build_usage_counter(
        current=managed_inference.total_tokens,
        soft_limit=mi_token_soft_limit,
        hard_limit=mi_token_hard_limit,
    )

    warning_fields = tuple(
        name
        for name, counter in (
            ("storage_bytes", storage_counter),
            ("hosted_eval_runs", hosted_eval_counter),
            ("managed_inference_requests", managed_inference_request_counter),
            ("managed_inference_tokens", managed_inference_token_counter),
        )
        if counter.status == "warning"
    )

    blocked_fields = list(
        name
        for name, counter in (
            ("storage_bytes", storage_counter),
            ("hosted_eval_runs", hosted_eval_counter),
            ("managed_inference_requests", managed_inference_request_counter),
            ("managed_inference_tokens", managed_inference_token_counter),
        )
        if counter.status == "blocked"
    )
    if usage_status.limit_exceeded == "monthly_cost_limit":
        blocked_fields.append("monthly_cost_limit")
    elif (
        usage_status.limit_exceeded == "monthly_evolution_runs"
        and "hosted_eval_runs" not in blocked_fields
    ):
        blocked_fields.append("hosted_eval_runs")

    blocked_fields_tuple = tuple(dict.fromkeys(blocked_fields))

    return WorkspaceUsageLimits(
        monthly_evolution_runs=usage_status.limits.monthly_evolution_runs,
        current_evolution_runs=usage_status.current_evolution_runs,
        remaining_evolution_runs=usage_status.remaining_evolution_runs,
        monthly_cost_limit_usd=usage_status.limits.monthly_cost_limit_usd,
        current_cost_usd=usage_status.current_cost_usd,
        remaining_cost_usd=usage_status.remaining_cost_usd,
        current_total_tokens=usage_status.current_total_tokens,
        max_playbooks=usage_status.limits.max_playbooks,
        storage_bytes=storage_counter,
        hosted_eval_runs=hosted_eval_counter,
        managed_inference_requests=managed_inference_request_counter,
        managed_inference_tokens=managed_inference_token_counter,
        warning_fields=warning_fields,
        blocked_fields=blocked_fields_tuple,
        is_within_limits=usage_status.is_within_limits and not blocked_fields_tuple,
        limit_exceeded=blocked_fields_tuple[0] if blocked_fields_tuple else None,
    )


async def resolve_workspace_entitlements(
    db: AsyncSession,
    user: User,
    workspace: Workspace | None = None,
) -> WorkspaceEntitlementsSnapshot:
    """Build a workspace-shaped entitlement snapshot for the authenticated user."""

    plan = normalize_workspace_plan(user, workspace)
    subscription_tier = get_subscription_tier(user, workspace)
    limits_tier = get_effective_tier_for_limits(user)
    usage_status = await get_user_usage_status(db, user.id, limits_tier)
    feature_access_enabled = has_feature_access(user, subscription_tier, workspace)
    entitlements = get_plan_entitlements(plan, feature_access_enabled)
    enabled_features = tuple(
        field.name for field in fields(WorkspaceFeatureAccess) if getattr(entitlements, field.name)
    )
    workspace_subscription = (
        getattr(workspace, "subscription", None) if workspace is not None else None
    )

    return WorkspaceEntitlementsSnapshot(
        workspace_id=get_workspace_id(user, workspace),
        plan=plan,
        deployment_mode=(workspace.deployment_mode.value if workspace is not None else "cloud"),
        seat_limit=workspace.seat_limit if workspace is not None else get_seat_limit(plan),
        entitlements=entitlements,
        enabled_features=enabled_features,
        access=WorkspaceAccessState(
            subscription_tier=subscription_tier,
            subscription_status=(
                SubscriptionStatus(workspace_subscription.status.value)
                if workspace_subscription is not None
                else getattr(user, "subscription_status", SubscriptionStatus.NONE)
            ),
            effective_tier=limits_tier,
            has_feature_access=feature_access_enabled,
            is_trialing=is_user_trialing(user),
        ),
        usage_limits=await get_workspace_usage_limits(
            db,
            user,
            workspace=workspace,
            usage_status=usage_status,
        ),
    )


async def check_workspace_managed_inference_allowed(
    db: AsyncSession,
    user: User,
    *,
    workspace: Workspace | None = None,
) -> tuple[bool, str | None]:
    """Return whether managed inference can proceed for the workspace."""

    period_start = get_billing_period_start()
    period_end = datetime.now(UTC)
    managed_inference = await get_usage_counter_summary(
        db,
        user.id,
        period_start,
        period_end,
        operation_prefixes=("managed_inference",),
        workspace_id=getattr(workspace, "id", None),
    )

    request_soft_limit, request_hard_limit = _resolve_counter_thresholds(
        workspace,
        "managed_inference_requests",
    )
    token_soft_limit, token_hard_limit = _resolve_counter_thresholds(
        workspace,
        "managed_inference_tokens",
    )

    request_counter = _build_usage_counter(
        current=managed_inference.request_count,
        soft_limit=request_soft_limit,
        hard_limit=request_hard_limit,
    )
    token_counter = _build_usage_counter(
        current=managed_inference.total_tokens,
        soft_limit=token_soft_limit,
        hard_limit=token_hard_limit,
    )

    if request_counter.status == "blocked":
        return False, "Workspace managed inference request limit reached."
    if token_counter.status == "blocked":
        return False, "Workspace managed inference token limit reached."
    return True, None
