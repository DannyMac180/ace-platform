"""Workspace tenancy defaults and entitlement evaluation helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ace_core.contracts import Feature
from ace_platform.db.models import (
    BillingProvider,
    DeploymentMode,
    MembershipRole,
    SubscriptionStatus,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspacePlan,
    WorkspaceSubscription,
    WorkspaceSubscriptionStatus,
)


@dataclass(frozen=True, slots=True)
class WorkspaceEntitlementSet:
    """Feature access for a workspace plan."""

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

    async def can(self, feature: Feature) -> bool:
        """Return whether the workspace can use the requested feature."""
        return bool(getattr(self, feature))

    def to_dict(self) -> dict[str, bool]:
        """Serialize the feature flags to a plain dictionary."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class WorkspaceUsageEnvelope:
    """Workspace-level usage envelope defaults.

    Usage and billing remain user-centric elsewhere in the platform today, so
    the initial workspace model only defines membership capacity authoritatively.
    The optional fields stay open for later billing/usage migration work.
    """

    max_members: int | None
    monthly_evolution_runs: int | None = None
    monthly_cost_limit_usd: Decimal | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the usage envelope for storage or API responses."""
        return {
            "max_members": self.max_members,
            "monthly_evolution_runs": self.monthly_evolution_runs,
            "monthly_cost_limit_usd": (
                None if self.monthly_cost_limit_usd is None else str(self.monthly_cost_limit_usd)
            ),
        }


@dataclass(frozen=True, slots=True)
class WorkspacePlanDefaults:
    """Default plan semantics for a hosted workspace."""

    default_deployment_mode: DeploymentMode
    default_seat_limit: int
    minimum_seat_limit: int
    entitlements: WorkspaceEntitlementSet
    usage: WorkspaceUsageEnvelope


WORKSPACE_PLAN_DEFAULTS: dict[WorkspacePlan, WorkspacePlanDefaults] = {
    WorkspacePlan.PERSONAL: WorkspacePlanDefaults(
        default_deployment_mode=DeploymentMode.CLOUD,
        default_seat_limit=1,
        minimum_seat_limit=1,
        entitlements=WorkspaceEntitlementSet(
            cloud_sync=True,
            hosted_backups=True,
            managed_inference=True,
            hosted_evals=True,
            invite_members=False,
            shared_workspace=False,
            approvals=False,
            rbac=False,
            sso=False,
            audit_logs=False,
        ),
        usage=WorkspaceUsageEnvelope(max_members=1),
    ),
    WorkspacePlan.TEAM: WorkspacePlanDefaults(
        default_deployment_mode=DeploymentMode.CLOUD,
        default_seat_limit=5,
        minimum_seat_limit=2,
        entitlements=WorkspaceEntitlementSet(
            cloud_sync=True,
            hosted_backups=True,
            managed_inference=True,
            hosted_evals=True,
            invite_members=True,
            shared_workspace=True,
            approvals=True,
            rbac=True,
            sso=False,
            audit_logs=True,
        ),
        usage=WorkspaceUsageEnvelope(max_members=None),
    ),
    WorkspacePlan.ENTERPRISE: WorkspacePlanDefaults(
        default_deployment_mode=DeploymentMode.SELF_HOSTED,
        default_seat_limit=25,
        minimum_seat_limit=2,
        entitlements=WorkspaceEntitlementSet(
            cloud_sync=True,
            hosted_backups=True,
            managed_inference=True,
            hosted_evals=True,
            invite_members=True,
            shared_workspace=True,
            approvals=True,
            rbac=True,
            sso=True,
            audit_logs=True,
        ),
        usage=WorkspaceUsageEnvelope(max_members=None),
    ),
}


def get_workspace_plan_defaults(plan: WorkspacePlan) -> WorkspacePlanDefaults:
    """Return the canonical defaults for a workspace plan."""
    return WORKSPACE_PLAN_DEFAULTS[plan]


def validate_workspace_shape(
    plan: WorkspacePlan,
    seat_limit: int,
    deployment_mode: DeploymentMode,
) -> None:
    """Validate that a workspace shape is compatible with its plan."""
    defaults = get_workspace_plan_defaults(plan)

    if seat_limit < defaults.minimum_seat_limit:
        raise ValueError(
            f"{plan.value} workspaces require at least {defaults.minimum_seat_limit} seat(s)."
        )

    if plan == WorkspacePlan.PERSONAL and seat_limit != 1:
        raise ValueError("personal workspaces must have exactly one seat.")

    if (
        plan in {WorkspacePlan.PERSONAL, WorkspacePlan.TEAM}
        and deployment_mode != DeploymentMode.CLOUD
    ):
        raise ValueError(f"{plan.value} workspaces must use cloud deployment.")


def _merge_entitlements(
    base: WorkspaceEntitlementSet,
    overrides: dict[str, Any] | None,
) -> WorkspaceEntitlementSet:
    if not overrides:
        return base

    merged = base.to_dict()
    for feature, value in overrides.items():
        if feature in merged:
            merged[feature] = bool(value)
    return WorkspaceEntitlementSet(**merged)


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _merge_usage(
    base: WorkspaceUsageEnvelope,
    overrides: dict[str, Any] | None,
    seat_limit: int,
) -> WorkspaceUsageEnvelope:
    if not overrides:
        if base.max_members is None:
            return WorkspaceUsageEnvelope(
                max_members=seat_limit,
                monthly_evolution_runs=base.monthly_evolution_runs,
                monthly_cost_limit_usd=base.monthly_cost_limit_usd,
            )
        return base

    max_members = overrides.get("max_members", base.max_members)
    if max_members is None:
        max_members = seat_limit

    return WorkspaceUsageEnvelope(
        max_members=int(max_members),
        monthly_evolution_runs=overrides.get(
            "monthly_evolution_runs",
            base.monthly_evolution_runs,
        ),
        monthly_cost_limit_usd=_parse_decimal(
            overrides.get("monthly_cost_limit_usd", base.monthly_cost_limit_usd)
        ),
    )


def resolve_workspace_entitlements(workspace: Workspace) -> WorkspaceEntitlementSet:
    """Resolve a workspace's effective entitlements."""
    defaults = get_workspace_plan_defaults(workspace.plan)
    return _merge_entitlements(defaults.entitlements, workspace.entitlement_overrides)


def resolve_workspace_usage(workspace: Workspace) -> WorkspaceUsageEnvelope:
    """Resolve a workspace's effective usage envelope."""
    defaults = get_workspace_plan_defaults(workspace.plan)
    return _merge_usage(defaults.usage, workspace.usage_limit_overrides, workspace.seat_limit)


async def workspace_can_use_feature(workspace: Workspace, feature: Feature) -> bool:
    """Convenience wrapper for checking a feature flag on a workspace."""
    entitlements = resolve_workspace_entitlements(workspace)
    return await entitlements.can(feature)


def build_personal_workspace_name(user: User) -> str:
    """Generate a stable default name for a user's hosted personal workspace."""
    local_part = user.email.split("@", 1)[0].strip() or "personal"
    return f"{local_part} personal workspace"


def has_legacy_workspace_billing(user: User) -> bool:
    """Return whether the user has legacy billing state worth projecting."""
    return bool(
        user.subscription_tier
        or user.stripe_customer_id
        or user.stripe_subscription_id
        or user.subscription_current_period_end
        or user.trial_ends_at
        or user.subscription_status != SubscriptionStatus.NONE
    )


def _map_legacy_subscription_status(
    user: User,
    *,
    now: datetime | None = None,
) -> WorkspaceSubscriptionStatus:
    """Map the current user-level billing status into workspace billing state."""
    current_time = now or datetime.now(UTC)
    if user.trial_ends_at and user.trial_ends_at > current_time:
        return WorkspaceSubscriptionStatus.TRIALING
    if user.subscription_status == SubscriptionStatus.ACTIVE:
        return WorkspaceSubscriptionStatus.ACTIVE
    if user.subscription_status == SubscriptionStatus.PAST_DUE:
        return WorkspaceSubscriptionStatus.PAST_DUE
    if user.subscription_status == SubscriptionStatus.CANCELED:
        return WorkspaceSubscriptionStatus.CANCELED
    return WorkspaceSubscriptionStatus.UNPAID


def build_workspace_subscription_from_user(
    user: User,
    *,
    workspace: Workspace,
    now: datetime | None = None,
) -> WorkspaceSubscription | None:
    """Project legacy user-scoped billing fields onto a workspace subscription."""
    if not has_legacy_workspace_billing(user):
        return None

    billing_provider = (
        BillingProvider.STRIPE
        if user.stripe_customer_id or user.stripe_subscription_id
        else BillingProvider.MANUAL
    )

    return WorkspaceSubscription(
        workspace=workspace,
        billing_provider=billing_provider,
        status=_map_legacy_subscription_status(user, now=now),
        plan_code=user.subscription_tier or WorkspacePlan.PERSONAL.value,
        external_customer_id=user.stripe_customer_id,
        external_subscription_id=user.stripe_subscription_id,
        current_period_end=user.subscription_current_period_end or user.trial_ends_at,
    )


async def ensure_personal_workspace_for_user(
    db: AsyncSession,
    user: User,
) -> Workspace:
    """Ensure a user has a personal hosted workspace and owner membership."""
    existing_result = await db.execute(
        select(Workspace)
        .join(WorkspaceMembership)
        .options(selectinload(Workspace.subscription))
        .where(WorkspaceMembership.user_id == user.id)
        .order_by(Workspace.created_at.asc())
    )
    workspace = existing_result.scalars().first()
    if workspace is not None:
        if workspace.subscription is None:
            subscription = build_workspace_subscription_from_user(user, workspace=workspace)
            if subscription is not None:
                db.add(subscription)
                await db.flush()
        return workspace

    defaults = get_workspace_plan_defaults(WorkspacePlan.PERSONAL)
    workspace = Workspace(
        name=build_personal_workspace_name(user),
        plan=WorkspacePlan.PERSONAL,
        deployment_mode=defaults.default_deployment_mode,
        seat_limit=defaults.default_seat_limit,
    )
    validate_workspace_shape(
        plan=workspace.plan,
        seat_limit=workspace.seat_limit,
        deployment_mode=workspace.deployment_mode,
    )

    membership = WorkspaceMembership(
        workspace=workspace,
        user=user,
        role=MembershipRole.OWNER,
    )

    db.add(workspace)
    db.add(membership)

    subscription = build_workspace_subscription_from_user(user, workspace=workspace)
    if subscription is not None:
        db.add(subscription)

    await db.flush()
    return workspace
