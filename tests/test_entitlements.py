"""Tests for the workspace entitlements service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ace_platform.core.entitlements import resolve_workspace_entitlements
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


def _make_usage_status(tier: SubscriptionTier) -> UsageStatus:
    limits = get_tier_limits(tier)
    return UsageStatus(
        tier=tier,
        limits=limits,
        current_evolution_runs=2,
        current_total_tokens=1_234,
        current_cost_usd=Decimal("0.42"),
        remaining_evolution_runs=None
        if limits.monthly_evolution_runs is None
        else max(0, limits.monthly_evolution_runs - 2),
        remaining_cost_usd=None
        if limits.monthly_cost_limit_usd is None
        else limits.monthly_cost_limit_usd - Decimal("0.42"),
        is_within_limits=True,
        limit_exceeded=None,
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
