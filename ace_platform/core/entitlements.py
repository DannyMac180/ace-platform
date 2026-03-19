"""Workspace entitlement resolution built on current user billing data."""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.core.limits import (
    SubscriptionTier,
    UsageStatus,
    get_effective_tier_for_limits,
    get_tier_limits,
    get_user_usage_status,
    is_user_trialing,
)
from ace_platform.core.subscription_service import get_subscription_tier_for_plan_code
from ace_platform.core.workspaces import DEFAULT_TEAM_WORKSPACE_SEAT_LIMIT
from ace_platform.db.models import SubscriptionStatus, User, Workspace

WorkspacePlan = Literal["personal", "team", "enterprise"]


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


def _build_usage_limits(status: UsageStatus) -> WorkspaceUsageLimits:
    """Convert the existing usage status shape into the workspace response shape."""

    return WorkspaceUsageLimits(
        monthly_evolution_runs=status.limits.monthly_evolution_runs,
        current_evolution_runs=status.current_evolution_runs,
        remaining_evolution_runs=status.remaining_evolution_runs,
        monthly_cost_limit_usd=status.limits.monthly_cost_limit_usd,
        current_cost_usd=status.current_cost_usd,
        remaining_cost_usd=status.remaining_cost_usd,
        current_total_tokens=status.current_total_tokens,
        max_playbooks=status.limits.max_playbooks,
        is_within_limits=status.is_within_limits,
        limit_exceeded=status.limit_exceeded,
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
    limits = get_tier_limits(limits_tier)

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
        usage_limits=WorkspaceUsageLimits(
            monthly_evolution_runs=limits.monthly_evolution_runs,
            current_evolution_runs=usage_status.current_evolution_runs,
            remaining_evolution_runs=usage_status.remaining_evolution_runs,
            monthly_cost_limit_usd=limits.monthly_cost_limit_usd,
            current_cost_usd=usage_status.current_cost_usd,
            remaining_cost_usd=usage_status.remaining_cost_usd,
            current_total_tokens=usage_status.current_total_tokens,
            max_playbooks=limits.max_playbooks,
            is_within_limits=usage_status.is_within_limits,
            limit_exceeded=usage_status.limit_exceeded,
        ),
    )
