"""Tests for the workspace entitlements service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ace_platform.core.entitlements import (
    check_workspace_managed_inference_allowed,
    resolve_workspace_entitlements,
)
from ace_platform.core.limits import SubscriptionTier, UsageStatus, get_tier_limits
from ace_platform.db.models import SubscriptionStatus


def _make_user(**overrides):
    now = datetime.now(UTC)
    defaults = {
        "id": uuid4(),
        "subscription_tier": None,
        "subscription_status": SubscriptionStatus.NONE,
        "trial_ends_at": None,
        "is_admin": False,
        "email": "user@example.com",
        "created_at": now,
        "updated_at": now,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_usage_status(
    tier: SubscriptionTier,
    *,
    storage_bytes: int = 0,
    managed_inference_requests: int = 0,
    total_tokens: int = 1_234,
    total_cost_usd: Decimal = Decimal("0.42"),
) -> UsageStatus:
    limits = get_tier_limits(tier)
    return UsageStatus(
        tier=tier,
        limits=limits,
        current_evolution_runs=2,
        current_total_tokens=total_tokens,
        current_cost_usd=total_cost_usd,
        remaining_evolution_runs=None
        if limits.monthly_evolution_runs is None
        else max(0, limits.monthly_evolution_runs - 2),
        remaining_cost_usd=None
        if limits.monthly_cost_limit_usd is None
        else limits.monthly_cost_limit_usd - total_cost_usd,
        remaining_storage_bytes=None
        if limits.storage_limit_bytes is None
        else max(0, limits.storage_limit_bytes - storage_bytes),
        is_within_limits=True,
        limit_exceeded=None,
        current_managed_inference_requests=managed_inference_requests,
        current_managed_inference_tokens=total_tokens,
        current_managed_inference_cost_usd=total_cost_usd,
        current_storage_bytes=storage_bytes,
    )


@pytest.mark.asyncio
async def test_free_user_gets_no_enabled_features(monkeypatch):
    user = _make_user()
    monkeypatch.setattr(
        "ace_platform.core.entitlements.get_user_usage_status",
        AsyncMock(return_value=_make_usage_status(SubscriptionTier.FREE)),
    )

    snapshot = await resolve_workspace_entitlements(object(), user)

    assert snapshot.plan == "personal"
    assert snapshot.seat_limit == 1
    assert snapshot.enabled_features == ()
    assert snapshot.access.subscription_tier == SubscriptionTier.FREE
    assert snapshot.access.effective_tier == SubscriptionTier.FREE
    assert snapshot.access.has_feature_access is False
    assert snapshot.entitlements.cloud_sync is False
    assert snapshot.entitlements.managed_inference is False
    assert snapshot.usage_limits.storage_bytes.current == 0
    assert snapshot.usage_limits.hosted_eval_runs.hard_limit == 5


@pytest.mark.asyncio
async def test_paid_personal_user_gets_convenience_features(monkeypatch):
    user = _make_user(
        subscription_tier="starter",
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    monkeypatch.setattr(
        "ace_platform.core.entitlements.get_user_usage_status",
        AsyncMock(return_value=_make_usage_status(SubscriptionTier.STARTER)),
    )

    snapshot = await resolve_workspace_entitlements(object(), user)

    assert snapshot.plan == "personal"
    assert snapshot.access.subscription_tier == SubscriptionTier.STARTER
    assert snapshot.access.effective_tier == SubscriptionTier.STARTER
    assert snapshot.access.has_feature_access is True
    assert snapshot.entitlements.cloud_sync is True
    assert snapshot.entitlements.hosted_backups is True
    assert snapshot.entitlements.managed_inference is True
    assert snapshot.entitlements.hosted_evals is True
    assert snapshot.entitlements.invite_members is False
    assert snapshot.usage_limits.monthly_evolution_runs == 100
    assert snapshot.usage_limits.max_playbooks == 5
    assert snapshot.usage_limits.storage_bytes.current == 0


@pytest.mark.asyncio
async def test_trial_user_keeps_features_but_uses_free_limits(monkeypatch):
    user = _make_user(
        subscription_tier="starter",
        subscription_status=SubscriptionStatus.ACTIVE,
        trial_ends_at=datetime.now(UTC) + timedelta(days=3),
    )
    monkeypatch.setattr(
        "ace_platform.core.entitlements.get_user_usage_status",
        AsyncMock(return_value=_make_usage_status(SubscriptionTier.FREE)),
    )

    snapshot = await resolve_workspace_entitlements(object(), user)

    assert snapshot.access.subscription_tier == SubscriptionTier.STARTER
    assert snapshot.access.effective_tier == SubscriptionTier.FREE
    assert snapshot.access.has_feature_access is True
    assert snapshot.access.is_trialing is True
    assert snapshot.entitlements.managed_inference is True
    assert snapshot.usage_limits.monthly_evolution_runs == 5
    assert snapshot.usage_limits.hosted_eval_runs.hard_limit == 5


@pytest.mark.asyncio
async def test_enterprise_user_gets_governance_features(monkeypatch):
    user = _make_user(
        subscription_tier="enterprise",
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    monkeypatch.setattr(
        "ace_platform.core.entitlements.get_user_usage_status",
        AsyncMock(return_value=_make_usage_status(SubscriptionTier.ENTERPRISE)),
    )

    snapshot = await resolve_workspace_entitlements(object(), user)

    assert snapshot.plan == "enterprise"
    assert snapshot.seat_limit is None
    assert snapshot.entitlements.invite_members is True
    assert snapshot.entitlements.shared_workspace is True
    assert snapshot.entitlements.approvals is True
    assert snapshot.entitlements.rbac is True
    assert snapshot.entitlements.sso is True
    assert snapshot.entitlements.audit_logs is True


@pytest.mark.asyncio
async def test_workspace_usage_config_adds_soft_and_hard_thresholds(monkeypatch):
    user = _make_user(
        subscription_tier="starter",
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    workspace = SimpleNamespace(
        id=uuid4(),
        plan=SimpleNamespace(value="personal"),
        seat_limit=1,
        deployment_mode=SimpleNamespace(value="cloud"),
        usage_limits={
            "storage_bytes": {"soft_limit": 1_024},
            "managed_inference_requests": {"hard_limit": 3},
            "managed_inference_tokens": {"soft_limit": 500, "hard_limit": 1_000},
            "hosted_eval_runs": {"soft_limit": 2, "hard_limit": 4},
        },
    )
    usage_status = _make_usage_status(
        SubscriptionTier.STARTER,
        storage_bytes=2_048,
        managed_inference_requests=3,
        total_tokens=750,
    )
    usage_status.current_evolution_runs = 3
    usage_status.remaining_evolution_runs = 97

    monkeypatch.setattr(
        "ace_platform.core.entitlements.get_user_usage_status",
        AsyncMock(return_value=usage_status),
    )

    snapshot = await resolve_workspace_entitlements(object(), user, workspace=workspace)

    assert snapshot.usage_limits.storage_bytes.status == "warning"
    assert snapshot.usage_limits.hosted_eval_runs.soft_limit == 2
    assert snapshot.usage_limits.hosted_eval_runs.hard_limit == 4
    assert snapshot.usage_limits.managed_inference_requests.status == "blocked"
    assert snapshot.usage_limits.managed_inference_tokens.status == "warning"
    assert snapshot.usage_limits.warning_fields == (
        "storage_bytes",
        "hosted_eval_runs",
        "managed_inference_tokens",
    )
    assert snapshot.usage_limits.blocked_fields == ("managed_inference_requests",)
    assert snapshot.usage_limits.is_within_limits is False
    assert snapshot.usage_limits.limit_exceeded == "managed_inference_requests"


@pytest.mark.asyncio
async def test_invalid_workspace_usage_limit_strings_are_ignored(monkeypatch):
    user = _make_user(
        subscription_tier="starter",
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    workspace = SimpleNamespace(
        id=uuid4(),
        plan=SimpleNamespace(value="personal"),
        seat_limit=1,
        deployment_mode=SimpleNamespace(value="cloud"),
        usage_limits={
            "storage_bytes": "100MB",
            "managed_inference_requests": "unlimited",
            "managed_inference_tokens": {"soft_limit": "soon", "hard_limit": "later"},
        },
    )
    monkeypatch.setattr(
        "ace_platform.core.entitlements.get_user_usage_status",
        AsyncMock(return_value=_make_usage_status(SubscriptionTier.STARTER)),
    )

    snapshot = await resolve_workspace_entitlements(object(), user, workspace=workspace)
    starter_limits = get_tier_limits(SubscriptionTier.STARTER)

    assert snapshot.usage_limits.storage_bytes.soft_limit is None
    assert snapshot.usage_limits.storage_bytes.hard_limit == starter_limits.storage_limit_bytes
    assert snapshot.usage_limits.managed_inference_requests.hard_limit is None
    assert snapshot.usage_limits.managed_inference_tokens.soft_limit is None
    assert snapshot.usage_limits.managed_inference_tokens.hard_limit is None


@pytest.mark.asyncio
async def test_trialing_workspace_subscription_maps_access_status_without_crashing(monkeypatch):
    user = _make_user(
        subscription_tier="starter",
        subscription_status=SubscriptionStatus.NONE,
    )
    workspace = SimpleNamespace(
        id=uuid4(),
        plan=SimpleNamespace(value="personal"),
        seat_limit=1,
        deployment_mode=SimpleNamespace(value="cloud"),
        subscription=SimpleNamespace(status=SimpleNamespace(value="trialing"), plan_code="starter"),
        usage_limits={},
    )
    monkeypatch.setattr(
        "ace_platform.core.entitlements.get_user_usage_status",
        AsyncMock(return_value=_make_usage_status(SubscriptionTier.STARTER)),
    )

    snapshot = await resolve_workspace_entitlements(object(), user, workspace=workspace)

    assert snapshot.access.subscription_status == SubscriptionStatus.ACTIVE
    assert snapshot.access.has_feature_access is True


@pytest.mark.asyncio
async def test_managed_inference_check_scopes_usage_to_workspace(monkeypatch):
    user = _make_user(
        subscription_tier="starter",
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    workspace = SimpleNamespace(
        id=uuid4(),
        plan=SimpleNamespace(value="personal"),
        seat_limit=1,
        deployment_mode=SimpleNamespace(value="cloud"),
        entitlements=None,
        subscription=None,
        usage_limits={},
    )
    get_usage_counter_summary = AsyncMock(
        return_value=SimpleNamespace(
            request_count=0,
            total_tokens=0,
            total_cost_usd=Decimal("0"),
        )
    )
    get_user_usage_status = AsyncMock()
    monkeypatch.setattr(
        "ace_platform.core.entitlements.get_user_usage_status",
        get_user_usage_status,
    )
    monkeypatch.setattr(
        "ace_platform.core.entitlements.get_usage_counter_summary",
        get_usage_counter_summary,
    )

    allowed, error_message = await check_workspace_managed_inference_allowed(
        object(),
        user,
        workspace=workspace,
    )

    assert allowed is True
    assert error_message is None
    get_user_usage_status.assert_not_awaited()
    assert get_usage_counter_summary.await_args.kwargs["workspace_id"] == workspace.id


@pytest.mark.asyncio
async def test_managed_inference_check_accepts_lightweight_user_with_workspace_subscription(
    monkeypatch,
):
    db = object()
    user = SimpleNamespace(id=uuid4())
    workspace = SimpleNamespace(
        id=uuid4(),
        plan=SimpleNamespace(value="personal"),
        seat_limit=1,
        deployment_mode=SimpleNamespace(value="cloud"),
        entitlements=None,
        subscription=SimpleNamespace(status=SimpleNamespace(value="active"), plan_code="starter"),
        usage_limits={},
    )
    get_user_usage_status = AsyncMock(return_value=_make_usage_status(SubscriptionTier.STARTER))
    get_usage_counter_summary = AsyncMock(
        return_value=SimpleNamespace(
            request_count=0,
            total_tokens=0,
            total_cost_usd=Decimal("0"),
        )
    )
    monkeypatch.setattr(
        "ace_platform.core.entitlements.get_user_usage_status",
        get_user_usage_status,
    )
    monkeypatch.setattr(
        "ace_platform.core.entitlements.get_usage_counter_summary",
        get_usage_counter_summary,
    )

    allowed, error_message = await check_workspace_managed_inference_allowed(
        db,
        user,
        workspace=workspace,
    )

    assert allowed is True
    assert error_message is None
    get_user_usage_status.assert_not_awaited()
    assert get_usage_counter_summary.await_args.kwargs["workspace_id"] == workspace.id


@pytest.mark.asyncio
async def test_managed_inference_check_accepts_trialing_workspace_without_full_snapshot(
    monkeypatch,
):
    user = _make_user(
        subscription_tier="starter",
        subscription_status=SubscriptionStatus.NONE,
    )
    workspace = SimpleNamespace(
        id=uuid4(),
        plan=SimpleNamespace(value="personal"),
        seat_limit=1,
        deployment_mode=SimpleNamespace(value="cloud"),
        entitlements=None,
        subscription=SimpleNamespace(status=SimpleNamespace(value="trialing"), plan_code="starter"),
        usage_limits={},
    )
    get_user_usage_status = AsyncMock()
    get_usage_counter_summary = AsyncMock(
        return_value=SimpleNamespace(
            request_count=0,
            total_tokens=0,
            total_cost_usd=Decimal("0"),
        )
    )
    monkeypatch.setattr(
        "ace_platform.core.entitlements.get_user_usage_status",
        get_user_usage_status,
    )
    monkeypatch.setattr(
        "ace_platform.core.entitlements.get_usage_counter_summary",
        get_usage_counter_summary,
    )

    allowed, error_message = await check_workspace_managed_inference_allowed(
        object(),
        user,
        workspace=workspace,
    )

    assert allowed is True
    assert error_message is None
    get_user_usage_status.assert_not_awaited()
    assert get_usage_counter_summary.await_args.kwargs["workspace_id"] == workspace.id


@pytest.mark.asyncio
async def test_managed_inference_check_blocks_when_workspace_subscription_lacks_access(
    monkeypatch,
):
    user = _make_user(
        subscription_tier="starter",
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    workspace = SimpleNamespace(
        id=uuid4(),
        plan=SimpleNamespace(value="personal"),
        seat_limit=1,
        deployment_mode=SimpleNamespace(value="cloud"),
        entitlements=None,
        subscription=SimpleNamespace(status=SimpleNamespace(value="unpaid"), plan_code="starter"),
        usage_limits={},
    )
    monkeypatch.setattr(
        "ace_platform.core.entitlements.get_user_usage_status",
        AsyncMock(return_value=_make_usage_status(SubscriptionTier.STARTER)),
    )
    get_usage_counter_summary = AsyncMock()
    monkeypatch.setattr(
        "ace_platform.core.entitlements.get_usage_counter_summary",
        get_usage_counter_summary,
    )

    allowed, error_message = await check_workspace_managed_inference_allowed(
        object(),
        user,
        workspace=workspace,
    )

    assert allowed is False
    assert error_message == "Managed inference is not enabled for this workspace plan."
    get_usage_counter_summary.assert_not_awaited()


@pytest.mark.asyncio
async def test_managed_inference_check_blocks_when_workspace_disables_feature(monkeypatch):
    user = _make_user(
        subscription_tier="starter",
        subscription_status=SubscriptionStatus.ACTIVE,
    )
    workspace = SimpleNamespace(
        id=uuid4(),
        plan=SimpleNamespace(value="personal"),
        seat_limit=1,
        deployment_mode=SimpleNamespace(value="cloud"),
        entitlements=SimpleNamespace(managed_inference=False),
        subscription=SimpleNamespace(status=SimpleNamespace(value="active"), plan_code="starter"),
        usage_limits={},
    )
    monkeypatch.setattr(
        "ace_platform.core.entitlements.get_user_usage_status",
        AsyncMock(return_value=_make_usage_status(SubscriptionTier.STARTER)),
    )
    get_usage_counter_summary = AsyncMock()
    monkeypatch.setattr(
        "ace_platform.core.entitlements.get_usage_counter_summary",
        get_usage_counter_summary,
    )

    allowed, error_message = await check_workspace_managed_inference_allowed(
        object(),
        user,
        workspace=workspace,
    )

    assert allowed is False
    assert error_message == "Managed inference is disabled for this workspace."
    get_usage_counter_summary.assert_not_awaited()
