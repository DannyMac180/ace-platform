"""Workspace service layer.

Provides CRUD helpers, membership management, and bootstrap flows that enforce
the hosted-workspace invariants for cloud users.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ace_platform.db.models import (
    User,
    Workspace,
    WorkspaceDeploymentMode,
    WorkspaceEntitlement,
    WorkspaceInferenceMode,
    WorkspaceInferenceProvider,
    WorkspaceMembership,
    WorkspacePlan,
    WorkspaceRole,
    get_default_workspace_entitlements,
    get_default_workspace_inference_config,
    workspace_supports_managed_inference,
)

MANAGER_ROLES = {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}
DEFAULT_TEAM_WORKSPACE_SEAT_LIMIT = 5
APPROVER_ROLES = {WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.REVIEWER}


@dataclass(frozen=True)
class WorkspacePermissions:
    """Effective role-based permissions for one workspace member."""

    can_manage_settings: bool
    can_manage_seats: bool
    can_approve_playbooks: bool


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

    member_count = await count_workspace_members(db, workspace.id)
    if next_seat_limit < member_count:
        raise ValueError(
            f"Workspace seat limit cannot be less than the current membership count ({member_count})"
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
) -> WorkspaceMembership:
    """Add a member to a workspace, enforcing uniqueness and seat limits."""
    existing = await get_workspace_membership(db, workspace.id, user.id)
    if existing:
        raise ValueError("User is already a member of this workspace")

    member_count = await count_workspace_members(db, workspace.id)
    if member_count >= workspace.seat_limit:
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
