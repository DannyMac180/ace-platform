"""Workspace service layer.

Provides CRUD helpers, membership management, and bootstrap flows that enforce
the hosted-workspace invariants for cloud users.
"""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timezone
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ace_core.contracts import Feature
from ace_platform.db.models import (
    BillingProvider,
    DeploymentMode,
    SubscriptionStatus,
    User,
    Workspace,
    WorkspaceDeploymentMode,
    WorkspaceEntitlement,
    WorkspaceInferenceMode,
    WorkspaceInferenceProvider,
    WorkspaceInvitation,
    WorkspaceMembership,
    WorkspacePlan,
    WorkspaceRole,
    WorkspaceSubscription,
    WorkspaceSubscriptionStatus,
    get_default_workspace_entitlements,
    get_default_workspace_inference_config,
    workspace_supports_managed_inference,
)

MANAGER_ROLES = {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}
DEFAULT_TEAM_WORKSPACE_SEAT_LIMIT = 5
APPROVER_ROLES = {WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.REVIEWER}


@dataclass(frozen=True, slots=True)
class WorkspaceEntitlementSet:
    """Compatibility feature snapshot for older workspace helper callers."""

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
    """Compatibility usage envelope for older workspace helper callers."""

    max_members: int | None
    monthly_evolution_runs: int | None = None
    monthly_cost_limit_usd: Decimal | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the usage envelope to plain values."""

        return {
            "max_members": self.max_members,
            "monthly_evolution_runs": self.monthly_evolution_runs,
            "monthly_cost_limit_usd": (
                None if self.monthly_cost_limit_usd is None else str(self.monthly_cost_limit_usd)
            ),
        }


@dataclass(frozen=True, slots=True)
class WorkspacePlanDefaults:
    """Compatibility default plan semantics for older tenancy helpers."""

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
        default_seat_limit=DEFAULT_TEAM_WORKSPACE_SEAT_LIMIT,
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
    """Return compatibility defaults for the requested workspace plan."""

    return WORKSPACE_PLAN_DEFAULTS[plan]


def validate_workspace_shape(
    plan: WorkspacePlan,
    seat_limit: int,
    deployment_mode: DeploymentMode,
) -> None:
    """Validate compatibility workspace-shape invariants."""

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
    """Resolve compatibility entitlements for a workspace."""

    defaults = get_workspace_plan_defaults(workspace.plan)
    relation = getattr(workspace, "entitlements", None)
    if relation is not None:
        overrides = {
            "cloud_sync": relation.cloud_sync,
            "hosted_backups": relation.hosted_backups,
            "managed_inference": relation.managed_inference,
            "hosted_evals": relation.hosted_evals,
            "invite_members": relation.invite_members,
            "shared_workspace": relation.shared_workspace,
            "approvals": relation.approvals,
            "rbac": relation.rbac,
            "sso": relation.sso,
            "audit_logs": relation.audit_logs,
        }
    else:
        overrides = getattr(workspace, "entitlement_overrides", None)
    return _merge_entitlements(defaults.entitlements, overrides)


def resolve_workspace_usage(workspace: Workspace) -> WorkspaceUsageEnvelope:
    """Resolve compatibility usage defaults for a workspace."""

    defaults = get_workspace_plan_defaults(workspace.plan)
    overrides = getattr(workspace, "usage_limits", None)
    if overrides is None:
        overrides = getattr(workspace, "usage_limit_overrides", None)
    return _merge_usage(defaults.usage, overrides, workspace.seat_limit)


async def workspace_can_use_feature(workspace: Workspace, feature: Feature) -> bool:
    """Compatibility wrapper for checking a feature flag on a workspace."""

    entitlements = resolve_workspace_entitlements(workspace)
    return await entitlements.can(feature)


@dataclass(frozen=True)
class WorkspacePermissions:
    """Effective role-based permissions for one workspace member."""

    can_manage_settings: bool
    can_manage_seats: bool
    can_approve_playbooks: bool


HostedPersonalWorkspaceMigrationAction = Literal[
    "created",
    "repaired",
    "unchanged",
    "skipped",
]
HostedPersonalWorkspaceValidationStatus = Literal["valid", "invalid", "skipped"]


@dataclass(frozen=True, slots=True)
class HostedPersonalWorkspaceMigrationResult:
    """One hosted-user migration outcome."""

    user_id: UUID
    email: str
    action: HostedPersonalWorkspaceMigrationAction
    workspace_id: UUID | None
    eligible: bool
    reasons: tuple[str, ...] = ()
    workspace_created: bool = False
    membership_created: bool = False
    membership_role_updated_from: str | None = None
    entitlements_created: bool = False
    subscription_created: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize the outcome for logs and scripts."""

        return {
            "user_id": str(self.user_id),
            "email": self.email,
            "action": self.action,
            "workspace_id": None if self.workspace_id is None else str(self.workspace_id),
            "eligible": self.eligible,
            "reasons": list(self.reasons),
            "workspace_created": self.workspace_created,
            "membership_created": self.membership_created,
            "membership_role_updated_from": self.membership_role_updated_from,
            "entitlements_created": self.entitlements_created,
            "subscription_created": self.subscription_created,
        }


@dataclass(frozen=True, slots=True)
class HostedPersonalWorkspaceMigrationSummary:
    """Aggregate migration outcomes for one run."""

    dry_run: bool
    scanned_users: int
    eligible_users: int
    created_count: int
    repaired_count: int
    unchanged_count: int
    skipped_count: int
    results: tuple[HostedPersonalWorkspaceMigrationResult, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the summary for logs and scripts."""

        return {
            "dry_run": self.dry_run,
            "scanned_users": self.scanned_users,
            "eligible_users": self.eligible_users,
            "created_count": self.created_count,
            "repaired_count": self.repaired_count,
            "unchanged_count": self.unchanged_count,
            "skipped_count": self.skipped_count,
            "results": [result.to_dict() for result in self.results],
        }


@dataclass(frozen=True, slots=True)
class HostedPersonalWorkspaceValidationResult:
    """One hosted-user validation outcome."""

    user_id: UUID
    email: str
    status: HostedPersonalWorkspaceValidationStatus
    workspace_id: UUID | None
    eligible: bool
    errors: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize the outcome for logs and scripts."""

        return {
            "user_id": str(self.user_id),
            "email": self.email,
            "status": self.status,
            "workspace_id": None if self.workspace_id is None else str(self.workspace_id),
            "eligible": self.eligible,
            "errors": list(self.errors),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class HostedPersonalWorkspaceValidationSummary:
    """Aggregate validation outcomes for one run."""

    scanned_users: int
    eligible_users: int
    valid_count: int
    invalid_count: int
    skipped_count: int
    results: tuple[HostedPersonalWorkspaceValidationResult, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the summary for logs and scripts."""

        return {
            "scanned_users": self.scanned_users,
            "eligible_users": self.eligible_users,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "skipped_count": self.skipped_count,
            "results": [result.to_dict() for result in self.results],
        }


def can_manage_workspace_settings(role: WorkspaceRole) -> bool:
    """Return whether the role can alter workspace settings."""

    return role in MANAGER_ROLES


def can_manage_workspace_seats(role: WorkspaceRole) -> bool:
    """Return whether the role can invite, remove, or re-role members."""

    return role in MANAGER_ROLES


def can_approve_workspace_playbooks(role: WorkspaceRole) -> bool:
    """Return whether the role can approve shared playbooks."""

    return role in APPROVER_ROLES


def resolve_workspace_permissions(
    workspace: Workspace,
    role: WorkspaceRole,
) -> WorkspacePermissions:
    """Resolve the caller's effective permissions inside a workspace."""

    entitlement_values = (
        get_default_workspace_entitlements(workspace.plan)
        if workspace.entitlements is None
        else {
            "invite_members": workspace.entitlements.invite_members,
            "approvals": workspace.entitlements.approvals,
        }
    )

    return WorkspacePermissions(
        can_manage_settings=can_manage_workspace_settings(role),
        can_manage_seats=bool(entitlement_values["invite_members"])
        and can_manage_workspace_seats(role),
        can_approve_playbooks=bool(entitlement_values["approvals"])
        and can_approve_workspace_playbooks(role),
    )


def default_personal_workspace_name(email: str | None) -> str:
    """Build a stable personal workspace name from an email address."""
    if not email:
        return "Personal Workspace"

    local_part = email.split("@", 1)[0]
    cleaned = local_part.replace(".", " ").replace("_", " ").replace("-", " ").strip()
    pretty_name = " ".join(part.capitalize() for part in cleaned.split())
    if pretty_name:
        return f"{pretty_name}'s Workspace"[:255]
    return "Personal Workspace"


def has_legacy_workspace_billing(user: User) -> bool:
    """Return whether the user still carries legacy billing fields."""

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
    """Project user-level billing status into workspace subscription status."""

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
    """Project legacy user billing fields into a workspace subscription row."""

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
        provider_customer_id=user.stripe_customer_id,
        provider_subscription_id=user.stripe_subscription_id,
        current_period_end=user.subscription_current_period_end,
        trial_ends_at=user.trial_ends_at,
    )


def normalize_workspace_invitation_email(email: str) -> str:
    """Canonicalize invitation email addresses for lookups."""
    return email.strip().lower()


def normalize_workspace_settings(
    *,
    plan: WorkspacePlan,
    deployment_mode: WorkspaceDeploymentMode,
    seat_limit: int | None,
    inference_config: dict | None,
    keep_unsupported_managed_mode: bool = False,
) -> tuple[WorkspacePlan, WorkspaceDeploymentMode, int, dict[str, str]]:
    """Normalize and validate workspace settings."""
    resolved_seat_limit = _default_workspace_seat_limit(plan, seat_limit)
    if resolved_seat_limit < 1:
        raise ValueError("Workspace seat limit must be at least 1")

    if plan == WorkspacePlan.PERSONAL:
        resolved_seat_limit = 1
    elif plan == WorkspacePlan.TEAM and resolved_seat_limit < 2:
        raise ValueError("Team workspace seat limit must be at least 2")

    resolved_inference_config = normalize_workspace_inference_config(
        plan=plan,
        deployment_mode=deployment_mode,
        inference_config=inference_config,
        keep_unsupported_managed_mode=keep_unsupported_managed_mode,
    )

    return plan, deployment_mode, resolved_seat_limit, resolved_inference_config


def _default_workspace_seat_limit(
    plan: WorkspacePlan,
    seat_limit: int | None,
) -> int:
    """Resolve plan-aware seat defaults for hosted workspaces."""

    if seat_limit is not None:
        return seat_limit
    if plan == WorkspacePlan.TEAM:
        return DEFAULT_TEAM_WORKSPACE_SEAT_LIMIT
    return 1


def normalize_workspace_inference_config(
    *,
    plan: WorkspacePlan,
    deployment_mode: WorkspaceDeploymentMode,
    inference_config: dict | None,
    keep_unsupported_managed_mode: bool = False,
) -> dict[str, str]:
    """Normalize and validate the workspace inference configuration."""

    default_config = get_default_workspace_inference_config(
        plan=plan,
        deployment_mode=deployment_mode,
    )
    raw_config = inference_config or default_config

    raw_mode = raw_config.get("mode", default_config["mode"])
    raw_provider = raw_config.get("provider", default_config["provider"])

    try:
        mode = WorkspaceInferenceMode(raw_mode)
    except ValueError as exc:
        raise ValueError(f"Unsupported workspace inference mode: {raw_mode}") from exc

    try:
        provider = WorkspaceInferenceProvider(raw_provider)
    except ValueError as exc:
        raise ValueError(f"Unsupported workspace inference provider: {raw_provider}") from exc

    if mode == WorkspaceInferenceMode.MANAGED_PROVIDER and not workspace_supports_managed_inference(
        plan=plan,
        deployment_mode=deployment_mode,
    ):
        if keep_unsupported_managed_mode:
            mode = WorkspaceInferenceMode.BYO_PROVIDER
        else:
            raise ValueError("ACE-managed inference is not supported for this workspace")

    return {
        "mode": mode.value,
        "provider": provider.value,
    }


def _normalize_user_email_filters(emails: list[str] | None) -> list[str]:
    return [email.strip().lower() for email in emails or [] if email.strip()]


async def list_hosted_personal_workspace_migration_users(
    db: AsyncSession,
    *,
    emails: list[str] | None = None,
) -> list[User]:
    """Load active users together with the relationships needed for migration."""

    stmt = (
        select(User)
        .where(User.is_active.is_(True))
        .options(
            selectinload(User.memberships)
            .selectinload(WorkspaceMembership.workspace)
            .selectinload(Workspace.subscription),
            selectinload(User.memberships)
            .selectinload(WorkspaceMembership.workspace)
            .selectinload(Workspace.entitlements),
        )
        .order_by(User.created_at.asc(), User.id.asc())
    )

    normalized_emails = _normalize_user_email_filters(emails)
    if normalized_emails:
        stmt = stmt.where(func.lower(User.email).in_(normalized_emails))

    result = await db.execute(stmt)
    return list(result.scalars().unique().all())


def _is_hosted_personal_workspace(workspace: Workspace) -> bool:
    return (
        workspace.plan == WorkspacePlan.PERSONAL
        and workspace.deployment_mode == WorkspaceDeploymentMode.CLOUD
    )


def _workspace_membership_for_user(
    user: User,
    workspace: Workspace,
) -> WorkspaceMembership | None:
    for membership in user.memberships:
        if membership.workspace_id == workspace.id:
            return membership
    return None


def classify_hosted_solo_user_workspace_state(
    user: User,
) -> tuple[bool, Workspace | None, tuple[str, ...]]:
    """Classify whether the user belongs to the hosted-solo migration cohort."""

    workspaces_by_id: dict[UUID, Workspace] = {}
    for membership in user.memberships:
        workspace = membership.workspace
        if workspace is not None:
            workspaces_by_id[workspace.id] = workspace

    workspaces = list(workspaces_by_id.values())
    if not workspaces:
        return True, None, ("missing_workspace",)

    if len(workspaces) == 1 and _is_hosted_personal_workspace(workspaces[0]):
        return True, workspaces[0], ()

    reasons: list[str] = []
    if len(workspaces) > 1:
        reasons.append("multiple_workspaces")
    elif not _is_hosted_personal_workspace(workspaces[0]):
        reasons.append("non_personal_or_non_cloud_workspace")
    return False, None, tuple(reasons)


async def list_user_workspaces(db: AsyncSession, user_id: UUID) -> list[Workspace]:
    """List all workspaces visible to a user."""
    result = await db.execute(
        select(Workspace)
        .join(WorkspaceMembership)
        .where(WorkspaceMembership.user_id == user_id)
        .options(
            selectinload(Workspace.memberships).selectinload(WorkspaceMembership.user),
            selectinload(Workspace.entitlements),
            selectinload(Workspace.subscription),
        )
        .order_by(Workspace.created_at.asc(), Workspace.id.asc())
    )
    return list(result.scalars().unique().all())


async def get_default_workspace_for_user(
    db: AsyncSession,
    user_id: UUID,
) -> Workspace | None:
    """Return the user's default workspace for personal entry points."""
    workspaces = await list_user_workspaces(db, user_id)
    if not workspaces:
        return None
    return workspaces[0]


async def get_workspace_for_user(
    db: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
) -> Workspace | None:
    """Fetch a workspace only if the user is a member."""
    result = await db.execute(
        select(Workspace)
        .join(WorkspaceMembership)
        .where(
            Workspace.id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
        .options(
            selectinload(Workspace.memberships).selectinload(WorkspaceMembership.user),
            selectinload(Workspace.entitlements),
            selectinload(Workspace.subscription),
        )
    )
    return result.scalars().unique().one_or_none()


async def get_workspace_by_id(
    db: AsyncSession,
    workspace_id: UUID,
) -> Workspace | None:
    """Fetch a workspace regardless of the requesting user."""
    result = await db.execute(
        select(Workspace)
        .where(Workspace.id == workspace_id)
        .options(
            selectinload(Workspace.memberships).selectinload(WorkspaceMembership.user),
            selectinload(Workspace.entitlements),
            selectinload(Workspace.subscription),
        )
    )
    return result.scalars().unique().one_or_none()


async def get_personal_workspace_for_user(
    db: AsyncSession,
    user_id: UUID,
) -> Workspace | None:
    """Return the user's default hosted personal workspace, if present."""

    result = await db.execute(
        select(Workspace)
        .join(WorkspaceMembership)
        .where(
            WorkspaceMembership.user_id == user_id,
            Workspace.plan == WorkspacePlan.PERSONAL,
            Workspace.deployment_mode == WorkspaceDeploymentMode.CLOUD,
        )
        .options(
            selectinload(Workspace.memberships).selectinload(WorkspaceMembership.user),
            selectinload(Workspace.entitlements),
            selectinload(Workspace.subscription),
        )
        .order_by(Workspace.created_at.asc(), Workspace.id.asc())
    )
    return result.scalars().unique().first()


async def ensure_personal_workspace_for_user(
    db: AsyncSession,
    user: User,
) -> Workspace:
    """Ensure the user has a personal workspace and legacy billing projection."""

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

    workspace = Workspace(
        name=default_personal_workspace_name(user.email),
        plan=WorkspacePlan.PERSONAL,
        deployment_mode=WorkspaceDeploymentMode.CLOUD,
        seat_limit=1,
        inference_config=get_default_workspace_inference_config(
            plan=WorkspacePlan.PERSONAL,
            deployment_mode=WorkspaceDeploymentMode.CLOUD,
        ),
    )
    db.add(workspace)

    membership = WorkspaceMembership(
        workspace=workspace,
        user=user,
        role=WorkspaceRole.OWNER,
    )
    db.add(membership)

    entitlements = WorkspaceEntitlement(
        workspace=workspace,
        **WorkspaceEntitlement.defaults_for_plan(WorkspacePlan.PERSONAL),
    )
    db.add(entitlements)

    subscription = build_workspace_subscription_from_user(user, workspace=workspace)
    if subscription is not None:
        db.add(subscription)

    await db.flush()
    return workspace


async def get_workspace_membership(
    db: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
) -> WorkspaceMembership | None:
    """Fetch the caller's membership for a workspace."""
    result = await db.execute(
        select(WorkspaceMembership)
        .where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
        .options(selectinload(WorkspaceMembership.user))
    )
    return result.scalar_one_or_none()


async def get_workspace_membership_by_id(
    db: AsyncSession,
    workspace_id: UUID,
    membership_id: UUID,
) -> WorkspaceMembership | None:
    """Fetch a specific membership inside a workspace."""
    result = await db.execute(
        select(WorkspaceMembership)
        .where(
            WorkspaceMembership.user_id == membership_id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
        .options(selectinload(WorkspaceMembership.user))
    )
    return result.scalar_one_or_none()


async def list_workspace_memberships(
    db: AsyncSession,
    workspace_id: UUID,
) -> list[WorkspaceMembership]:
    """List memberships for a workspace."""
    result = await db.execute(
        select(WorkspaceMembership)
        .where(WorkspaceMembership.workspace_id == workspace_id)
        .options(selectinload(WorkspaceMembership.user))
        .order_by(WorkspaceMembership.created_at.asc(), WorkspaceMembership.user_id.asc())
    )
    return list(result.scalars().all())


async def get_workspace_invitation_by_id(
    db: AsyncSession,
    workspace_id: UUID,
    invitation_id: UUID,
) -> WorkspaceInvitation | None:
    """Fetch one invitation scoped to a workspace."""
    result = await db.execute(
        select(WorkspaceInvitation)
        .where(
            WorkspaceInvitation.workspace_id == workspace_id,
            WorkspaceInvitation.id == invitation_id,
        )
        .options(
            selectinload(WorkspaceInvitation.workspace),
            selectinload(WorkspaceInvitation.invited_by_user),
        )
    )
    return result.scalar_one_or_none()


async def list_workspace_invitations(
    db: AsyncSession,
    workspace_id: UUID,
) -> list[WorkspaceInvitation]:
    """List active invitations for a workspace."""
    result = await db.execute(
        select(WorkspaceInvitation)
        .where(
            WorkspaceInvitation.workspace_id == workspace_id,
            WorkspaceInvitation.accepted_at.is_(None),
            WorkspaceInvitation.revoked_at.is_(None),
        )
        .options(
            selectinload(WorkspaceInvitation.workspace),
            selectinload(WorkspaceInvitation.invited_by_user),
        )
        .order_by(WorkspaceInvitation.created_at.asc(), WorkspaceInvitation.id.asc())
    )
    return list(result.scalars().all())


async def list_user_workspace_invitations(
    db: AsyncSession,
    email: str,
) -> list[WorkspaceInvitation]:
    """List active invitations addressed to a specific email address."""
    result = await db.execute(
        select(WorkspaceInvitation)
        .where(
            WorkspaceInvitation.invited_email == normalize_workspace_invitation_email(email),
            WorkspaceInvitation.accepted_at.is_(None),
            WorkspaceInvitation.revoked_at.is_(None),
        )
        .options(
            selectinload(WorkspaceInvitation.workspace),
            selectinload(WorkspaceInvitation.invited_by_user),
        )
        .order_by(WorkspaceInvitation.created_at.asc(), WorkspaceInvitation.id.asc())
    )
    return list(result.scalars().all())


async def create_workspace(
    db: AsyncSession,
    *,
    owner_user: User,
    name: str,
    plan: WorkspacePlan,
    deployment_mode: WorkspaceDeploymentMode,
    seat_limit: int | None,
    inference_config: dict | None = None,
) -> Workspace:
    """Create a workspace and the creator's owner membership."""
    plan, deployment_mode, seat_limit, inference_config = normalize_workspace_settings(
        plan=plan,
        deployment_mode=deployment_mode,
        seat_limit=seat_limit,
        inference_config=inference_config,
    )

    workspace = Workspace(
        name=name,
        plan=plan,
        deployment_mode=deployment_mode,
        seat_limit=seat_limit,
        inference_config=inference_config,
    )
    db.add(workspace)
    await db.flush()

    membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=owner_user.id,
        role=WorkspaceRole.OWNER,
    )
    db.add(membership)

    entitlements = WorkspaceEntitlement(
        workspace_id=workspace.id,
        **WorkspaceEntitlement.defaults_for_plan(plan),
    )
    db.add(entitlements)
    await db.flush()

    return workspace


async def bootstrap_workspace_for_user(
    db: AsyncSession,
    user: User,
) -> tuple[Workspace, bool]:
    """Ensure a user belongs to at least one workspace."""
    existing = await list_user_workspaces(db, user.id)
    if existing:
        return existing[0], False

    workspace = await create_workspace(
        db,
        owner_user=user,
        name=default_personal_workspace_name(user.email),
        plan=WorkspacePlan.PERSONAL,
        deployment_mode=WorkspaceDeploymentMode.CLOUD,
        seat_limit=1,
        inference_config=None,
    )
    return workspace, True


async def migrate_hosted_solo_user_to_personal_workspace(
    db: AsyncSession,
    user: User,
    *,
    dry_run: bool = False,
) -> HostedPersonalWorkspaceMigrationResult:
    """Create or repair hosted personal workspace state for one eligible user."""

    eligible, workspace, reasons = classify_hosted_solo_user_workspace_state(user)
    if not eligible:
        return HostedPersonalWorkspaceMigrationResult(
            user_id=user.id,
            email=user.email,
            action="skipped",
            workspace_id=None,
            eligible=False,
            reasons=reasons,
        )

    if workspace is None:
        projected_subscription = build_workspace_subscription_from_user(
            user,
            workspace=Workspace(
                name=default_personal_workspace_name(user.email),
                plan=WorkspacePlan.PERSONAL,
                deployment_mode=WorkspaceDeploymentMode.CLOUD,
                seat_limit=1,
                inference_config=get_default_workspace_inference_config(
                    plan=WorkspacePlan.PERSONAL,
                    deployment_mode=WorkspaceDeploymentMode.CLOUD,
                ),
            ),
        )
        subscription_needed = projected_subscription is not None

        if dry_run:
            return HostedPersonalWorkspaceMigrationResult(
                user_id=user.id,
                email=user.email,
                action="created",
                workspace_id=None,
                eligible=True,
                reasons=("missing_workspace",),
                workspace_created=True,
                membership_created=True,
                entitlements_created=True,
                subscription_created=subscription_needed,
            )

        created_workspace = await create_workspace(
            db,
            owner_user=user,
            name=default_personal_workspace_name(user.email),
            plan=WorkspacePlan.PERSONAL,
            deployment_mode=WorkspaceDeploymentMode.CLOUD,
            seat_limit=1,
            inference_config=None,
        )
        subscription = build_workspace_subscription_from_user(user, workspace=created_workspace)
        if subscription is not None:
            db.add(subscription)
        await db.flush()
        return HostedPersonalWorkspaceMigrationResult(
            user_id=user.id,
            email=user.email,
            action="created",
            workspace_id=created_workspace.id,
            eligible=True,
            reasons=("missing_workspace",),
            workspace_created=True,
            membership_created=True,
            entitlements_created=True,
            subscription_created=subscription is not None,
        )

    membership = _workspace_membership_for_user(user, workspace)
    reasons_list: list[str] = []
    membership_role_updated_from: str | None = None
    entitlements_created = False
    subscription_created = False

    if membership is not None and membership.role != WorkspaceRole.OWNER:
        membership_role_updated_from = membership.role.value
        reasons_list.append(f"membership_role:{membership.role.value}->owner")
        if not dry_run:
            membership.role = WorkspaceRole.OWNER

    if workspace.entitlements is None:
        reasons_list.append("missing_entitlements")
        entitlements_created = True
        if not dry_run:
            entitlements = WorkspaceEntitlement(
                workspace_id=workspace.id,
                **WorkspaceEntitlement.defaults_for_plan(WorkspacePlan.PERSONAL),
            )
            db.add(entitlements)
            workspace.entitlements = entitlements

    if workspace.subscription is None:
        subscription = build_workspace_subscription_from_user(user, workspace=workspace)
        if subscription is not None:
            reasons_list.append("missing_subscription_projection")
            subscription_created = True
            if not dry_run:
                db.add(subscription)
                workspace.subscription = subscription

    if not reasons_list:
        return HostedPersonalWorkspaceMigrationResult(
            user_id=user.id,
            email=user.email,
            action="unchanged",
            workspace_id=workspace.id,
            eligible=True,
            reasons=("already_valid",),
        )

    if not dry_run:
        await db.flush()

    return HostedPersonalWorkspaceMigrationResult(
        user_id=user.id,
        email=user.email,
        action="repaired",
        workspace_id=workspace.id,
        eligible=True,
        reasons=tuple(reasons_list),
        membership_role_updated_from=membership_role_updated_from,
        entitlements_created=entitlements_created,
        subscription_created=subscription_created,
    )


async def migrate_existing_hosted_solo_users_to_personal_workspaces(
    db: AsyncSession,
    *,
    emails: list[str] | None = None,
    dry_run: bool = False,
) -> HostedPersonalWorkspaceMigrationSummary:
    """Backfill hosted-solo users into hosted personal workspaces."""

    users = await list_hosted_personal_workspace_migration_users(db, emails=emails)
    results = tuple(
        [
            await migrate_hosted_solo_user_to_personal_workspace(db, user, dry_run=dry_run)
            for user in users
        ]
    )
    return HostedPersonalWorkspaceMigrationSummary(
        dry_run=dry_run,
        scanned_users=len(users),
        eligible_users=sum(1 for result in results if result.eligible),
        created_count=sum(1 for result in results if result.action == "created"),
        repaired_count=sum(1 for result in results if result.action == "repaired"),
        unchanged_count=sum(1 for result in results if result.action == "unchanged"),
        skipped_count=sum(1 for result in results if result.action == "skipped"),
        results=results,
    )


def _legacy_workspace_billing_validation_errors(
    user: User,
    workspace: Workspace,
) -> list[str]:
    errors: list[str] = []
    if not has_legacy_workspace_billing(user):
        return errors

    subscription = workspace.subscription
    if subscription is None:
        return ["missing_subscription_projection"]

    expected_status = _map_legacy_subscription_status(user)
    if subscription.status != expected_status:
        errors.append(f"subscription_status:{subscription.status.value}!={expected_status.value}")
    if user.stripe_customer_id and subscription.provider_customer_id != user.stripe_customer_id:
        errors.append("provider_customer_id_mismatch")
    if (
        user.stripe_subscription_id
        and subscription.provider_subscription_id != user.stripe_subscription_id
    ):
        errors.append("provider_subscription_id_mismatch")
    if (
        user.subscription_current_period_end is not None
        and subscription.current_period_end != user.subscription_current_period_end
    ):
        errors.append("current_period_end_mismatch")
    if user.trial_ends_at is not None and subscription.trial_ends_at != user.trial_ends_at:
        errors.append("trial_ends_at_mismatch")
    return errors


async def validate_hosted_solo_users_personal_workspaces(
    db: AsyncSession,
    *,
    emails: list[str] | None = None,
) -> HostedPersonalWorkspaceValidationSummary:
    """Validate that hosted-solo users are attached to usable personal workspaces."""

    users = await list_hosted_personal_workspace_migration_users(db, emails=emails)
    results: list[HostedPersonalWorkspaceValidationResult] = []

    for user in users:
        eligible, workspace, reasons = classify_hosted_solo_user_workspace_state(user)
        if not eligible:
            results.append(
                HostedPersonalWorkspaceValidationResult(
                    user_id=user.id,
                    email=user.email,
                    status="skipped",
                    workspace_id=None,
                    eligible=False,
                    reasons=reasons,
                )
            )
            continue

        errors: list[str] = []
        if workspace is None:
            errors.append("missing_personal_workspace")
        else:
            membership = _workspace_membership_for_user(user, workspace)
            if membership is None:
                errors.append("missing_workspace_membership")
            elif membership.role != WorkspaceRole.OWNER:
                errors.append(f"membership_role:{membership.role.value}")
            if workspace.entitlements is None:
                errors.append("missing_entitlements")
            errors.extend(_legacy_workspace_billing_validation_errors(user, workspace))

        results.append(
            HostedPersonalWorkspaceValidationResult(
                user_id=user.id,
                email=user.email,
                status="invalid" if errors else "valid",
                workspace_id=None if workspace is None else workspace.id,
                eligible=True,
                errors=tuple(errors),
            )
        )

    frozen_results = tuple(results)
    return HostedPersonalWorkspaceValidationSummary(
        scanned_users=len(users),
        eligible_users=sum(1 for result in frozen_results if result.eligible),
        valid_count=sum(1 for result in frozen_results if result.status == "valid"),
        invalid_count=sum(1 for result in frozen_results if result.status == "invalid"),
        skipped_count=sum(1 for result in frozen_results if result.status == "skipped"),
        results=frozen_results,
    )


async def update_workspace(
    db: AsyncSession,
    workspace: Workspace,
    *,
    name: str | None = None,
    plan: WorkspacePlan | None = None,
    deployment_mode: WorkspaceDeploymentMode | None = None,
    seat_limit: int | None = None,
    inference_config: dict | None = None,
) -> Workspace:
    """Update mutable workspace fields."""
    if "entitlements" in inspect(workspace).unloaded:
        await db.refresh(workspace, attribute_names=["entitlements"])

    previous_plan = workspace.plan
    next_plan = plan or workspace.plan
    next_deployment_mode = deployment_mode or workspace.deployment_mode
    requested_seat_limit = seat_limit
    if requested_seat_limit is None and next_plan == workspace.plan:
        requested_seat_limit = workspace.seat_limit
    next_plan, next_deployment_mode, next_seat_limit, next_inference_config = (
        normalize_workspace_settings(
            plan=next_plan,
            deployment_mode=next_deployment_mode,
            seat_limit=requested_seat_limit,
            inference_config=inference_config or workspace.inference_config,
            keep_unsupported_managed_mode=inference_config is None,
        )
    )

    occupied_seat_count = await count_workspace_occupied_seats(db, workspace.id)
    if next_seat_limit < occupied_seat_count:
        raise ValueError(
            "Workspace seat limit cannot be less than the current occupied seat count "
            f"({occupied_seat_count})"
        )

    if name is not None:
        workspace.name = name
    workspace.plan = next_plan
    workspace.deployment_mode = next_deployment_mode
    workspace.seat_limit = next_seat_limit
    workspace.inference_config = next_inference_config

    entitlements = (
        workspace.entitlements
        if "entitlements" in workspace.__dict__
        else await db.get(WorkspaceEntitlement, workspace.id)
    )
    if entitlements is None:
        entitlements = WorkspaceEntitlement(
            workspace_id=workspace.id, **WorkspaceEntitlement.defaults_for_plan(next_plan)
        )
        db.add(entitlements)
        workspace.entitlements = entitlements
    elif next_plan != previous_plan:
        for field_name, value in WorkspaceEntitlement.defaults_for_plan(next_plan).items():
            setattr(entitlements, field_name, value)

    await db.flush()
    return workspace


async def upgrade_personal_workspace_to_team(
    db: AsyncSession,
    workspace: Workspace,
    *,
    name: str | None = None,
    seat_limit: int | None = None,
    deployment_mode: WorkspaceDeploymentMode | None = None,
    inference_config: dict | None = None,
) -> Workspace:
    """Convert a hosted personal workspace into a team workspace in place."""
    if workspace.plan != WorkspacePlan.PERSONAL:
        raise ValueError("Only personal workspaces can be upgraded to team")

    return await update_workspace(
        db,
        workspace,
        name=name,
        plan=WorkspacePlan.TEAM,
        seat_limit=seat_limit,
        deployment_mode=deployment_mode,
        inference_config=inference_config,
    )


async def add_workspace_member(
    db: AsyncSession,
    *,
    workspace: Workspace,
    user: User,
    role: WorkspaceRole,
    reserved_invitation_id: UUID | None = None,
) -> WorkspaceMembership:
    """Add a member to a workspace, enforcing uniqueness and seat limits."""
    existing = await get_workspace_membership(db, workspace.id, user.id)
    if existing:
        raise ValueError("User is already a member of this workspace")

    occupied_seat_count = await count_workspace_occupied_seats(
        db,
        workspace.id,
        excluded_invitation_id=reserved_invitation_id,
    )
    if occupied_seat_count >= workspace.seat_limit:
        raise ValueError("Workspace seat limit reached")

    membership = WorkspaceMembership(
        workspace_id=workspace.id,
        user_id=user.id,
        role=role,
    )
    db.add(membership)
    await db.flush()
    await db.refresh(membership, ["user"])
    return membership


async def count_workspace_invitations(
    db: AsyncSession,
    workspace_id: UUID,
    *,
    excluded_invitation_id: UUID | None = None,
) -> int:
    """Count active invitations in a workspace."""
    invitation_filters = [
        WorkspaceInvitation.workspace_id == workspace_id,
        WorkspaceInvitation.accepted_at.is_(None),
        WorkspaceInvitation.revoked_at.is_(None),
    ]
    if excluded_invitation_id is not None:
        invitation_filters.append(WorkspaceInvitation.id != excluded_invitation_id)

    return (
        await db.scalar(
            select(func.count()).select_from(WorkspaceInvitation).where(*invitation_filters)
        )
        or 0
    )


async def count_workspace_occupied_seats(
    db: AsyncSession,
    workspace_id: UUID,
    *,
    excluded_invitation_id: UUID | None = None,
) -> int:
    """Count current seats consumed by memberships and active invitations."""
    member_count = await count_workspace_members(db, workspace_id)
    invitation_count = await count_workspace_invitations(
        db,
        workspace_id,
        excluded_invitation_id=excluded_invitation_id,
    )
    return member_count + invitation_count


async def create_workspace_invitation(
    db: AsyncSession,
    *,
    workspace: Workspace,
    invited_by_user: User,
    invited_email: str,
    role: WorkspaceRole,
) -> WorkspaceInvitation:
    """Create a pending invitation for a team-capable workspace."""
    normalized_email = normalize_workspace_invitation_email(invited_email)
    if not normalized_email:
        raise ValueError("Invitation email is required")
    if invited_by_user.email and normalized_email == normalize_workspace_invitation_email(
        invited_by_user.email
    ):
        raise ValueError("You cannot invite your own email address")
    if workspace.entitlements is None or not workspace.entitlements.invite_members:
        raise ValueError("Workspace plan does not allow member invitations")

    target_user_result = await db.execute(select(User).where(User.email == normalized_email))
    target_user = target_user_result.scalar_one_or_none()
    if target_user is not None:
        existing = await get_workspace_membership(db, workspace.id, target_user.id)
        if existing is not None:
            raise ValueError("User is already a member of this workspace")

    existing_invite_result = await db.execute(
        select(WorkspaceInvitation).where(
            WorkspaceInvitation.workspace_id == workspace.id,
            WorkspaceInvitation.invited_email == normalized_email,
            WorkspaceInvitation.accepted_at.is_(None),
            WorkspaceInvitation.revoked_at.is_(None),
        )
    )
    if existing_invite_result.scalar_one_or_none() is not None:
        raise ValueError("An active invitation already exists for this email")

    occupied_seat_count = await count_workspace_occupied_seats(db, workspace.id)
    if occupied_seat_count >= workspace.seat_limit:
        raise ValueError("Workspace seat limit reached")

    invitation = WorkspaceInvitation(
        workspace_id=workspace.id,
        invited_by_user_id=invited_by_user.id,
        invited_email=normalized_email,
        role=role,
    )
    db.add(invitation)
    await db.flush()
    await db.refresh(invitation, ["workspace", "invited_by_user"])
    return invitation


async def accept_workspace_invitation(
    db: AsyncSession,
    *,
    invitation: WorkspaceInvitation,
    user: User,
) -> WorkspaceMembership:
    """Accept a pending workspace invitation for the authenticated user."""
    if invitation.accepted_at is not None or invitation.revoked_at is not None:
        raise ValueError("Invitation is no longer active")
    if (
        not user.email
        or normalize_workspace_invitation_email(user.email) != invitation.invited_email
    ):
        raise ValueError("Invitation is not addressed to the current user")

    workspace = await get_workspace_by_id(db, invitation.workspace_id)
    if workspace is None:
        raise ValueError("Workspace not found")
    if workspace.entitlements is None or not workspace.entitlements.invite_members:
        raise ValueError("Workspace plan does not allow member invitations")

    membership = await add_workspace_member(
        db,
        workspace=workspace,
        user=user,
        role=invitation.role,
        reserved_invitation_id=invitation.id,
    )
    invitation.accepted_at = datetime.now(timezone.utc)
    invitation.accepted_by_user_id = user.id
    await db.flush()
    return membership


async def revoke_workspace_invitation(
    db: AsyncSession,
    *,
    invitation: WorkspaceInvitation,
    revoked_by_user_id: UUID,
) -> WorkspaceInvitation:
    """Revoke a pending workspace invitation."""
    if invitation.accepted_at is not None or invitation.revoked_at is not None:
        raise ValueError("Invitation is no longer active")
    invitation.revoked_at = datetime.now(timezone.utc)
    invitation.revoked_by_user_id = revoked_by_user_id
    await db.flush()
    return invitation


async def update_workspace_membership_role(
    db: AsyncSession,
    membership: WorkspaceMembership,
    role: WorkspaceRole,
) -> WorkspaceMembership:
    """Update a member's role, preventing a workspace from losing its last owner."""
    if membership.role == role:
        return membership

    if membership.role == WorkspaceRole.OWNER and role != WorkspaceRole.OWNER:
        owner_count = await count_workspace_owners(db, membership.workspace_id)
        if owner_count <= 1:
            raise ValueError("Workspace must retain at least one owner")

    membership.role = role
    await db.flush()
    await db.refresh(membership, ["user"])
    return membership


async def remove_workspace_membership(
    db: AsyncSession,
    membership: WorkspaceMembership,
) -> None:
    """Remove a user from a workspace without violating ownership or bootstrap invariants."""
    if membership.role == WorkspaceRole.OWNER:
        owner_count = await count_workspace_owners(db, membership.workspace_id)
        if owner_count <= 1:
            raise ValueError("Workspace must retain at least one owner")

    remaining_workspaces = await count_user_other_workspaces(
        db,
        user_id=membership.user_id,
        excluded_workspace_id=membership.workspace_id,
    )
    if remaining_workspaces <= 0:
        raise ValueError("Removing this membership would leave the user with no workspaces")

    await db.delete(membership)
    await db.flush()


async def delete_workspace(
    db: AsyncSession,
    workspace: Workspace,
) -> None:
    """Delete a workspace when all members still belong to another workspace."""
    memberships = await list_workspace_memberships(db, workspace.id)
    for membership in memberships:
        remaining_workspaces = await count_user_other_workspaces(
            db,
            user_id=membership.user_id,
            excluded_workspace_id=workspace.id,
        )
        if remaining_workspaces <= 0:
            raise ValueError(
                "Deleting this workspace would leave at least one user without any workspace"
            )

    await db.delete(workspace)
    await db.flush()


async def count_workspace_members(db: AsyncSession, workspace_id: UUID) -> int:
    """Count members in a workspace."""
    return (
        await db.scalar(
            select(func.count())
            .select_from(WorkspaceMembership)
            .where(WorkspaceMembership.workspace_id == workspace_id)
        )
        or 0
    )


async def count_workspace_owners(db: AsyncSession, workspace_id: UUID) -> int:
    """Count owners in a workspace."""
    return (
        await db.scalar(
            select(func.count())
            .select_from(WorkspaceMembership)
            .where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.role == WorkspaceRole.OWNER,
            )
        )
        or 0
    )


async def count_user_other_workspaces(
    db: AsyncSession,
    *,
    user_id: UUID,
    excluded_workspace_id: UUID,
) -> int:
    """Count the user's memberships outside a specific workspace."""
    return (
        await db.scalar(
            select(func.count())
            .select_from(WorkspaceMembership)
            .where(
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.workspace_id != excluded_workspace_id,
            )
        )
        or 0
    )
