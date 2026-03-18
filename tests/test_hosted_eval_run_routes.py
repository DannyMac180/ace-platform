from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from ace_platform.api.auth import require_active_subscription
from ace_platform.api.deps import get_db
from ace_platform.api.main import create_app
from ace_platform.db.models import EvolutionJobStatus


def _make_user():
    return SimpleNamespace(
        id=uuid4(),
        email_verified=True,
        has_payment_method=True,
        trial_ends_at=None,
        subscription_status="active",
        subscription_tier="starter",
    )


def _make_job(status: EvolutionJobStatus = EvolutionJobStatus.COMPLETED):
    playbook_id = uuid4()
    from_version_id = uuid4()
    to_version_id = uuid4()
    return SimpleNamespace(
        id=uuid4(),
        playbook_id=playbook_id,
        playbook=SimpleNamespace(name="Revenue Assistant"),
        status=status,
        outcomes_processed=6,
        error_message=None,
        created_at=datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        started_at=datetime(2026, 1, 1, 10, 1, tzinfo=timezone.utc),
        completed_at=datetime(2026, 1, 1, 10, 2, tzinfo=timezone.utc)
        if status == EvolutionJobStatus.COMPLETED
        else None,
        ace_core_version="1.2.3",
        token_totals={
            "total_tokens": 3210,
            "model": "gpt-5.2",
            "operations": {"evolve": {"total_tokens": 3210}},
        },
        from_version=SimpleNamespace(
            id=from_version_id,
            version_number=3,
            created_at=datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
            diff_summary=None,
        ),
        to_version=SimpleNamespace(
            id=to_version_id,
            version_number=4,
            created_at=datetime(2026, 1, 1, 10, 2, tzinfo=timezone.utc),
            diff_summary="Added fallback qualification step",
        ),
        created_version=None,
    )


def _make_client(user):
    app = create_app()

    async def override_get_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[require_active_subscription] = lambda: user
    return TestClient(app)


def test_hosted_eval_routes_registered():
    app = create_app()
    routes = [route.path for route in app.routes]

    assert "/v1/workspaces/{workspace_id}/evals/run" in routes
    assert "/v1/workspaces/{workspace_id}/evals/{run_id}" in routes


def test_get_hosted_eval_run_returns_detail_payload():
    user = _make_user()
    job = _make_job()
    client = _make_client(user)

    with patch(
        "ace_platform.api.routes.workspaces._resolve_hosted_eval_workspace",
        new=AsyncMock(return_value="me"),
    ), patch(
        "ace_platform.api.routes.workspaces._get_hosted_eval_run_or_404",
        new=AsyncMock(return_value=job),
    ):
        response = client.get(f"/v1/workspaces/me/evals/{job.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(job.id)
    assert data["workspace_id"] == "me"
    assert data["playbook_name"] == "Revenue Assistant"
    assert data["status"] == "completed"
    assert data["has_changes"] is True
    assert data["to_version"]["diff_summary"] == "Added fallback qualification step"


def test_trigger_hosted_eval_run_returns_launched_run_detail():
    user = _make_user()
    job = _make_job(EvolutionJobStatus.QUEUED)
    client = _make_client(user)

    with patch(
        "ace_platform.api.routes.workspaces._resolve_hosted_eval_workspace",
        new=AsyncMock(return_value="me"),
    ), patch(
        "ace_platform.api.routes.workspaces._get_hosted_eval_playbook",
        new=AsyncMock(return_value=SimpleNamespace(id=job.playbook_id)),
    ), patch(
        "ace_platform.api.routes.workspaces.check_can_evolve",
        new=AsyncMock(return_value=(True, None)),
    ), patch(
        "ace_platform.api.routes.workspaces._get_hosted_eval_run_or_404",
        new=AsyncMock(return_value=job),
    ), patch(
        "ace_platform.core.rate_limit.rate_limit_evolution",
        new=AsyncMock(),
    ), patch(
        "ace_platform.core.evolution_jobs.trigger_evolution_async",
        new=AsyncMock(return_value=SimpleNamespace(job_id=job.id, is_new=True)),
    ):
        response = client.post(
            "/v1/workspaces/me/evals/run",
            json={"playbook_id": str(job.playbook_id)},
        )

    assert response.status_code == 202
    data = response.json()
    assert data["id"] == str(job.id)
    assert data["is_new"] is True
    assert data["status"] == "queued"
    assert data["playbook_id"] == str(job.playbook_id)
