"""Workspace-facing routes built on top of the current user model."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.api.auth import RequiredUser
from ace_platform.api.deps import get_db
from ace_platform.core.entitlements import (
    WorkspaceEntitlementsSnapshot,
    get_workspace_id,
    resolve_workspace_entitlements,
)

router = APIRouter(tags=["workspaces"])


DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = RequiredUser


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
    deployment_mode: Literal["cloud"]
    seat_limit: int | None
    entitlements: WorkspaceFeatureAccessResponse
    usage_limits: WorkspaceUsageLimitsResponse


def _validate_workspace_access(current_user, workspace_id: str) -> None:
    """Allow access to the caller's workspace id and a `me` alias only."""

    if workspace_id in {"me", get_workspace_id(current_user)}:
        return

    try:
        UUID(workspace_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found.",
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have access to this workspace.",
    )


def _to_response(snapshot: WorkspaceEntitlementsSnapshot) -> WorkspaceEntitlementsResponse:
    """Serialize the core entitlement snapshot into the route response model."""

    return WorkspaceEntitlementsResponse(
        workspace_id=snapshot.workspace_id,
        plan=snapshot.plan,
        deployment_mode=snapshot.deployment_mode,
        seat_limit=snapshot.seat_limit,
        entitlements=WorkspaceFeatureAccessResponse(
            cloud_sync=snapshot.entitlements.cloud_sync,
            hosted_backups=snapshot.entitlements.hosted_backups,
            managed_inference=snapshot.entitlements.managed_inference,
            hosted_evals=snapshot.entitlements.hosted_evals,
            invite_members=snapshot.entitlements.invite_members,
            shared_workspace=snapshot.entitlements.shared_workspace,
            approvals=snapshot.entitlements.approvals,
            rbac=snapshot.entitlements.rbac,
            sso=snapshot.entitlements.sso,
            audit_logs=snapshot.entitlements.audit_logs,
        ),
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


@router.get("/v1/workspaces/{workspace_id}/entitlements", response_model=WorkspaceEntitlementsResponse)
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

    _validate_workspace_access(current_user, workspace_id)
    snapshot = await resolve_workspace_entitlements(db, current_user)
    return _to_response(snapshot)
