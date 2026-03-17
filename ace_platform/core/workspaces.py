"""Workspace tenancy defaults and entitlement evaluation helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from ace_core.contracts import Feature
from ace_platform.db.models import DeploymentMode, Workspace, WorkspacePlan


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
                None
                if self.monthly_cost_limit_usd is None
                else str(self.monthly_cost_limit_usd)
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

    if plan in {WorkspacePlan.PERSONAL, WorkspacePlan.TEAM} and deployment_mode != DeploymentMode.CLOUD:
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
