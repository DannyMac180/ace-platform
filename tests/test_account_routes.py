"""Tests for account management routes.

These tests avoid database/network access by focusing on:
- Route registration and auth protection
- Unit-level serialization behavior for export
"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request, status
from fastapi.testclient import TestClient

from ace_platform.api.main import create_app
from ace_platform.api.routes.account import (
    DeleteAccountRequest,
    delete_account,
    export_account_data,
)
from ace_platform.db.models import (
    AuditEventType,
    AuditSeverity,
    EvolutionJobStatus,
    OutcomeStatus,
    PlaybookSource,
    PlaybookStatus,
    SubscriptionStatus,
)


class _ScalarResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


def test_account_routes_registered():
    app = create_app()
    routes = [route.path for route in app.routes]
    assert "/account" in routes
    assert "/account/export" in routes
    assert "/account/audit-logs" in routes


def test_account_export_requires_auth():
    client = TestClient(create_app())
    resp = client.get("/account/export")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


def test_account_delete_requires_auth():
    client = TestClient(create_app())
    resp = client.request("DELETE", "/account", json={"confirm": "DELETE"})
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


def test_account_audit_logs_requires_auth():
    client = TestClient(create_app())
    resp = client.get("/account/audit-logs")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_export_includes_expected_keys_and_omits_secrets():
    user_id = uuid4()
    now = datetime.now(UTC)

    current_user = MagicMock()
    current_user.id = user_id
    current_user.email = "test@example.com"
    current_user.is_active = True
    current_user.email_verified = True
    current_user.subscription_tier = "starter"
    current_user.subscription_status = SubscriptionStatus.ACTIVE
    current_user.subscription_current_period_end = None
    current_user.has_used_trial = False
    current_user.trial_ends_at = None
    current_user.has_payment_method = True
    current_user.stripe_customer_id = "cus_test"
    current_user.stripe_subscription_id = "sub_test"
    current_user.created_at = now
    current_user.updated_at = now

    version = MagicMock()
    version.id = uuid4()
    version.version_number = 1
    version.content = "playbook content"
    version.bullet_count = 0
    version.diff_summary = None
    version.created_by_job_id = None
    version.created_at = now

    outcome = MagicMock()
    outcome.id = uuid4()
    outcome.task_description = "Do thing"
    outcome.outcome_status = OutcomeStatus.SUCCESS
    outcome.notes = None
    outcome.reasoning_trace = None
    outcome.created_at = now
    outcome.processed_at = None
    outcome.evolution_job_id = None

    evo = MagicMock()
    evo.id = uuid4()
    evo.status = EvolutionJobStatus.COMPLETED
    evo.from_version_id = None
    evo.to_version_id = None
    evo.outcomes_processed = 1
    evo.error_message = None
    evo.created_at = now
    evo.started_at = now
    evo.completed_at = now

    playbook = MagicMock()
    playbook.id = uuid4()
    playbook.name = "PB"
    playbook.description = "desc"
    playbook.status = PlaybookStatus.ACTIVE
    playbook.source = PlaybookSource.USER_CREATED
    playbook.current_version_id = version.id
    playbook.created_at = now
    playbook.updated_at = now
    playbook.versions = [version]
    playbook.outcomes = [outcome]
    playbook.evolution_jobs = [evo]

    api_key = MagicMock()
    api_key.id = uuid4()
    api_key.name = "Key"
    api_key.key_prefix = "ace_test"
    api_key.scopes = ["playbooks:read"]
    api_key.created_at = now
    api_key.last_used_at = None
    api_key.revoked_at = None
    api_key.is_active = True

    oauth = MagicMock()
    oauth.id = uuid4()
    oauth.provider = SimpleNamespace(value="google")
    oauth.provider_user_id = "123"
    oauth.provider_email = "test@example.com"
    oauth.created_at = now
    oauth.updated_at = now

    usage = MagicMock()
    usage.id = uuid4()
    usage.playbook_id = playbook.id
    usage.evolution_job_id = evo.id
    usage.operation = "evolution_reflection"
    usage.model = "gpt-4o-mini"
    usage.prompt_tokens = 10
    usage.completion_tokens = 5
    usage.total_tokens = 15
    usage.cost_usd = Decimal("0.000001")
    usage.request_id = None
    usage.extra_data = None
    usage.created_at = now

    audit = MagicMock()
    audit.id = uuid4()
    audit.event_type = AuditEventType.LOGIN_SUCCESS
    audit.severity = AuditSeverity.INFO
    audit.created_at = now
    audit.ip_address = "127.0.0.1"
    audit.user_agent = "test"
    audit.details = {"method": "password"}

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[
            _ScalarResult([playbook]),
            _ScalarResult([api_key]),
            _ScalarResult([oauth]),
            _ScalarResult([usage]),
            _ScalarResult([audit]),
        ]
    )
    db.commit = AsyncMock()

    req = MagicMock(spec=Request)

    with patch("ace_platform.api.routes.account.audit_data_exported", new=AsyncMock()):
        resp = await export_account_data(req, db, current_user)

    payload = json.loads(resp.body.decode("utf-8"))

    assert payload["user"]["email"] == "test@example.com"
    assert payload["playbooks"][0]["versions"][0]["content"] == "playbook content"
    assert payload["api_keys"][0]["key_prefix"] == "ace_test"
    assert "hashed_key" not in payload["api_keys"][0]


@pytest.mark.asyncio
async def test_delete_account_requires_confirm_phrase():
    db = AsyncMock()
    current_user = MagicMock()
    current_user.hashed_password = None
    current_user.id = uuid4()

    with pytest.raises(HTTPException) as exc_info:
        await delete_account(
            DeleteAccountRequest(confirm="NOPE"),
            MagicMock(spec=Request),
            db,
            current_user,
        )

    assert exc_info.value.status_code == 400
