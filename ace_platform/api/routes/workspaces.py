"""Workspace service and entitlement routes."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.api.auth import RequiredUser
from ace_platform.api.deps import get_db
from ace_platform.core.entitlements import (
    WorkspaceEntitlementsSnapshot,
    get_workspace_id,
    resolve_workspace_entitlements,
)
from ace_platform.core.workspaces import (
    MANAGER_ROLES,
    add_workspace_member,
    bootstrap_workspace_for_user,
    create_workspace,
    delete_workspace,
    get_default_workspace_for_user,
    get_workspace_for_user,
    get_workspace_membership,
    get_workspace_membership_by_id,
    list_user_workspaces,
    list_workspace_memberships,
    remove_workspace_membership,
    update_workspace,
    update_workspace_membership_role,
)
from ace_platform.db.models import (
    User,
    Workspace,
    WorkspaceDeploymentMode,
    WorkspacePlan,
    WorkspaceRole,
)

router = APIRouter(tags=["workspaces"])

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = RequiredUser


class WorkspaceCreateRequest(BaseModel):
    """Request body for creating a workspace."""

    name: str = Field(..., min_length=1, max_length=255)
    plan: WorkspacePlan = Field(default=WorkspacePlan.PERSONAL)
    deployment_mode: WorkspaceDeploymentMode = Field(default=WorkspaceDeploymentMode.CLOUD)
    seat_limit: int | None = Field(default=None, ge=1)


class WorkspaceUpdateRequest(BaseModel):
    """Request body for updating a workspace."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    plan: WorkspacePlan | None = None
    deployment_mode: WorkspaceDeploymentMode | None = None
    seat_limit: int | None = Field(default=None, ge=1)


class WorkspaceMembershipCreateRequest(BaseModel):
    """Request body for adding a workspace member."""

    user_id: UUID | None = None
    user_email: str | None = Field(default=None, max_length=255)
    role: WorkspaceRole = Field(default=WorkspaceRole.MEMBER)

    @model_validator(mode="after")
    def validate_lookup(self) -> WorkspaceMembershipCreateRequest:
        """Require either a user ID or email."""
        if not self.user_id and not self.user_email:
            raise ValueError("Either user_id or user_email is required")
        return self


class WorkspaceMembershipUpdateRequest(BaseModel):
    """Request body for updating a workspace member."""

    role: WorkspaceRole


class WorkspaceResponse(BaseModel):
    """Serialized workspace."""

    id: UUID
    name: str
    plan: WorkspacePlan
    deployment_mode: WorkspaceDeploymentMode
    seat_limit: int
    member_count: int
    current_user_role: WorkspaceRole


class WorkspaceMembershipResponse(BaseModel):
    """Serialized workspace membership."""

    id: UUID
    workspace_id: UUID
    user_id: UUID
    user_email: str
    role: WorkspaceRole


class WorkspaceBootstrapResponse(BaseModel):
    """Bootstrap response for the current user."""

    created: bool
    workspaces: list[WorkspaceResponse]


class WorkspaceFeatureAccessResponse(BaseModel):
    """API response model for workspace feature flags."""

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


class WorkspaceUsageLimitsResponse(BaseModel):
    """API response model for workspace usage limits and current usage."""

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


class WorkspaceEntitlementsResponse(BaseModel):
    """API response model for one workspace entitlement snapshot."""

    workspace_id: str
    plan: Literal["personal", "team", "enterprise"]
    deployment_mode: Literal["cloud", "self_hosted"]
    seat_limit: int | None
    enabled_features: list[str]
    access: WorkspaceAccessResponse
    entitlements: WorkspaceFeatureAccessResponse
    usage_limits: WorkspaceUsageLimitsResponse


class WorkspaceAccessResponse(BaseModel):
    """API response model for subscription-derived access state."""

    subscription_tier: str
    subscription_status: str
    effective_tier: str
    has_feature_access: bool
    is_trialing: bool


ENTITLEMENT_FIELDS = (
    "cloud_sync",
    "hosted_backups",
    "managed_inference",
    "hosted_evals",
    "invite_members",
    "shared_workspace",
    "approvals",
    "rbac",
    "sso",
    "audit_logs",
)


def _serialize_workspace(workspace: Workspace, current_user_id: UUID) -> WorkspaceResponse:
    """Serialize a workspace with the caller's role."""
    current_membership = next(
        (
            membership
            for membership in workspace.memberships
            if membership.user_id == current_user_id
        ),
        None,
    )
    if current_membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        plan=workspace.plan,
        deployment_mode=workspace.deployment_mode,
        seat_limit=workspace.seat_limit,
        member_count=len(workspace.memberships),
        current_user_role=current_membership.role,
    )


def _serialize_membership(membership) -> WorkspaceMembershipResponse:
    """Serialize a workspace membership."""
    return WorkspaceMembershipResponse(
        id=membership.id,
        workspace_id=membership.workspace_id,
        user_id=membership.user_id,
        user_email=membership.user.email,
        role=membership.role,
    )


async def _resolve_entitlements_workspace(
    db: AsyncSession,
    current_user: User,
    workspace_id: str,
) -> Workspace | None:
    """Resolve a concrete workspace id for entitlement lookups."""
    if workspace_id in {"personal", "me", get_workspace_id(current_user)}:
        return await get_default_workspace_for_user(db, current_user.id)

    try:
        parsed_workspace_id = UUID(workspace_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        ) from exc

    workspace = await get_workspace_for_user(db, parsed_workspace_id, current_user.id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this workspace.",
        )
    return workspace


def _to_response(
    snapshot: WorkspaceEntitlementsSnapshot,
    workspace: Workspace | None = None,
) -> WorkspaceEntitlementsResponse:
    """Serialize the core entitlement snapshot into the route response model."""
    entitlements_source = workspace.entitlements if workspace is not None else None
    feature_values: dict[str, bool] = {}
    for field_name in ENTITLEMENT_FIELDS:
        if entitlements_source is None:
            feature_values[field_name] = bool(getattr(snapshot.entitlements, field_name))
            continue

        feature_values[field_name] = (
            bool(getattr(entitlements_source, field_name)) and snapshot.access.has_feature_access
        )

    workspace_id = snapshot.workspace_id
    plan = snapshot.plan
    deployment_mode = snapshot.deployment_mode
    seat_limit = snapshot.seat_limit
    if workspace is not None:
        workspace_id = str(workspace.id)
        plan = workspace.plan.value
        deployment_mode = workspace.deployment_mode.value
        seat_limit = workspace.seat_limit

    return WorkspaceEntitlementsResponse(
        workspace_id=workspace_id,
        plan=plan,
        deployment_mode=deployment_mode,
        seat_limit=seat_limit,
        enabled_features=[name for name in ENTITLEMENT_FIELDS if feature_values[name]],
        access=WorkspaceAccessResponse(
            subscription_tier=snapshot.access.subscription_tier.value,
            subscription_status=snapshot.access.subscription_status.value,
            effective_tier=snapshot.access.effective_tier.value,
            has_feature_access=snapshot.access.has_feature_access,
            is_trialing=snapshot.access.is_trialing,
        ),
        entitlements=WorkspaceFeatureAccessResponse(**feature_values),
        usage_limits=WorkspaceUsageLimitsResponse(
            monthly_evolution_runs=snapshot.usage_limits.monthly_evolution_runs,
            current_evolution_runs=snapshot.usage_limits.current_evolution_runs,
            remaining_evolution_runs=snapshot.usage_limits.remaining_evolution_runs,
            monthly_cost_limit_usd=snapshot.usage_limits.monthly_cost_limit_usd,
            current_cost_usd=snapshot.usage_limits.current_cost_usd,
            remaining_cost_usd=snapshot.usage_limits.remaining_cost_usd,
            current_total_tokens=snapshot.usage_limits.current_total_tokens,
            max_playbooks=snapshot.usage_limits.max_playbooks,
            is_within_limits=snapshot.usage_limits.is_within_limits,
            limit_exceeded=snapshot.usage_limits.limit_exceeded,
        ),
    )


def _ensure_manager(membership) -> None:
    """Require a manager-capable workspace role."""
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    if membership.role not in MANAGER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace owner or admin role required",
        )


async def _require_workspace_membership(
    db: AsyncSession,
    workspace_id: UUID,
    current_user: User,
):
    """Fetch the caller's workspace membership or return 404."""
    membership = await get_workspace_membership(db, workspace_id, current_user.id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return membership


async def _resolve_user(
    db: AsyncSession,
    user_id: UUID | None,
    user_email: str | None,
) -> User:
    """Resolve a target user by ID or email."""
    target_user = None
    if user_id is not None:
        target_user = await db.get(User, user_id)
    elif user_email is not None:
        result = await db.execute(select(User).where(User.email == user_email.lower()))
        target_user = result.scalar_one_or_none()

    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return target_user


@router.get("/workspaces", response_model=list[WorkspaceResponse])
async def list_workspaces(
    db: DbSession,
    current_user: CurrentUser,
) -> list[WorkspaceResponse]:
    """List workspaces for the authenticated user."""
    _, created = await bootstrap_workspace_for_user(db, current_user)
    if created:
        await db.commit()

    workspaces = await list_user_workspaces(db, current_user.id)
    return [_serialize_workspace(workspace, current_user.id) for workspace in workspaces]


@router.post("/workspaces/bootstrap", response_model=WorkspaceBootstrapResponse)
async def bootstrap_workspaces(
    db: DbSession,
    current_user: CurrentUser,
) -> WorkspaceBootstrapResponse:
    """Ensure the current user belongs to at least one workspace."""
    _, created = await bootstrap_workspace_for_user(db, current_user)
    await db.commit()

    workspaces = await list_user_workspaces(db, current_user.id)
    return WorkspaceBootstrapResponse(
        created=created,
        workspaces=[_serialize_workspace(workspace, current_user.id) for workspace in workspaces],
    )


@router.post("/workspaces", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace_route(
    payload: WorkspaceCreateRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkspaceResponse:
    """Create a workspace owned by the current user."""
    workspace = await create_workspace(
        db,
        owner_user=current_user,
        name=payload.name,
        plan=payload.plan,
        deployment_mode=payload.deployment_mode,
        seat_limit=payload.seat_limit,
    )
    await db.commit()

    workspace = await get_workspace_for_user(db, workspace.id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return _serialize_workspace(workspace, current_user.id)


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace_route(
    workspace_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkspaceResponse:
    """Get a workspace visible to the current user."""
    workspace = await get_workspace_for_user(db, workspace_id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return _serialize_workspace(workspace, current_user.id)


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace_route(
    workspace_id: UUID,
    payload: WorkspaceUpdateRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkspaceResponse:
    """Update a workspace managed by the current user."""
    membership = await _require_workspace_membership(db, workspace_id, current_user)
    _ensure_manager(membership)

    workspace = await get_workspace_for_user(db, workspace_id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    try:
        await update_workspace(
            db,
            workspace,
            name=payload.name,
            plan=payload.plan,
            deployment_mode=payload.deployment_mode,
            seat_limit=payload.seat_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await db.commit()
    workspace = await get_workspace_for_user(db, workspace_id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return _serialize_workspace(workspace, current_user.id)


@router.delete("/workspaces/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace_route(
    workspace_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    """Delete a workspace when every member still belongs to another workspace."""
    membership = await _require_workspace_membership(db, workspace_id, current_user)
    _ensure_manager(membership)

    workspace = await get_workspace_for_user(db, workspace_id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    try:
        await delete_workspace(db, workspace)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await db.commit()


@router.get(
    "/workspaces/{workspace_id}/memberships",
    response_model=list[WorkspaceMembershipResponse],
)
async def list_workspace_memberships_route(
    workspace_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> list[WorkspaceMembershipResponse]:
    """List memberships for a workspace visible to the current user."""
    await _require_workspace_membership(db, workspace_id, current_user)
    memberships = await list_workspace_memberships(db, workspace_id)
    return [_serialize_membership(membership) for membership in memberships]


@router.post(
    "/workspaces/{workspace_id}/memberships",
    response_model=WorkspaceMembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_workspace_membership_route(
    workspace_id: UUID,
    payload: WorkspaceMembershipCreateRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkspaceMembershipResponse:
    """Add a member to a workspace."""
    membership = await _require_workspace_membership(db, workspace_id, current_user)
    _ensure_manager(membership)

    workspace = await get_workspace_for_user(db, workspace_id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    target_user = await _resolve_user(db, payload.user_id, payload.user_email)
    try:
        created_membership = await add_workspace_member(
            db,
            workspace=workspace,
            user=target_user,
            role=payload.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await db.commit()
    return _serialize_membership(created_membership)


@router.patch(
    "/workspaces/{workspace_id}/memberships/{membership_id}",
    response_model=WorkspaceMembershipResponse,
)
async def update_workspace_membership_route(
    workspace_id: UUID,
    membership_id: UUID,
    payload: WorkspaceMembershipUpdateRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkspaceMembershipResponse:
    """Update a member role inside a workspace."""
    membership = await _require_workspace_membership(db, workspace_id, current_user)
    _ensure_manager(membership)

    target_membership = await get_workspace_membership_by_id(db, workspace_id, membership_id)
    if target_membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")

    try:
        updated = await update_workspace_membership_role(db, target_membership, payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await db.commit()
    return _serialize_membership(updated)


@router.delete(
    "/workspaces/{workspace_id}/memberships/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_workspace_membership_route(
    workspace_id: UUID,
    membership_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    """Remove a member from a workspace."""
    membership = await _require_workspace_membership(db, workspace_id, current_user)
    _ensure_manager(membership)

    target_membership = await get_workspace_membership_by_id(db, workspace_id, membership_id)
    if target_membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")

    try:
        await remove_workspace_membership(db, target_membership)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await db.commit()


@router.get(
    "/v1/workspaces/{workspace_id}/entitlements",
    response_model=WorkspaceEntitlementsResponse,
)
@router.get(
    "/workspaces/{workspace_id}/entitlements",
    response_model=WorkspaceEntitlementsResponse,
    include_in_schema=False,
)
async def get_workspace_entitlements(
    workspace_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkspaceEntitlementsResponse:
    """Return authoritative feature access for the caller's cloud workspace."""
    workspace = await _resolve_entitlements_workspace(db, current_user, workspace_id)
    snapshot = await resolve_workspace_entitlements(db, current_user)
    return _to_response(snapshot, workspace)
