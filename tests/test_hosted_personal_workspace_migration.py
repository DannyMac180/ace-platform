"""Unit tests for hosted personal workspace migration helpers."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ace_platform.core import workspaces as workspace_service
from ace_platform.db.models import (
    SubscriptionStatus,
    User,
    Workspace,
    WorkspaceDeploymentMode,
    WorkspaceEntitlement,
    WorkspaceMembership,
    WorkspacePlan,
    WorkspaceRole,
)
from scripts.migrate_hosted_solo_users_to_personal_workspaces import normalize_database_url


def _make_user(**overrides) -> User:
    now = datetime.now(UTC)
    defaults = {
        "id": uuid4(),
        "email": "dan@example.com",
        "hashed_password": "hashed",
        "email_verified": True,
        "is_active": True,
        "subscription_status": SubscriptionStatus.NONE,
        "created_at": now,
        "updated_at": now,
        "memberships": [],
    }
    defaults.update(overrides)
    return User(**defaults)


def _make_personal_workspace(**overrides) -> Workspace:
    defaults = {
        "id": uuid4(),
        "name": "Dan Personal",
        "plan": WorkspacePlan.PERSONAL,
        "deployment_mode": WorkspaceDeploymentMode.CLOUD,
        "seat_limit": 1,
        "inference_config": {"mode": "managed_provider", "provider": "openai"},
    }
    defaults.update(overrides)
    return Workspace(**defaults)


def _attach_membership(
    user: User, workspace: Workspace, role: WorkspaceRole
) -> WorkspaceMembership:
    membership = WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role=role)
    membership.workspace = workspace
    membership.user = user
    user.memberships = [membership]
    workspace.memberships = [membership]
    return membership


def test_classify_hosted_solo_user_without_workspace_is_eligible():
    user = _make_user()

    eligible, workspace, reasons = workspace_service.classify_hosted_solo_user_workspace_state(user)

    assert eligible is True
    assert workspace is None
    assert reasons == ("missing_workspace",)


def test_normalize_database_url_translates_sslmode_disable_for_asyncpg():
    url = "postgresql://user:pass@localhost:5432/ace_platform?sslmode=disable"

    assert (
        normalize_database_url(url)
        == "postgresql+asyncpg://user:pass@localhost:5432/ace_platform?ssl=disable"
    )


def test_normalize_database_url_strips_sslmode_and_preserves_other_query_params():
    url = (
        "postgres://user:pass@localhost:5432/ace_platform"
        "?application_name=ace&sslmode=require&connect_timeout=10"
    )

    assert (
        normalize_database_url(url) == "postgresql+asyncpg://user:pass@localhost:5432/ace_platform"
        "?application_name=ace&connect_timeout=10"
    )


@pytest.mark.asyncio
async def test_migrate_creates_personal_workspace_for_unassigned_user(monkeypatch):
    added: list[object] = []
    db = MagicMock()
    db.add = MagicMock(side_effect=added.append)
    db.flush = AsyncMock()

    user = _make_user(
        subscription_tier="starter",
        subscription_status=SubscriptionStatus.ACTIVE,
        stripe_customer_id="cus_123",
        stripe_subscription_id="sub_123",
        subscription_current_period_end=datetime.now(UTC) + timedelta(days=30),
    )
    created_workspace = _make_personal_workspace()

    async def fake_create_workspace(*_args, **_kwargs):
        return created_workspace

    monkeypatch.setattr(workspace_service, "create_workspace", fake_create_workspace)

    result = await workspace_service.migrate_hosted_solo_user_to_personal_workspace(db, user)

    assert result.action == "created"
    assert result.workspace_id == created_workspace.id
    assert result.workspace_created is True
    assert result.membership_created is True
    assert result.entitlements_created is True
    assert result.subscription_created is True
    assert len([item for item in added if item.__class__.__name__ == "WorkspaceSubscription"]) == 1


@pytest.mark.asyncio
async def test_migrate_repairs_existing_personal_workspace_state():
    added: list[object] = []
    db = MagicMock()
    db.add = MagicMock(side_effect=added.append)
    db.flush = AsyncMock()

    user = _make_user(
        subscription_tier="starter",
        subscription_status=SubscriptionStatus.ACTIVE,
        stripe_customer_id="cus_123",
        stripe_subscription_id="sub_123",
    )
    workspace = _make_personal_workspace(entitlements=None, subscription=None)
    membership = _attach_membership(user, workspace, WorkspaceRole.MEMBER)

    result = await workspace_service.migrate_hosted_solo_user_to_personal_workspace(db, user)

    assert result.action == "repaired"
    assert result.workspace_id == workspace.id
    assert result.membership_role_updated_from == WorkspaceRole.MEMBER.value
    assert result.entitlements_created is True
    assert result.subscription_created is True
    assert membership.role == WorkspaceRole.OWNER
    assert any(isinstance(item, WorkspaceEntitlement) for item in added)
    assert len([item for item in added if item.__class__.__name__ == "WorkspaceSubscription"]) == 1


@pytest.mark.asyncio
async def test_migrate_skips_non_solo_workspace_users():
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    user = _make_user()
    workspace = Workspace(
        id=uuid4(),
        name="Team Alpha",
        plan=WorkspacePlan.TEAM,
        deployment_mode=WorkspaceDeploymentMode.CLOUD,
        seat_limit=5,
        inference_config={"mode": "managed_provider", "provider": "openai"},
    )
    _attach_membership(user, workspace, WorkspaceRole.MEMBER)

    result = await workspace_service.migrate_hosted_solo_user_to_personal_workspace(db, user)

    assert result.action == "skipped"
    assert result.eligible is False
    assert result.reasons == ("non_personal_or_non_cloud_workspace",)
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_validate_flags_missing_subscription_projection_for_legacy_billing(monkeypatch):
    user = _make_user(
        subscription_tier="starter",
        subscription_status=SubscriptionStatus.ACTIVE,
        stripe_customer_id="cus_123",
    )
    workspace = _make_personal_workspace(
        entitlements=WorkspaceEntitlement(
            workspace_id=uuid4(),
            **WorkspaceEntitlement.defaults_for_plan(WorkspacePlan.PERSONAL),
        ),
        subscription=None,
    )
    _attach_membership(user, workspace, WorkspaceRole.OWNER)

    db = MagicMock()

    async def fake_list_users(*_args, **_kwargs):
        return [user]

    monkeypatch.setattr(
        workspace_service,
        "list_hosted_personal_workspace_migration_users",
        fake_list_users,
    )

    summary = await workspace_service.validate_hosted_solo_users_personal_workspaces(db)

    assert summary.invalid_count == 1
    assert summary.results[0].status == "invalid"
    assert "missing_subscription_projection" in summary.results[0].errors
