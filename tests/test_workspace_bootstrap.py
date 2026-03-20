"""Tests for workspace bootstrap and signup integration."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ace_platform.db.models import (
    BillingProvider,
    DeploymentMode,
    OAuthProvider,
    SubscriptionStatus,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspacePlan,
    WorkspaceSubscription,
    WorkspaceSubscriptionStatus,
)


def _make_user(**overrides) -> User:
    now = datetime.now(UTC)
    defaults = {
        "id": uuid4(),
        "email": "dan@example.com",
        "hashed_password": "hashed",
        "email_verified": True,
        "subscription_status": SubscriptionStatus.NONE,
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return User(**defaults)


def _empty_workspace_lookup():
    result = MagicMock()
    scalars = MagicMock()
    scalars.first.return_value = None
    result.scalars.return_value = scalars
    return result


@pytest.mark.asyncio
async def test_build_workspace_subscription_from_user_maps_legacy_paid_state():
    from ace_platform.core.workspaces import build_workspace_subscription_from_user

    current_period_end = datetime.now(UTC) + timedelta(days=14)
    user = _make_user(
        subscription_tier="starter",
        subscription_status=SubscriptionStatus.ACTIVE,
        stripe_customer_id="cus_123",
        stripe_subscription_id="sub_123",
        subscription_current_period_end=current_period_end,
    )
    workspace = Workspace(
        name="dan personal workspace",
        plan=WorkspacePlan.PERSONAL,
        deployment_mode=DeploymentMode.CLOUD,
        seat_limit=1,
    )

    subscription = build_workspace_subscription_from_user(user, workspace=workspace)

    assert subscription is not None
    assert subscription.workspace is workspace
    assert subscription.billing_provider == BillingProvider.STRIPE
    assert subscription.status == WorkspaceSubscriptionStatus.ACTIVE
    assert subscription.plan_code == "starter"
    assert subscription.current_period_end == current_period_end


def test_build_workspace_subscription_from_user_skips_users_without_billing_state():
    from ace_platform.core.workspaces import build_workspace_subscription_from_user

    user = _make_user()
    workspace = Workspace(
        name="dan personal workspace",
        plan=WorkspacePlan.PERSONAL,
        deployment_mode=DeploymentMode.CLOUD,
        seat_limit=1,
    )

    assert build_workspace_subscription_from_user(user, workspace=workspace) is None


@pytest.mark.asyncio
async def test_ensure_personal_workspace_for_user_creates_owner_membership_and_subscription():
    from ace_platform.core.workspaces import ensure_personal_workspace_for_user

    db = MagicMock()
    db.execute.return_value = _empty_workspace_lookup()
    db.execute = AsyncMock(return_value=_empty_workspace_lookup())
    db.flush = AsyncMock()
    added: list[object] = []
    db.add = MagicMock(side_effect=added.append)

    user = _make_user(
        subscription_tier="starter",
        subscription_status=SubscriptionStatus.ACTIVE,
        stripe_customer_id="cus_123",
        stripe_subscription_id="sub_123",
    )

    workspace = await ensure_personal_workspace_for_user(db, user)

    membership = next(item for item in added if isinstance(item, WorkspaceMembership))
    subscription = next(item for item in added if isinstance(item, WorkspaceSubscription))

    assert isinstance(workspace, Workspace)
    assert workspace.plan == WorkspacePlan.PERSONAL
    assert workspace.seat_limit == 1
    assert membership.workspace is workspace
    assert membership.user is user
    assert subscription.workspace is workspace
    assert subscription.status == WorkspaceSubscriptionStatus.ACTIVE
    assert db.flush.await_count == 1


@pytest.mark.asyncio
async def test_ensure_personal_workspace_for_user_reuses_existing_workspace_and_backfills_subscription():
    from ace_platform.core.workspaces import ensure_personal_workspace_for_user

    workspace = Workspace(
        name="existing",
        plan=WorkspacePlan.PERSONAL,
        deployment_mode=DeploymentMode.CLOUD,
        seat_limit=1,
    )
    existing_result = MagicMock()
    scalars = MagicMock()
    scalars.first.return_value = workspace
    existing_result.scalars.return_value = scalars

    db = MagicMock()
    db.execute = AsyncMock(return_value=existing_result)
    db.flush = AsyncMock()
    added: list[object] = []
    db.add = MagicMock(side_effect=added.append)

    user = _make_user(
        subscription_tier="starter",
        subscription_status=SubscriptionStatus.ACTIVE,
        stripe_customer_id="cus_123",
    )

    resolved = await ensure_personal_workspace_for_user(db, user)

    assert resolved is workspace
    assert len([item for item in added if isinstance(item, WorkspaceSubscription)]) == 1
    assert len([item for item in added if isinstance(item, WorkspaceMembership)]) == 0


@pytest.mark.asyncio
async def test_register_bootstraps_personal_workspace(monkeypatch):
    from ace_platform.api.routes import auth as auth_routes

    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    request = auth_routes.UserRegisterRequest(email="new@example.com", password="password123")
    ensure_workspace = AsyncMock()

    monkeypatch.setattr(auth_routes, "get_user_by_email", AsyncMock(return_value=None))
    monkeypatch.setattr(auth_routes, "ensure_personal_workspace_for_user", ensure_workspace)
    monkeypatch.setattr(auth_routes, "audit_account_created", AsyncMock())
    monkeypatch.setattr(auth_routes, "is_email_enabled", lambda: False)
    monkeypatch.setattr(
        auth_routes,
        "get_settings",
        lambda: SimpleNamespace(
            acquisition_tracking_enabled=False, frontend_url="http://localhost"
        ),
    )
    monkeypatch.setattr(
        auth_routes,
        "create_tokens",
        lambda user_id: auth_routes.TokenResponse(
            access_token=f"access-{user_id}",
            refresh_token=f"refresh-{user_id}",
        ),
    )

    response = await auth_routes.register(request, MagicMock(), db, None)

    created_user = db.add.call_args_list[0].args[0]
    ensure_workspace.assert_awaited_once_with(db, created_user)
    assert response.access_token.startswith("access-")


@pytest.mark.asyncio
async def test_oauth_service_bootstraps_personal_workspace_for_new_users(monkeypatch):
    from ace_platform.core import oauth_service as oauth_service_module

    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    ensure_workspace = AsyncMock()

    monkeypatch.setattr(
        oauth_service_module,
        "ensure_personal_workspace_for_user",
        ensure_workspace,
    )

    service = oauth_service_module.OAuthService(db)
    service._get_oauth_account = AsyncMock(return_value=None)
    service._get_user_by_email = AsyncMock(return_value=None)

    user, is_new = await service.get_or_create_user_from_oauth(
        provider=OAuthProvider.GITHUB,
        provider_user_id="12345",
        email="oauth@example.com",
        user_info={"id": "12345", "login": "oauth"},
        access_token="token",
    )

    ensure_workspace.assert_awaited_once_with(db, user)
    assert is_new is True
