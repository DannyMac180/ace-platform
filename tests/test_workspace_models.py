"""Tests for workspace tenancy schema models."""

import pytest
from sqlalchemy import CheckConstraint

from ace_platform.core.workspaces import resolve_workspace_permissions
from ace_platform.db.models import (
    Membership,
    MembershipRole,
    User,
    Workspace,
    WorkspaceBillingProvider,
    WorkspaceDeploymentMode,
    WorkspaceEntitlement,
    WorkspaceInferenceMode,
    WorkspaceInferenceProvider,
    WorkspacePlan,
    WorkspaceSubscription,
    WorkspaceSubscriptionStatus,
    get_default_workspace_entitlements,
    get_default_workspace_inference_config,
    get_workspace_plan_from_legacy_tier,
    workspace_supports_managed_inference,
)


def test_get_default_workspace_entitlements_by_plan():
    personal = get_default_workspace_entitlements(WorkspacePlan.PERSONAL)
    team = get_default_workspace_entitlements(WorkspacePlan.TEAM)
    enterprise = get_default_workspace_entitlements(WorkspacePlan.ENTERPRISE)

    assert personal["cloud_sync"] is True
    assert personal["invite_members"] is False
    assert personal["rbac"] is False

    assert team["invite_members"] is True
    assert team["shared_workspace"] is True
    assert team["sso"] is False

    assert enterprise["invite_members"] is True
    assert enterprise["sso"] is True
    assert enterprise["audit_logs"] is True


def test_get_default_workspace_inference_config_by_mode_support():
    personal_cloud = get_default_workspace_inference_config(
        plan=WorkspacePlan.PERSONAL,
        deployment_mode=WorkspaceDeploymentMode.CLOUD,
    )
    enterprise_self_hosted = get_default_workspace_inference_config(
        plan=WorkspacePlan.ENTERPRISE,
        deployment_mode=WorkspaceDeploymentMode.SELF_HOSTED,
    )

    assert personal_cloud == {
        "mode": WorkspaceInferenceMode.MANAGED_PROVIDER.value,
        "provider": WorkspaceInferenceProvider.OPENAI.value,
    }
    assert enterprise_self_hosted == {
        "mode": WorkspaceInferenceMode.BYO_PROVIDER.value,
        "provider": WorkspaceInferenceProvider.OPENAI.value,
    }


def test_workspace_supports_managed_inference_only_for_cloud_workspaces():
    assert (
        workspace_supports_managed_inference(
            plan=WorkspacePlan.PERSONAL,
            deployment_mode=WorkspaceDeploymentMode.CLOUD,
        )
        is True
    )
    assert (
        workspace_supports_managed_inference(
            plan=WorkspacePlan.ENTERPRISE,
            deployment_mode=WorkspaceDeploymentMode.SELF_HOSTED,
        )
        is False
    )


def test_get_workspace_plan_from_legacy_tier():
    assert get_workspace_plan_from_legacy_tier(None) == WorkspacePlan.PERSONAL
    assert get_workspace_plan_from_legacy_tier("starter") == WorkspacePlan.PERSONAL
    assert get_workspace_plan_from_legacy_tier("enterprise") == WorkspacePlan.ENTERPRISE


def test_workspace_models_support_all_plans_in_one_schema():
    owner = User(email="owner@example.com")
    reviewer = User(email="reviewer@example.com")

    personal = Workspace(
        name="Owner Workspace",
        plan=WorkspacePlan.PERSONAL,
        deployment_mode=WorkspaceDeploymentMode.CLOUD,
        seat_limit=1,
        inference_config=get_default_workspace_inference_config(
            plan=WorkspacePlan.PERSONAL,
            deployment_mode=WorkspaceDeploymentMode.CLOUD,
        ),
        entitlements=WorkspaceEntitlement(
            **WorkspaceEntitlement.defaults_for_plan(WorkspacePlan.PERSONAL)
        ),
        memberships=[Membership(user=owner, role=MembershipRole.OWNER)],
        subscription=WorkspaceSubscription(
            billing_provider=WorkspaceBillingProvider.STRIPE,
            status=WorkspaceSubscriptionStatus.TRIALING,
            plan_code="starter",
            provider_customer_id="cus_personal",
            provider_subscription_id="sub_personal",
        ),
    )
    team = Workspace(
        name="Team Workspace",
        plan=WorkspacePlan.TEAM,
        deployment_mode=WorkspaceDeploymentMode.CLOUD,
        seat_limit=5,
        inference_config=get_default_workspace_inference_config(
            plan=WorkspacePlan.TEAM,
            deployment_mode=WorkspaceDeploymentMode.CLOUD,
        ),
        entitlements=WorkspaceEntitlement(
            **WorkspaceEntitlement.defaults_for_plan(WorkspacePlan.TEAM)
        ),
        memberships=[
            Membership(user=owner, role=MembershipRole.OWNER),
            Membership(user=reviewer, role=MembershipRole.REVIEWER),
        ],
        subscription=WorkspaceSubscription(
            billing_provider=WorkspaceBillingProvider.STRIPE,
            status=WorkspaceSubscriptionStatus.ACTIVE,
            plan_code="team-v1",
            provider_customer_id="cus_team",
            provider_subscription_id="sub_team",
        ),
    )
    enterprise = Workspace(
        name="Enterprise Workspace",
        plan=WorkspacePlan.ENTERPRISE,
        deployment_mode=WorkspaceDeploymentMode.SELF_HOSTED,
        seat_limit=25,
        inference_config=get_default_workspace_inference_config(
            plan=WorkspacePlan.ENTERPRISE,
            deployment_mode=WorkspaceDeploymentMode.SELF_HOSTED,
        ),
        entitlements=WorkspaceEntitlement(
            **WorkspaceEntitlement.defaults_for_plan(WorkspacePlan.ENTERPRISE)
        ),
        memberships=[Membership(user=owner, role=MembershipRole.ADMIN)],
        subscription=WorkspaceSubscription(
            billing_provider=WorkspaceBillingProvider.MANUAL,
            status=WorkspaceSubscriptionStatus.UNPAID,
            plan_code="enterprise-contract",
        ),
    )

    assert personal.subscription is not None
    assert personal.subscription.status is WorkspaceSubscriptionStatus.TRIALING
    assert personal.inference_config["mode"] == WorkspaceInferenceMode.MANAGED_PROVIDER.value
    assert team.subscription is not None
    assert team.subscription.plan_code == "team-v1"
    assert team.entitlements is not None
    assert team.entitlements.shared_workspace is True
    assert team.inference_config["mode"] == WorkspaceInferenceMode.MANAGED_PROVIDER.value
    assert len(team.memberships) == 2
    assert enterprise.entitlements is not None
    assert enterprise.entitlements.audit_logs is True
    assert enterprise.entitlements.sso is True
    assert enterprise.inference_config["mode"] == WorkspaceInferenceMode.BYO_PROVIDER.value
    assert enterprise.subscription is not None
    assert enterprise.subscription.status is WorkspaceSubscriptionStatus.UNPAID


@pytest.mark.parametrize(
    ("role", "expected_permissions"),
    [
        (
            MembershipRole.OWNER,
            {
                "can_manage_settings": True,
                "can_manage_seats": True,
                "can_approve_playbooks": True,
            },
        ),
        (
            MembershipRole.ADMIN,
            {
                "can_manage_settings": True,
                "can_manage_seats": True,
                "can_approve_playbooks": True,
            },
        ),
        (
            MembershipRole.REVIEWER,
            {
                "can_manage_settings": False,
                "can_manage_seats": False,
                "can_approve_playbooks": True,
            },
        ),
        (
            MembershipRole.MEMBER,
            {
                "can_manage_settings": False,
                "can_manage_seats": False,
                "can_approve_playbooks": False,
            },
        ),
    ],
)
def test_team_workspace_permissions_follow_role_matrix(role, expected_permissions):
    workspace = Workspace(
        name="Team Permissions",
        plan=WorkspacePlan.TEAM,
        deployment_mode=WorkspaceDeploymentMode.CLOUD,
        seat_limit=5,
        inference_config=get_default_workspace_inference_config(
            plan=WorkspacePlan.TEAM,
            deployment_mode=WorkspaceDeploymentMode.CLOUD,
        ),
        entitlements=WorkspaceEntitlement(
            **WorkspaceEntitlement.defaults_for_plan(WorkspacePlan.TEAM)
        ),
    )

    permissions = resolve_workspace_permissions(workspace, role)

    assert permissions.can_manage_settings is expected_permissions["can_manage_settings"]
    assert permissions.can_manage_seats is expected_permissions["can_manage_seats"]
    assert permissions.can_approve_playbooks is expected_permissions["can_approve_playbooks"]


def test_personal_workspace_permissions_disable_seat_and_approval_actions():
    workspace = Workspace(
        name="Personal Permissions",
        plan=WorkspacePlan.PERSONAL,
        deployment_mode=WorkspaceDeploymentMode.CLOUD,
        seat_limit=1,
        inference_config=get_default_workspace_inference_config(
            plan=WorkspacePlan.PERSONAL,
            deployment_mode=WorkspaceDeploymentMode.CLOUD,
        ),
        entitlements=WorkspaceEntitlement(
            **WorkspaceEntitlement.defaults_for_plan(WorkspacePlan.PERSONAL)
        ),
    )

    permissions = resolve_workspace_permissions(workspace, MembershipRole.OWNER)

    assert permissions.can_manage_settings is True
    assert permissions.can_manage_seats is False
    assert permissions.can_approve_playbooks is False


def test_workspace_constraints_encode_uniqueness_and_personal_seat_limit():
    membership_pk = list(Membership.__table__.primary_key.columns.keys())
    subscription_pk = list(WorkspaceSubscription.__table__.primary_key.columns.keys())
    entitlement_pk = list(WorkspaceEntitlement.__table__.primary_key.columns.keys())
    workspace_constraints = [
        constraint
        for constraint in Workspace.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    ]

    assert membership_pk == ["workspace_id", "user_id"]
    assert subscription_pk == ["workspace_id"]
    assert entitlement_pk == ["workspace_id"]
    assert any(
        constraint.name == "ck_workspaces_seat_limit"
        and "seat_limit >= 1" in str(constraint.sqltext)
        for constraint in workspace_constraints
    )
    assert any(
        constraint.name == "ck_workspaces_personal_seat_limit"
        and "seat_limit = 1" in str(constraint.sqltext)
        for constraint in workspace_constraints
    )
