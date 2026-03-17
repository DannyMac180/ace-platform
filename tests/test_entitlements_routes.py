"""Tests for workspace entitlements routes."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from ace_platform.api.auth import require_user
from ace_platform.api.deps import get_db
from ace_platform.api.routes.workspaces import router
from ace_platform.core.entitlements import (
    WorkspaceAccessState,
    WorkspaceEntitlementsSnapshot,
    WorkspaceFeatureAccess,
    WorkspaceUsageLimits,
)
from ace_platform.core.limits import SubscriptionTier
from ace_platform.db.models import SubscriptionStatus


def _make_snapshot(workspace_id: str) -> WorkspaceEntitlementsSnapshot:
    return WorkspaceEntitlementsSnapshot(
        workspace_id=workspace_id,
        plan="personal",
        deployment_mode="cloud",
        seat_limit=1,
        entitlements=WorkspaceFeatureAccess(
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
        enabled_features=(
            "cloud_sync",
            "hosted_backups",
            "managed_inference",
            "hosted_evals",
        ),
        access=WorkspaceAccessState(
            subscription_tier=SubscriptionTier.STARTER,
            subscription_status=SubscriptionStatus.ACTIVE,
            effective_tier=SubscriptionTier.STARTER,
            has_feature_access=True,
            is_trialing=False,
        ),
        usage_limits=WorkspaceUsageLimits(
            monthly_evolution_runs=100,
            current_evolution_runs=3,
            remaining_evolution_runs=97,
            monthly_cost_limit_usd=Decimal("9.00"),
            current_cost_usd=Decimal("0.75"),
            remaining_cost_usd=Decimal("8.25"),
            current_total_tokens=987,
            max_playbooks=5,
            is_within_limits=True,
            limit_exceeded=None,
        ),
    )


class TestWorkspaceEntitlementsRoutes:
    @pytest.fixture
    def app(self):
        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app):
        return TestClient(app)

    def test_route_requires_authentication(self, client):
        response = client.get("/v1/workspaces/personal/entitlements")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_route_returns_forbidden_for_other_workspace_id(self, app):
        user = SimpleNamespace(id=uuid4())

        async def override_user():
            return user

        async def override_db():
            yield object()

        app.dependency_overrides[require_user] = override_user
        app.dependency_overrides[get_db] = override_db

        response = TestClient(app).get(f"/v1/workspaces/{uuid4()}/entitlements")

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["detail"] == "You do not have access to this workspace."

    def test_route_returns_entitlements_for_personal_alias(self, monkeypatch, app):
        user = SimpleNamespace(id=uuid4())

        async def override_user():
            return user

        async def override_db():
            yield object()

        app.dependency_overrides[require_user] = override_user
        app.dependency_overrides[get_db] = override_db
        monkeypatch.setattr(
            "ace_platform.api.routes.workspaces.resolve_workspace_entitlements",
            AsyncMock(return_value=_make_snapshot(str(user.id))),
        )

        response = TestClient(app).get("/v1/workspaces/personal/entitlements")

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "workspace_id": str(user.id),
            "plan": "personal",
            "deployment_mode": "cloud",
            "seat_limit": 1,
            "enabled_features": [
                "cloud_sync",
                "hosted_backups",
                "managed_inference",
                "hosted_evals",
            ],
            "access": {
                "subscription_tier": "starter",
                "subscription_status": "active",
                "effective_tier": "starter",
                "has_feature_access": True,
                "is_trialing": False,
            },
            "entitlements": {
                "cloud_sync": True,
                "hosted_backups": True,
                "managed_inference": True,
                "hosted_evals": True,
                "invite_members": False,
                "shared_workspace": False,
                "approvals": False,
                "rbac": False,
                "sso": False,
                "audit_logs": False,
            },
            "usage_limits": {
                "monthly_evolution_runs": 100,
                "current_evolution_runs": 3,
                "remaining_evolution_runs": 97,
                "monthly_cost_limit_usd": "9.00",
                "current_cost_usd": "0.75",
                "remaining_cost_usd": "8.25",
                "current_total_tokens": 987,
                "max_playbooks": 5,
                "is_within_limits": True,
                "limit_exceeded": None,
            },
        }


class TestWorkspaceEntitlementsRouteRegistration:
    def test_routes_are_registered_on_main_app(self):
        from ace_platform.api.main import create_app

        app = create_app()
        routes = [route.path for route in app.routes]
        assert "/v1/workspaces/{workspace_id}/entitlements" in routes
        assert "/workspaces/{workspace_id}/entitlements" in routes
