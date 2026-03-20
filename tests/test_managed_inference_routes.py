from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from ace_core.contracts import ModelResponse, TokenUsage
from ace_platform.api.auth import require_active_subscription
from ace_platform.api.deps import get_db
from ace_platform.api.main import create_app
from ace_platform.core.managed_inference import ManagedInferenceConfigurationError
from ace_platform.db.models import WorkspaceDeploymentMode


def _make_user():
    return SimpleNamespace(
        id=uuid4(),
        email="managed@example.com",
        email_verified=True,
        has_payment_method=True,
        trial_ends_at=None,
        subscription_status="active",
        subscription_tier="starter",
    )


def _make_client(user):
    app = create_app()

    async def override_get_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_active_subscription] = lambda: user
    return TestClient(app)


def test_managed_inference_routes_registered():
    app = create_app()
    routes = [route.path for route in app.routes]

    assert "/v1/workspaces/{workspace_id}/inference" in routes


def test_managed_inference_route_requires_authentication():
    client = TestClient(create_app())

    response = client.post(
        "/v1/workspaces/me/inference",
        json={
            "model": "gpt-5.2",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 401


def test_managed_inference_returns_normalized_response():
    user = _make_user()
    client = _make_client(user)
    response_model = ModelResponse(
        model="gpt-5.2",
        output_text="managed answer",
        finish_reason="stop",
        usage=TokenUsage(input_tokens=12, output_tokens=18, total_tokens=30),
        metadata={"provider": "openai", "request_id": "req_managed_123"},
    )

    with (
        patch(
            "ace_platform.api.routes.workspaces._resolve_entitlements_workspace",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "ace_platform.api.routes.workspaces.check_workspace_managed_inference_allowed",
            new=AsyncMock(return_value=(True, None)),
        ),
        patch(
            "ace_platform.api.routes.workspaces.ManagedInferenceGateway.call",
            new=AsyncMock(return_value=response_model),
        ),
    ):
        response = client.post(
            "/v1/workspaces/me/inference",
            json={
                "model": "gpt-5.2",
                "messages": [{"role": "user", "content": "hello"}],
                "reasoning_effort": "medium",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "workspace_id": str(user.id),
        "model": "gpt-5.2",
        "provider": "openai",
        "output_text": "managed answer",
        "finish_reason": "stop",
        "request_id": "req_managed_123",
        "usage": {
            "input_tokens": 12,
            "output_tokens": 18,
            "total_tokens": 30,
        },
    }


def test_managed_inference_returns_service_unavailable_when_provider_is_unconfigured():
    user = _make_user()
    client = _make_client(user)

    with (
        patch(
            "ace_platform.api.routes.workspaces._resolve_entitlements_workspace",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "ace_platform.api.routes.workspaces.check_workspace_managed_inference_allowed",
            new=AsyncMock(return_value=(True, None)),
        ),
        patch(
            "ace_platform.api.routes.workspaces.ManagedInferenceGateway.call",
            new=AsyncMock(
                side_effect=ManagedInferenceConfigurationError(
                    "Managed OpenAI inference is not configured on this server."
                )
            ),
        ),
    ):
        response = client.post(
            "/v1/workspaces/me/inference",
            json={
                "model": "gpt-5.2",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

    assert response.status_code == 503
    assert (
        response.json()["error"]["message"]
        == "Managed OpenAI inference is not configured on this server."
    )


def test_managed_inference_rejects_non_cloud_workspaces():
    user = _make_user()
    client = _make_client(user)
    workspace = SimpleNamespace(id=uuid4(), deployment_mode=WorkspaceDeploymentMode.SELF_HOSTED)

    with patch(
        "ace_platform.api.routes.workspaces._resolve_entitlements_workspace",
        new=AsyncMock(return_value=workspace),
    ):
        response = client.post(
            f"/v1/workspaces/{workspace.id}/inference",
            json={
                "model": "gpt-5.2",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

    assert response.status_code == 400
    assert (
        response.json()["error"]["message"]
        == "Managed inference is only available for cloud workspaces."
    )


def test_managed_inference_rejects_workspace_without_entitlement_access():
    user = _make_user()
    client = _make_client(user)

    with (
        patch(
            "ace_platform.api.routes.workspaces._resolve_entitlements_workspace",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "ace_platform.api.routes.workspaces.check_workspace_managed_inference_allowed",
            new=AsyncMock(
                return_value=(False, "Managed inference is not enabled for this workspace plan.")
            ),
        ),
    ):
        response = client.post(
            "/v1/workspaces/me/inference",
            json={
                "model": "gpt-5.2",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )

    assert response.status_code == 402
    assert (
        response.json()["error"]["message"]
        == "Managed inference is not enabled for this workspace plan."
    )
