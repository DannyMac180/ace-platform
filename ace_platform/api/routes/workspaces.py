"""Workspace, sync, hosted eval, and entitlement routes."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ace_core.contracts import InferenceMessage, ModelRequest
from ace_core.portability import PortablePlaybook
from ace_platform.api.auth import PaidUser, RequiredUser, require_capability
from ace_platform.api.deps import get_db
from ace_platform.api.routes.playbooks import PlaybookResponse, PlaybookVersionResponse
from ace_platform.core.entitlements import (
    WorkspaceEntitlementsSnapshot,
    get_workspace_id,
    resolve_workspace_entitlements,
)
from ace_platform.core.limits import (
    check_can_evolve,
    get_effective_tier_for_limits,
    is_user_trialing,
)
from ace_platform.core.logging import get_logger
from ace_platform.core.managed_inference import (
    ManagedInferenceConfigurationError,
    ManagedInferenceGateway,
    ManagedInferenceProviderError,
    ManagedInferenceRequestError,
)
from ace_platform.core.playbooks import (
    PlaybookLimitError,
    list_shared_workspace_playbooks,
    reuse_shared_workspace_playbook,
)
from ace_platform.core.workspace_sync import (
    WorkspaceSyncConflictError,
    apply_playbook_sync_delete,
    apply_playbook_sync_upsert,
    encode_sync_cursor,
    ensure_personal_sync_workspace,
    list_workspace_sync_events,
)
from ace_platform.core.workspaces import (
    accept_workspace_invitation,
    add_workspace_member,
    bootstrap_workspace_for_user,
    create_workspace,
    create_workspace_invitation,
    delete_workspace,
    get_default_workspace_for_user,
    get_personal_workspace_for_user,
    get_workspace_by_id,
    get_workspace_for_user,
    get_workspace_invitation_by_id,
    get_workspace_membership,
    get_workspace_membership_by_id,
    list_user_workspace_invitations,
    list_user_workspaces,
    list_workspace_invitations,
    list_workspace_memberships,
    remove_workspace_membership,
    resolve_workspace_permissions,
    revoke_workspace_invitation,
    update_workspace,
    update_workspace_membership_role,
    upgrade_personal_workspace_to_team,
)
from ace_platform.db.models import (
    EvolutionJob,
    EvolutionJobStatus,
    Playbook,
    PlaybookSource,
    PlaybookStatus,
    PlaybookVersion,
    User,
    Workspace,
    WorkspaceDeploymentMode,
    WorkspaceInferenceMode,
    WorkspaceInferenceProvider,
    WorkspaceInvitation,
    WorkspacePlan,
    WorkspaceRole,
)

router = APIRouter(tags=["workspaces"])
logger = get_logger(__name__)

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = RequiredUser
HostedEvalUser = Annotated[User, Depends(require_capability("hosted_evals"))]
ManagedInferenceUser = Annotated[User, Depends(require_capability("managed_inference"))]


class WorkspaceCreateRequest(BaseModel):
    """Request body for creating a workspace."""

    name: str = Field(..., min_length=1, max_length=255)
    plan: WorkspacePlan = Field(default=WorkspacePlan.PERSONAL)
    deployment_mode: WorkspaceDeploymentMode = Field(default=WorkspaceDeploymentMode.CLOUD)
    seat_limit: int | None = Field(default=None, ge=1)
    inference_config: WorkspaceInferenceConfigRequest | None = None


class WorkspaceUpdateRequest(BaseModel):
    """Request body for updating a workspace."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    plan: WorkspacePlan | None = None
    deployment_mode: WorkspaceDeploymentMode | None = None
    seat_limit: int | None = Field(default=None, ge=1)
    inference_config: WorkspaceInferenceConfigRequest | None = None


class WorkspaceUpgradeToTeamRequest(BaseModel):
    """Request body for converting a personal workspace into a team workspace."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    seat_limit: int | None = Field(default=None, ge=2)


class WorkspaceInferenceConfigRequest(BaseModel):
    """Incoming workspace inference configuration."""

    mode: WorkspaceInferenceMode
    provider: WorkspaceInferenceProvider = WorkspaceInferenceProvider.OPENAI


class WorkspaceInferenceConfigResponse(BaseModel):
    """Serialized workspace inference configuration."""

    mode: WorkspaceInferenceMode
    provider: WorkspaceInferenceProvider
    available_modes: list[WorkspaceInferenceMode]


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


class WorkspacePermissionsResponse(BaseModel):
    """Serialized effective workspace permissions for the current user."""

    can_manage_settings: bool
    can_manage_seats: bool
    can_approve_playbooks: bool


class WorkspaceResponse(BaseModel):
    """Serialized workspace."""

    id: UUID
    name: str
    plan: WorkspacePlan
    deployment_mode: WorkspaceDeploymentMode
    seat_limit: int
    inference_config: WorkspaceInferenceConfigResponse
    member_count: int
    current_user_role: WorkspaceRole
    permissions: WorkspacePermissionsResponse


class WorkspaceMembershipResponse(BaseModel):
    """Serialized workspace membership."""

    id: UUID
    workspace_id: UUID
    user_id: UUID
    user_email: str
    role: WorkspaceRole


class WorkspaceInvitationCreateRequest(BaseModel):
    """Request body for inviting a workspace member."""

    email: EmailStr = Field(..., max_length=255)
    role: WorkspaceRole = Field(default=WorkspaceRole.MEMBER)


class WorkspaceInvitationResponse(BaseModel):
    """Serialized workspace invitation."""

    id: UUID
    workspace_id: UUID
    workspace_name: str
    invited_email: str
    role: WorkspaceRole
    invited_by_user_id: UUID
    invited_by_email: str
    created_at: datetime


class SharedPlaybookOwnerResponse(BaseModel):
    """Ownership metadata for one shared registry entry."""

    user_id: UUID
    email: str


class WorkspaceSharedPlaybookResponse(BaseModel):
    """Serialized shared playbook entry for the team registry."""

    id: UUID
    name: str
    description: str | None
    status: PlaybookStatus
    source: PlaybookSource
    created_at: datetime
    updated_at: datetime
    version_count: int
    outcome_count: int
    owner: SharedPlaybookOwnerResponse
    is_owned_by_current_user: bool


class PaginatedWorkspaceSharedPlaybookResponse(BaseModel):
    """Paginated shared playbook catalog response."""

    items: list[WorkspaceSharedPlaybookResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class WorkspaceBootstrapResponse(BaseModel):
    """Bootstrap response for the current user."""

    created: bool
    workspaces: list[WorkspaceResponse]


class HostedEvalRunRequest(BaseModel):
    """Request body for launching a hosted eval run."""

    playbook_id: UUID


class HostedEvalRunVersionResponse(BaseModel):
    """Serialized playbook version metadata for a hosted eval run."""

    id: UUID
    version_number: int
    created_at: str
    diff_summary: str | None = None


class HostedEvalRunResponse(BaseModel):
    """Serialized hosted eval run detail."""

    id: UUID
    workspace_id: str
    playbook_id: UUID
    playbook_name: str
    status: EvolutionJobStatus
    outcomes_processed: int
    error_message: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    ace_core_version: str | None = None
    token_totals: dict[str, Any] | None = None
    has_changes: bool | None = None
    from_version: HostedEvalRunVersionResponse | None = None
    to_version: HostedEvalRunVersionResponse | None = None


class TriggerHostedEvalRunResponse(HostedEvalRunResponse):
    """Hosted eval launch response."""

    is_new: bool


class ManagedInferenceMessageRequest(BaseModel):
    """One normalized chat message for managed inference."""

    role: Literal["system", "user", "assistant", "tool"]
    content: str = Field(..., min_length=1)
    name: str | None = Field(default=None, max_length=100)

    model_config = {"extra": "forbid"}


class ManagedInferenceRequest(BaseModel):
    """Request body for invoking managed inference."""

    model: str = Field(..., min_length=1, max_length=100)
    messages: list[ManagedInferenceMessageRequest] = Field(..., min_length=1, max_length=100)
    provider: Literal["openai", "anthropic"] | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0, le=2)
    reasoning_effort: Literal["low", "medium", "high"] | None = None

    model_config = {"extra": "forbid"}


class ManagedInferenceUsageResponse(BaseModel):
    """Portable token usage payload for managed inference."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


class ManagedInferenceResponse(BaseModel):
    """Normalized managed inference response payload."""

    workspace_id: str
    model: str
    provider: str
    output_text: str
    finish_reason: str | None = None
    request_id: str | None = None
    usage: ManagedInferenceUsageResponse | None = None


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


class WorkspaceSyncEventResponse(BaseModel):
    """Serialized sync event returned from push/pull APIs."""

    id: str
    entity_type: Literal["playbook"]
    entity_id: str
    operation: Literal["upsert", "delete"]
    occurred_at: datetime
    payload: PortablePlaybook | None = None


class WorkspaceSyncConflictResponse(BaseModel):
    """One rejected pushed sync event."""

    event_id: str
    entity_type: Literal["playbook"]
    entity_id: str
    message: str
    server_event: WorkspaceSyncEventResponse | None = None


class WorkspaceSyncPushEventRequest(BaseModel):
    """One event pushed from a client workspace replica."""

    id: str = Field(..., min_length=1, max_length=255)
    entity_type: Literal["playbook"] = "playbook"
    entity_id: str = Field(..., min_length=1, max_length=64)
    operation: Literal["upsert", "delete"]
    payload: PortablePlaybook | None = None
    base_updated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_event_shape(self) -> WorkspaceSyncPushEventRequest:
        """Require the right payload shape for each sync mutation."""
        if self.operation == "upsert" and self.payload is None:
            raise ValueError("payload is required for upsert events")
        if self.operation == "delete" and self.payload is not None:
            raise ValueError("payload must be omitted for delete events")
        if (
            self.payload is not None
            and self.payload.id is not None
            and self.payload.id != self.entity_id
        ):
            raise ValueError("payload.id must match entity_id")
        return self


class WorkspaceSyncPushRequest(BaseModel):
    """Batch push request for hosted workspace sync."""

    events: list[WorkspaceSyncPushEventRequest] = Field(default_factory=list)


class WorkspaceSyncPullResponse(BaseModel):
    """Cursor-based pull response for hosted workspace sync."""

    events: list[WorkspaceSyncEventResponse]
    next_cursor: str | None = None


class WorkspaceSyncPushResponse(BaseModel):
    """Push result including any explicit conflicts."""

    applied_events: list[WorkspaceSyncEventResponse]
    conflicts: list[WorkspaceSyncConflictResponse]
    next_cursor: str | None = None


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

    permissions = resolve_workspace_permissions(workspace, current_membership.role)
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        plan=workspace.plan,
        deployment_mode=workspace.deployment_mode,
        seat_limit=workspace.seat_limit,
        inference_config=_serialize_workspace_inference_config(workspace),
        member_count=len(workspace.memberships),
        current_user_role=current_membership.role,
        permissions=WorkspacePermissionsResponse(
            can_manage_settings=permissions.can_manage_settings,
            can_manage_seats=permissions.can_manage_seats,
            can_approve_playbooks=permissions.can_approve_playbooks,
        ),
    )


def _serialize_workspace_inference_config(
    workspace: Workspace,
) -> WorkspaceInferenceConfigResponse:
    """Serialize the workspace inference configuration with available mode choices."""

    raw_config = workspace.inference_config or {}
    available_modes = [WorkspaceInferenceMode.BYO_PROVIDER]
    if (
        workspace.deployment_mode == WorkspaceDeploymentMode.CLOUD
        and workspace.entitlements is not None
        and workspace.entitlements.managed_inference
    ):
        available_modes.append(WorkspaceInferenceMode.MANAGED_PROVIDER)

    return WorkspaceInferenceConfigResponse(
        mode=WorkspaceInferenceMode(
            raw_config.get("mode", WorkspaceInferenceMode.BYO_PROVIDER.value)
        ),
        provider=WorkspaceInferenceProvider(
            raw_config.get("provider", WorkspaceInferenceProvider.OPENAI.value)
        ),
        available_modes=available_modes,
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


def _serialize_invitation(invitation: WorkspaceInvitation) -> WorkspaceInvitationResponse:
    """Serialize a workspace invitation."""
    return WorkspaceInvitationResponse(
        id=invitation.id,
        workspace_id=invitation.workspace_id,
        workspace_name=invitation.workspace.name,
        invited_email=invitation.invited_email,
        role=invitation.role,
        invited_by_user_id=invitation.invited_by_user_id,
        invited_by_email=invitation.invited_by_user.email,
        created_at=invitation.created_at,
    )


def _serialize_shared_playbook(
    playbook: Playbook,
    *,
    current_user_id: UUID,
) -> WorkspaceSharedPlaybookResponse:
    """Serialize one shared registry playbook entry."""

    owner = playbook.user
    if owner is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Shared playbook owner was not loaded",
        )

    return WorkspaceSharedPlaybookResponse(
        id=playbook.id,
        name=playbook.name,
        description=playbook.description,
        status=playbook.status,
        source=playbook.source,
        created_at=playbook.created_at,
        updated_at=playbook.updated_at,
        version_count=len(playbook.versions),
        outcome_count=len(playbook.outcomes),
        owner=SharedPlaybookOwnerResponse(
            user_id=owner.id,
            email=owner.email,
        ),
        is_owned_by_current_user=playbook.user_id == current_user_id,
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


def _ensure_can_manage_workspace_settings(workspace: Workspace, membership) -> None:
    """Require a role that can alter workspace settings."""
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    permissions = resolve_workspace_permissions(workspace, membership.role)
    if not permissions.can_manage_settings:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace owner or admin role required to manage workspace settings",
        )


def _ensure_can_manage_workspace_seats(workspace: Workspace, membership) -> None:
    """Require a role that can change workspace seat assignments."""
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    permissions = resolve_workspace_permissions(workspace, membership.role)
    if not permissions.can_manage_seats:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workspace owner or admin role required to manage workspace seats",
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


async def _require_shared_registry_workspace(
    db: AsyncSession,
    current_user: User,
    workspace_id: str,
) -> Workspace:
    """Resolve a workspace and require shared-registry entitlement."""

    workspace = await _resolve_entitlements_workspace(db, current_user, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    if workspace.entitlements is None or not workspace.entitlements.shared_workspace:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Shared playbook registry is not enabled for this workspace.",
        )

    return workspace


def _serialize_sync_event(event) -> WorkspaceSyncEventResponse:
    """Convert a service-level sync event into the API response model."""

    return WorkspaceSyncEventResponse(
        id=event.id,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        operation=event.operation,
        occurred_at=event.occurred_at,
        payload=event.payload,
    )


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


def _serialize_eval_version(version: PlaybookVersion | None) -> HostedEvalRunVersionResponse | None:
    """Serialize version metadata for a hosted eval response."""
    if version is None:
        return None

    return HostedEvalRunVersionResponse(
        id=version.id,
        version_number=version.version_number,
        created_at=version.created_at.isoformat(),
        diff_summary=version.diff_summary,
    )


def _serialize_hosted_eval_run(
    workspace_id: str,
    job: EvolutionJob,
    *,
    is_new: bool | None = None,
) -> HostedEvalRunResponse | TriggerHostedEvalRunResponse:
    """Serialize one hosted eval run detail payload."""
    resolved_to_version = job.to_version or job.created_version
    payload = {
        "id": job.id,
        "workspace_id": workspace_id,
        "playbook_id": job.playbook_id,
        "playbook_name": job.playbook.name,
        "status": job.status,
        "outcomes_processed": job.outcomes_processed,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "ace_core_version": job.ace_core_version,
        "token_totals": job.token_totals,
        "has_changes": resolved_to_version is not None if job.completed_at else None,
        "from_version": _serialize_eval_version(job.from_version),
        "to_version": _serialize_eval_version(resolved_to_version),
    }
    if is_new is not None:
        return TriggerHostedEvalRunResponse(**payload, is_new=is_new)
    return HostedEvalRunResponse(**payload)


async def _resolve_hosted_eval_workspace(
    db: AsyncSession,
    current_user: User,
    workspace_id: str,
) -> str:
    """Resolve a supported hosted eval workspace identifier."""
    workspace = await _resolve_entitlements_workspace(db, current_user, workspace_id)
    if workspace is not None and workspace.plan != WorkspacePlan.PERSONAL:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hosted eval runs are currently only supported for personal workspaces.",
        )

    return str(workspace.id) if workspace is not None else get_workspace_id(current_user)


async def _get_hosted_eval_playbook(
    db: AsyncSession,
    current_user: User,
    playbook_id: UUID,
) -> Playbook:
    """Load a playbook for the current hosted personal user."""
    playbook = await db.get(Playbook, playbook_id)
    if playbook is None or playbook.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playbook not found")
    return playbook


async def _get_hosted_eval_run_or_404(
    db: AsyncSession,
    current_user: User,
    run_id: UUID,
) -> EvolutionJob:
    """Load one hosted eval run for the current user."""
    result = await db.execute(
        select(EvolutionJob)
        .join(Playbook)
        .where(
            EvolutionJob.id == run_id,
            Playbook.user_id == current_user.id,
        )
        .options(
            selectinload(EvolutionJob.playbook),
            selectinload(EvolutionJob.from_version),
            selectinload(EvolutionJob.to_version),
            selectinload(EvolutionJob.created_version),
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval run not found")
    return job


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
        inference_config=payload.inference_config.model_dump()
        if payload.inference_config
        else None,
    )
    await db.commit()

    workspace = await get_workspace_for_user(db, workspace.id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    return _serialize_workspace(workspace, current_user.id)


@router.post("/workspaces/me/upgrade-to-team", response_model=WorkspaceResponse)
async def upgrade_personal_workspace_to_team_route(
    payload: WorkspaceUpgradeToTeamRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkspaceResponse:
    """Upgrade the caller's hosted personal workspace into a team workspace."""
    workspace = await get_personal_workspace_for_user(db, current_user.id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Personal workspace not found",
        )

    membership = await _require_workspace_membership(db, workspace.id, current_user)
    _ensure_can_manage_workspace_settings(workspace, membership)

    try:
        await upgrade_personal_workspace_to_team(
            db,
            workspace,
            name=payload.name,
            seat_limit=payload.seat_limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

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

    workspace = await get_workspace_for_user(db, workspace_id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    _ensure_can_manage_workspace_settings(workspace, membership)

    inference_config = payload.inference_config.model_dump() if payload.inference_config else None

    try:
        if payload.plan == WorkspacePlan.TEAM and workspace.plan == WorkspacePlan.PERSONAL:
            await upgrade_personal_workspace_to_team(
                db,
                workspace,
                name=payload.name,
                seat_limit=payload.seat_limit,
                deployment_mode=payload.deployment_mode,
                inference_config=inference_config,
            )
        else:
            await update_workspace(
                db,
                workspace,
                name=payload.name,
                plan=payload.plan,
                deployment_mode=payload.deployment_mode,
                seat_limit=payload.seat_limit,
                inference_config=inference_config,
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

    workspace = await get_workspace_for_user(db, workspace_id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    _ensure_can_manage_workspace_settings(workspace, membership)

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

    workspace = await get_workspace_for_user(db, workspace_id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    _ensure_can_manage_workspace_seats(workspace, membership)

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

    workspace = await get_workspace_for_user(db, workspace_id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    _ensure_can_manage_workspace_seats(workspace, membership)

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

    workspace = await get_workspace_for_user(db, workspace_id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    _ensure_can_manage_workspace_seats(workspace, membership)

    target_membership = await get_workspace_membership_by_id(db, workspace_id, membership_id)
    if target_membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")

    try:
        await remove_workspace_membership(db, target_membership)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await db.commit()


@router.get(
    "/workspaces/{workspace_id}/invitations",
    response_model=list[WorkspaceInvitationResponse],
)
@router.get(
    "/v1/workspaces/{workspace_id}/invitations",
    response_model=list[WorkspaceInvitationResponse],
    include_in_schema=False,
)
async def list_workspace_invitations_route(
    workspace_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> list[WorkspaceInvitationResponse]:
    """List pending invitations for a workspace."""
    membership = await _require_workspace_membership(db, workspace_id, current_user)
    workspace = await get_workspace_for_user(db, workspace_id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    _ensure_can_manage_workspace_seats(workspace, membership)
    invitations = await list_workspace_invitations(db, workspace_id)
    return [_serialize_invitation(invitation) for invitation in invitations]


@router.post(
    "/workspaces/{workspace_id}/invitations",
    response_model=WorkspaceInvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
@router.post(
    "/v1/workspaces/{workspace_id}/invitations",
    response_model=WorkspaceInvitationResponse,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_workspace_invitation_route(
    workspace_id: UUID,
    payload: WorkspaceInvitationCreateRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkspaceInvitationResponse:
    """Create a pending invitation for a workspace."""
    membership = await _require_workspace_membership(db, workspace_id, current_user)

    workspace = await get_workspace_by_id(db, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    _ensure_can_manage_workspace_seats(workspace, membership)

    try:
        invitation = await create_workspace_invitation(
            db,
            workspace=workspace,
            invited_by_user=current_user,
            invited_email=payload.email,
            role=payload.role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await db.commit()
    refreshed = await get_workspace_invitation_by_id(db, workspace_id, invitation.id)
    if refreshed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    return _serialize_invitation(refreshed)


@router.delete(
    "/workspaces/{workspace_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@router.delete(
    "/v1/workspaces/{workspace_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    include_in_schema=False,
)
async def delete_workspace_invitation_route(
    workspace_id: UUID,
    invitation_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    """Cancel a pending workspace invitation."""
    membership = await _require_workspace_membership(db, workspace_id, current_user)
    workspace = await get_workspace_for_user(db, workspace_id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")
    _ensure_can_manage_workspace_seats(workspace, membership)

    invitation = await get_workspace_invitation_by_id(db, workspace_id, invitation_id)
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    try:
        await revoke_workspace_invitation(
            db,
            invitation=invitation,
            revoked_by_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await db.commit()


@router.get(
    "/workspace-invitations",
    response_model=list[WorkspaceInvitationResponse],
)
@router.get(
    "/v1/workspace-invitations",
    response_model=list[WorkspaceInvitationResponse],
    include_in_schema=False,
)
async def list_user_workspace_invitations_route(
    db: DbSession,
    current_user: CurrentUser,
) -> list[WorkspaceInvitationResponse]:
    """List pending invitations addressed to the current user."""
    invitations = await list_user_workspace_invitations(db, current_user.email)
    return [_serialize_invitation(invitation) for invitation in invitations]


@router.post(
    "/workspace-invitations/{invitation_id}/accept",
    response_model=WorkspaceMembershipResponse,
)
@router.post(
    "/v1/workspace-invitations/{invitation_id}/accept",
    response_model=WorkspaceMembershipResponse,
    include_in_schema=False,
)
async def accept_workspace_invitation_route(
    invitation_id: UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> WorkspaceMembershipResponse:
    """Accept a pending invitation for the authenticated user."""
    result = await db.execute(
        select(WorkspaceInvitation)
        .where(
            WorkspaceInvitation.id == invitation_id,
            WorkspaceInvitation.invited_email == current_user.email.lower(),
        )
        .options(
            selectinload(WorkspaceInvitation.workspace),
            selectinload(WorkspaceInvitation.invited_by_user),
        )
    )
    invitation = result.scalar_one_or_none()
    if invitation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    try:
        membership = await accept_workspace_invitation(
            db,
            invitation=invitation,
            user=current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await db.commit()
    return _serialize_membership(membership)


@router.get(
    "/v1/workspaces/{workspace_id}/playbooks/shared",
    response_model=PaginatedWorkspaceSharedPlaybookResponse,
)
@router.get(
    "/workspaces/{workspace_id}/playbooks/shared",
    response_model=PaginatedWorkspaceSharedPlaybookResponse,
    include_in_schema=False,
)
async def list_shared_workspace_playbooks_route(
    workspace_id: str,
    db: DbSession,
    current_user: PaidUser,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
) -> PaginatedWorkspaceSharedPlaybookResponse:
    """List approved shared playbooks for a team workspace."""

    workspace = await _require_shared_registry_workspace(db, current_user, workspace_id)
    playbooks, total = await list_shared_workspace_playbooks(
        db,
        workspace,
        current_user_id=current_user.id,
        page=page,
        page_size=page_size,
    )
    total_pages = (total + page_size - 1) // page_size

    return PaginatedWorkspaceSharedPlaybookResponse(
        items=[
            _serialize_shared_playbook(playbook, current_user_id=current_user.id)
            for playbook in playbooks
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post(
    "/v1/workspaces/{workspace_id}/playbooks/shared/{playbook_id}/reuse",
    response_model=PlaybookResponse,
)
@router.post(
    "/workspaces/{workspace_id}/playbooks/shared/{playbook_id}/reuse",
    response_model=PlaybookResponse,
    include_in_schema=False,
)
async def reuse_shared_workspace_playbook_route(
    workspace_id: str,
    playbook_id: UUID,
    db: DbSession,
    current_user: PaidUser,
) -> PlaybookResponse:
    """Copy one shared workspace playbook into the caller's library."""

    workspace = await _require_shared_registry_workspace(db, current_user, workspace_id)
    try:
        copied_playbook = await reuse_shared_workspace_playbook(
            db,
            workspace,
            current_user=current_user,
            source_playbook_id=playbook_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PlaybookLimitError as exc:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(copied_playbook)
    if copied_playbook.current_version_id is not None:
        await db.refresh(copied_playbook, ["current_version"])

    return PlaybookResponse(
        id=copied_playbook.id,
        name=copied_playbook.name,
        description=copied_playbook.description,
        status=copied_playbook.status,
        source=copied_playbook.source,
        created_at=copied_playbook.created_at,
        updated_at=copied_playbook.updated_at,
        current_version=(
            PlaybookVersionResponse(
                id=copied_playbook.current_version.id,
                version_number=copied_playbook.current_version.version_number,
                content=copied_playbook.current_version.content,
                bullet_count=copied_playbook.current_version.bullet_count,
                created_at=copied_playbook.current_version.created_at,
            )
            if copied_playbook.current_version is not None
            else None
        ),
    )


@router.get(
    "/v1/workspaces/{workspace_id}/sync/pull",
    response_model=WorkspaceSyncPullResponse,
)
@router.get(
    "/workspaces/{workspace_id}/sync/pull",
    response_model=WorkspaceSyncPullResponse,
    include_in_schema=False,
)
async def pull_workspace_sync_route(
    workspace_id: UUID,
    db: DbSession,
    current_user: PaidUser,
    cursor: str | None = Query(default=None),
) -> WorkspaceSyncPullResponse:
    """Pull sync events for a hosted personal workspace."""

    workspace = await get_workspace_for_user(db, workspace_id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    try:
        ensure_personal_sync_workspace(workspace)
        events, next_cursor = await list_workspace_sync_events(db, workspace, cursor=cursor)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return WorkspaceSyncPullResponse(
        events=[_serialize_sync_event(event) for event in events],
        next_cursor=next_cursor,
    )


@router.post(
    "/v1/workspaces/{workspace_id}/sync/push",
    response_model=WorkspaceSyncPushResponse,
)
@router.post(
    "/workspaces/{workspace_id}/sync/push",
    response_model=WorkspaceSyncPushResponse,
    include_in_schema=False,
)
async def push_workspace_sync_route(
    workspace_id: UUID,
    payload: WorkspaceSyncPushRequest,
    db: DbSession,
    current_user: PaidUser,
):
    """Push a batch of playbook sync mutations into a hosted personal workspace."""

    workspace = await get_workspace_for_user(db, workspace_id, current_user.id)
    if workspace is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")

    try:
        ensure_personal_sync_workspace(workspace)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    applied_events = []
    conflicts = []
    for event in payload.events:
        try:
            if event.operation == "upsert":
                applied = await apply_playbook_sync_upsert(
                    db,
                    workspace,
                    event_id=event.id,
                    entity_id=event.entity_id,
                    payload=event.payload,
                    base_updated_at=event.base_updated_at,
                )
            else:
                applied = await apply_playbook_sync_delete(
                    db,
                    workspace,
                    event_id=event.id,
                    entity_id=event.entity_id,
                    base_updated_at=event.base_updated_at,
                )
            applied_events.append(applied)
        except WorkspaceSyncConflictError as exc:
            conflicts.append(
                WorkspaceSyncConflictResponse(
                    event_id=exc.event_id,
                    entity_type=exc.entity_type,
                    entity_id=exc.entity_id,
                    message=exc.message,
                    server_event=(
                        _serialize_sync_event(exc.server_event)
                        if exc.server_event is not None
                        else None
                    ),
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await db.commit()

    next_cursor = None
    if applied_events:
        latest_event = max(
            applied_events,
            key=lambda item: (item.occurred_at, item.entity_type, item.entity_id),
        )
        next_cursor = encode_sync_cursor(latest_event.cursor_token)

    response = WorkspaceSyncPushResponse(
        applied_events=[_serialize_sync_event(event) for event in applied_events],
        conflicts=conflicts,
        next_cursor=next_cursor,
    )
    if conflicts:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=response.model_dump(mode="json"),
        )
    return response


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
    snapshot = await resolve_workspace_entitlements(db, current_user, workspace=workspace)
    return _to_response(snapshot, workspace)


@router.post(
    "/v1/workspaces/{workspace_id}/inference",
    response_model=ManagedInferenceResponse,
)
@router.post(
    "/workspaces/{workspace_id}/inference",
    response_model=ManagedInferenceResponse,
    include_in_schema=False,
)
async def invoke_managed_inference(
    workspace_id: str,
    payload: ManagedInferenceRequest,
    db: DbSession,
    current_user: ManagedInferenceUser,
) -> ManagedInferenceResponse:
    """Execute a managed inference request using server-side provider credentials."""
    workspace = await _resolve_entitlements_workspace(db, current_user, workspace_id)
    if workspace is not None and workspace.deployment_mode != WorkspaceDeploymentMode.CLOUD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Managed inference is only available for cloud workspaces.",
        )

    resolved_workspace_id = (
        str(workspace.id) if workspace is not None else get_workspace_id(current_user)
    )
    metadata = {}
    if payload.provider:
        metadata["provider"] = payload.provider.strip().lower()
    if payload.reasoning_effort:
        metadata["reasoning_effort"] = payload.reasoning_effort.strip().lower()

    gateway = ManagedInferenceGateway(
        db=db,
        user_id=current_user.id,
        workspace_id=resolved_workspace_id,
    )
    request_model = ModelRequest(
        model=payload.model,
        messages=[
            InferenceMessage(role=message.role, content=message.content, name=message.name)
            for message in payload.messages
        ],
        max_tokens=payload.max_tokens,
        temperature=payload.temperature,
        metadata=metadata,
    )

    try:
        response = await gateway.call(request_model)
    except ManagedInferenceConfigurationError as exc:
        logger.warning(
            "Managed inference request could not be served due to missing provider config",
            extra={"workspace_id": resolved_workspace_id, "model": payload.model},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ManagedInferenceRequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ManagedInferenceProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return ManagedInferenceResponse(
        workspace_id=resolved_workspace_id,
        model=response.model,
        provider=str(response.metadata.get("provider", metadata.get("provider", "openai"))),
        output_text=response.output_text,
        finish_reason=response.finish_reason,
        request_id=str(response.metadata.get("request_id"))
        if response.metadata.get("request_id")
        else None,
        usage=ManagedInferenceUsageResponse(
            input_tokens=response.usage.input_tokens if response.usage else None,
            output_tokens=response.usage.output_tokens if response.usage else None,
            total_tokens=response.usage.total_tokens if response.usage else None,
        )
        if response.usage
        else None,
    )


@router.post(
    "/v1/workspaces/{workspace_id}/evals/run",
    response_model=TriggerHostedEvalRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@router.post(
    "/workspaces/{workspace_id}/evals/run",
    response_model=TriggerHostedEvalRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
)
async def trigger_hosted_eval_run(
    workspace_id: str,
    payload: HostedEvalRunRequest,
    request: Request,
    db: DbSession,
    current_user: HostedEvalUser,
) -> TriggerHostedEvalRunResponse:
    """Launch a hosted eval run for a personal workspace."""
    from ace_platform.core.evolution_jobs import trigger_evolution_async
    from ace_platform.core.rate_limit import rate_limit_evolution

    if not current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required to trigger hosted eval runs.",
        )

    resolved_workspace_id = await _resolve_hosted_eval_workspace(db, current_user, workspace_id)
    playbook = await _get_hosted_eval_playbook(db, current_user, payload.playbook_id)

    await rate_limit_evolution(request, str(playbook.id))

    effective_tier = get_effective_tier_for_limits(current_user)
    can_proceed, error_message = await check_can_evolve(
        db,
        current_user.id,
        effective_tier,
        has_payment_method=current_user.has_payment_method,
        is_trialing=is_user_trialing(current_user),
    )
    if not can_proceed:
        detail = error_message
        if is_user_trialing(current_user):
            detail = (
                "You've reached the hosted eval limit for your free trial. "
                "Subscribe to a paid plan to unlock more hosted eval runs. "
                "Visit your account settings to view plans and upgrade."
            )
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=detail,
        )

    try:
        trigger_result = await trigger_evolution_async(db, playbook.id)
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    job = await _get_hosted_eval_run_or_404(db, current_user, trigger_result.job_id)
    return _serialize_hosted_eval_run(
        resolved_workspace_id,
        job,
        is_new=trigger_result.is_new,
    )


@router.get(
    "/v1/workspaces/{workspace_id}/evals/{run_id}",
    response_model=HostedEvalRunResponse,
)
@router.get(
    "/workspaces/{workspace_id}/evals/{run_id}",
    response_model=HostedEvalRunResponse,
    include_in_schema=False,
)
async def get_hosted_eval_run(
    workspace_id: str,
    run_id: UUID,
    db: DbSession,
    current_user: HostedEvalUser,
) -> HostedEvalRunResponse:
    """Return hosted eval run detail for a personal workspace."""
    resolved_workspace_id = await _resolve_hosted_eval_workspace(db, current_user, workspace_id)
    job = await _get_hosted_eval_run_or_404(db, current_user, run_id)
    return _serialize_hosted_eval_run(resolved_workspace_id, job)
