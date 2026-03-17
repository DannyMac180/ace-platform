"""Tests for the workspace tenancy schema primitives."""

from sqlalchemy import UniqueConstraint

from ace_platform.db.models import (
    DeploymentMode,
    Workspace,
    WorkspaceMembership,
    WorkspacePlan,
    WorkspaceSubscription,
)


def test_workspace_schema_supports_personal_and_team_plans():
    """Workspace model carries the tenancy fields from the product spec."""
    workspace = Workspace(
        name="Dan Personal",
        plan=WorkspacePlan.PERSONAL,
        deployment_mode=DeploymentMode.CLOUD,
        seat_limit=1,
    )

    assert workspace.plan == WorkspacePlan.PERSONAL
    assert workspace.deployment_mode == DeploymentMode.CLOUD
    assert workspace.seat_limit == 1
    assert set(WorkspacePlan) == {
        WorkspacePlan.PERSONAL,
        WorkspacePlan.TEAM,
        WorkspacePlan.ENTERPRISE,
    }


def test_workspace_membership_enforces_unique_workspace_user_pair():
    """A user can only appear once per workspace membership list."""
    unique_constraints = {
        constraint.name
        for constraint in WorkspaceMembership.__table__.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert "uq_workspace_memberships_workspace_user" in unique_constraints


def test_workspace_subscription_is_one_to_one_with_workspace():
    """Each workspace stores one active billing record."""
    workspace_id_column = WorkspaceSubscription.__table__.c.workspace_id

    assert workspace_id_column.unique is True
