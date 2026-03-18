"""Tests for workspace entitlement resolution and routing."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from ace_platform.api.auth import require_user
from ace_platform.api.deps import get_db
from ace_platform.api.main import create_app
from ace_platform.core.entitlements import (
    get_plan_entitlements,
    normalize_workspace_plan,
    resolve_workspace_entitlements,
)
from ace_platform.core.limits import SubscriptionTier, UsageStatus, get_tier_limits
from ace_platform.db.models import SubscriptionStatus, User


def _make_user(
    *,
    subscription_tier: str | None = None,
    is_admin: bool = False,
    trial_ends_at: datetime | None = None,
):
    now = datetime.now(timezone.utc)
    return User(
        id=uuid4(),
        email="test@example.com",
        hashed_password=None,
        is_active=True,
        is_admin=is_admin,
        email_verified=True,
        subscription_tier=subscription_tier,
        subscription_status=SubscriptionStatus.ACTIVE,
        trial_ends_at=trial_ends_at,
        has_payment_method=True,
        created_at=now,
        updated_at=now,
    )


def _usage_status(tier: SubscriptionTier) -> UsageStatus:
    limits = get_tier_limits(tier)
    return UsageStatus(
        tier=tier,
        limits=limits,
        current_evolution_runs=2,
        current_total_tokens=1234,
        current_cost_usd=Decimal("0.42"),
        remaining_evolution_runs=(
            None if limits.monthly_evolution_runs is None else limits.monthly_evolution_runs - 2
        ),
        remaining_cost_usd=(
            None
            if limits.monthly_cost_limit_usd is None
            else limits.monthly_cost_limit_usd - Decimal("0.42")
        ),
        is_within_limits=True,
        limit_exceeded=None,
    )


def test_normalize_workspace_plan_maps_current_billing_model():
    assert normalize_workspace_plan(_make_user(subscription_tier=None)) == "personal"
    assert normalize_workspace_plan(_make_user(subscription_tier="starter")) == "personal"
    assert normalize_workspace_plan(_make_user(subscription_tier="enterprise")) == "enterprise"
    assert normalize_workspace_plan(_make_user(is_admin=True)) == "enterprise"


def test_get_plan_entitlements_matches_spec_shape():
    personal = get_plan_entitlements("personal")
    assert personal.cloud_sync is True
    assert personal.invite_members is False
    assert personal.audit_logs is False

    enterprise = get_plan_entitlements("enterprise")
    assert enterprise.shared_workspace is True
    assert enterprise.rbac is True
    assert enterprise.sso is True


@pytest.mark.asyncio
async def test_resolve_workspace_entitlements_uses_effective_limits_tier_for_trials():
    user = _make_user(
        subscription_tier="starter",
        trial_ends_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db = AsyncMock()

    with patch(
        "ace_platform.core.entitlements.get_user_usage_status",
        new=AsyncMock(return_value=_usage_status(SubscriptionTier.FREE)),
    ) as mock_status:
        snapshot = await resolve_workspace_entitlements(db, user)

    mock_status.assert_awaited_once_with(db, user.id, SubscriptionTier.FREE)
    assert snapshot.workspace_id == str(user.id)
    assert snapshot.plan == "personal"
    assert snapshot.seat_limit == 1
    assert snapshot.usage_limits.monthly_evolution_runs == 5
    assert snapshot.entitlements.managed_inference is True


def test_workspace_entitlements_routes_registered():
    app = create_app()
    routes = [route.path for route in app.routes]
    assert "/v1/workspaces/{workspace_id}/entitlements" in routes
    assert "/workspaces/{workspace_id}/entitlements" in routes


def test_workspace_entitlements_requires_auth():
    client = TestClient(create_app())
    response = client.get("/v1/workspaces/me/entitlements")
    assert response.status_code == 401


def test_workspace_entitlements_returns_authoritative_snapshot():
    app = create_app()
    user = _make_user(subscription_tier="starter")
    workspace_id = uuid4()

    async def override_get_db():
        yield AsyncMock()

    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = override_get_db

    with (
        patch(
            "ace_platform.core.entitlements.get_user_usage_status",
            new=AsyncMock(return_value=_usage_status(SubscriptionTier.STARTER)),
        ),
        patch(
            "ace_platform.api.routes.workspaces.get_default_workspace_for_user",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    id=workspace_id,
                    plan=SimpleNamespace(value="personal"),
                    deployment_mode=SimpleNamespace(value="cloud"),
                    seat_limit=1,
                    entitlements=SimpleNamespace(
                        cloud_sync=True,
                        hosted_backups=True,
                        managed_inference=True,
                        hosted_evals=True,
                        invite_members=False,
                        shared_workspace=False,
                        approvals=False,
                        rbac=False,
                        sso=False,
                        audit_logs=False,
                    ),
                )
            ),
        ),
    ):
        client = TestClient(app)
        response = client.get("/v1/workspaces/me/entitlements")

    assert response.status_code == 200
    data = response.json()
    assert data["workspace_id"] == str(workspace_id)
    assert data["plan"] == "personal"
    assert data["deployment_mode"] == "cloud"
    assert data["seat_limit"] == 1
    assert data["entitlements"]["cloud_sync"] is True
    assert data["entitlements"]["invite_members"] is False
    assert data["usage_limits"]["monthly_evolution_runs"] == 100
    assert data["usage_limits"]["current_total_tokens"] == 1234
    assert data["usage_limits"]["is_within_limits"] is True


def test_workspace_entitlements_forbidden_for_other_workspace():
    app = create_app()
    user = _make_user(subscription_tier="starter")

    async def override_get_db():
        yield AsyncMock()

    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = override_get_db

    with patch(
        "ace_platform.api.routes.workspaces.get_workspace_for_user",
        new=AsyncMock(return_value=None),
    ):
        client = TestClient(app)
        response = client.get(f"/v1/workspaces/{uuid4()}/entitlements")

    assert response.status_code == 403
    assert response.json()["error"]["message"] == "You do not have access to this workspace."


def test_workspace_entitlements_not_found_for_invalid_workspace_identifier():
    app = create_app()
    user = _make_user(subscription_tier="starter")

    async def override_get_db():
        yield AsyncMock()

    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = override_get_db

    client = TestClient(app)
    response = client.get("/v1/workspaces/not-a-workspace/entitlements")

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Workspace not found."
