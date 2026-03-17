"""Tests for workspace entitlement defaults and validation."""

import pytest

from ace_platform.core.workspaces import (
    get_workspace_plan_defaults,
    resolve_workspace_entitlements,
    resolve_workspace_usage,
    validate_workspace_shape,
)
from ace_platform.db.models import DeploymentMode, Workspace, WorkspacePlan


@pytest.mark.asyncio
async def test_personal_workspace_entitlements_match_cloud_solo_plan():
    """Personal workspaces keep convenience features but disable collaboration."""
    workspace = Workspace(
        name="Solo",
        plan=WorkspacePlan.PERSONAL,
        deployment_mode=DeploymentMode.CLOUD,
        seat_limit=1,
    )

    entitlements = resolve_workspace_entitlements(workspace)

    assert await entitlements.can("cloud_sync") is True
    assert await entitlements.can("hosted_backups") is True
    assert await entitlements.can("managed_inference") is True
    assert await entitlements.can("invite_members") is False
    assert await entitlements.can("shared_workspace") is False


@pytest.mark.asyncio
async def test_team_workspace_entitlements_enable_collaboration_features():
    """Team workspaces expose the collaboration controls missing from personal."""
    workspace = Workspace(
        name="Team",
        plan=WorkspacePlan.TEAM,
        deployment_mode=DeploymentMode.CLOUD,
        seat_limit=8,
    )

    entitlements = resolve_workspace_entitlements(workspace)

    assert await entitlements.can("invite_members") is True
    assert await entitlements.can("shared_workspace") is True
    assert await entitlements.can("approvals") is True
    assert await entitlements.can("rbac") is True


def test_workspace_shape_validation_enforces_personal_and_team_seat_rules():
    """Seat semantics stay aligned with the product spec."""
    validate_workspace_shape(
        plan=WorkspacePlan.PERSONAL,
        seat_limit=1,
        deployment_mode=DeploymentMode.CLOUD,
    )
    validate_workspace_shape(
        plan=WorkspacePlan.TEAM,
        seat_limit=2,
        deployment_mode=DeploymentMode.CLOUD,
    )

    with pytest.raises(ValueError, match="exactly one seat"):
        validate_workspace_shape(
            plan=WorkspacePlan.PERSONAL,
            seat_limit=2,
            deployment_mode=DeploymentMode.CLOUD,
        )

    with pytest.raises(ValueError, match="at least 2 seat"):
        validate_workspace_shape(
            plan=WorkspacePlan.TEAM,
            seat_limit=1,
            deployment_mode=DeploymentMode.CLOUD,
        )

    with pytest.raises(ValueError, match="must use cloud deployment"):
        validate_workspace_shape(
            plan=WorkspacePlan.TEAM,
            seat_limit=5,
            deployment_mode=DeploymentMode.SELF_HOSTED,
        )


def test_workspace_entitlement_and_usage_overrides_merge_with_plan_defaults():
    """Workspace-specific overrides can adjust the default plan envelope."""
    defaults = get_workspace_plan_defaults(WorkspacePlan.TEAM)
    workspace = Workspace(
        name="Custom Team",
        plan=WorkspacePlan.TEAM,
        deployment_mode=DeploymentMode.CLOUD,
        seat_limit=12,
        entitlement_overrides={"audit_logs": False},
        usage_limit_overrides={"monthly_evolution_runs": 500, "max_members": 12},
    )

    entitlements = resolve_workspace_entitlements(workspace)
    usage = resolve_workspace_usage(workspace)

    assert defaults.entitlements.audit_logs is True
    assert entitlements.audit_logs is False
    assert usage.max_members == 12
    assert usage.monthly_evolution_runs == 500
