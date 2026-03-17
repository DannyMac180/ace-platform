"""Workspace entitlement resolution built on current user billing data."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.core.limits import (
    SubscriptionTier,
    UsageStatus,
    get_effective_tier_for_limits,
    get_user_usage_status,
)
from ace_platform.db.models import User

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
    deployment_mode: Literal["cloud"]
    seat_limit: int | None
    entitlements: WorkspaceFeatureAccess
    usage_limits: WorkspaceUsageLimits


def get_workspace_id(user: User) -> str:
    """Use the current user id as the temporary single-user workspace id."""

    return str(user.id)


def normalize_workspace_plan(user: User) -> WorkspacePlan:
    """Map the current billing model into the workspace plans from the spec."""

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


def get_seat_limit(plan: WorkspacePlan) -> int | None:
    """Return the seat limit implied by the normalized workspace plan."""

    if plan == "personal":
        return 1
    if plan == "team":
        return 10
    return None


def get_plan_entitlements(plan: WorkspacePlan) -> WorkspaceFeatureAccess:
    """Return feature access flags for the normalized workspace plan."""

    collaboration_enabled = plan in {"team", "enterprise"}
    governance_enabled = plan == "enterprise"

    return WorkspaceFeatureAccess(
        cloud_sync=True,
        hosted_backups=True,
        managed_inference=True,
        hosted_evals=True,
        invite_members=collaboration_enabled,
        shared_workspace=collaboration_enabled,
        approvals=collaboration_enabled,
        rbac=governance_enabled,
        sso=governance_enabled,
        audit_logs=governance_enabled,
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
) -> WorkspaceEntitlementsSnapshot:
    """Build a workspace-shaped entitlement snapshot for the authenticated user."""

    plan = normalize_workspace_plan(user)
    limits_tier = get_effective_tier_for_limits(user)
    usage_status = await get_user_usage_status(db, user.id, limits_tier)

    return WorkspaceEntitlementsSnapshot(
        workspace_id=get_workspace_id(user),
        plan=plan,
        deployment_mode="cloud",
        seat_limit=get_seat_limit(plan),
        entitlements=get_plan_entitlements(plan),
        usage_limits=_build_usage_limits(usage_status),
    )
