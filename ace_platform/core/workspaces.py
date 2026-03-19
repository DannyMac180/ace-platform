"""Workspace service layer.

Provides CRUD helpers, membership management, and bootstrap flows that enforce
the hosted-workspace invariants for cloud users.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ace_platform.db.models import (
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
    get_default_workspace_inference_config,
    workspace_supports_managed_inference,
)

MANAGER_ROLES = {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}


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
    resolved_seat_limit = seat_limit if seat_limit is not None else 1
    if resolved_seat_limit < 1:
        raise ValueError("Workspace seat limit must be at least 1")

    if plan == WorkspacePlan.PERSONAL:
        resolved_seat_limit = 1

    resolved_inference_config = normalize_workspace_inference_config(
        plan=plan,
        deployment_mode=deployment_mode,
        inference_config=inference_config,
        keep_unsupported_managed_mode=keep_unsupported_managed_mode,
    )

    return plan, deployment_mode, resolved_seat_limit, resolved_inference_config


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
    requested_seat_limit = seat_limit if seat_limit is not None else workspace.seat_limit
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

    if workspace.entitlements is None:
        workspace.entitlements = WorkspaceEntitlement(
            **WorkspaceEntitlement.defaults_for_plan(next_plan)
        )
    elif next_plan != previous_plan:
        for field_name, value in WorkspaceEntitlement.defaults_for_plan(next_plan).items():
            setattr(workspace.entitlements, field_name, value)

    await db.flush()
    return workspace


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
