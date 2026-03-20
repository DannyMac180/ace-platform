"""Tests for the workspace-aware subscription service."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from ace_platform.core.limits import SubscriptionTier
from ace_platform.core.subscription_service import (
    FREE_PLAN_CODE,
    get_plan_catalog,
    get_plan_catalog_entry_for_tier,
    get_subscription_tier_for_plan_code,
    sync_workspace_subscription_state,
)
from ace_platform.db.models import (
    WorkspaceBillingProvider,
    WorkspacePlan,
    WorkspaceSubscriptionStatus,
)


def test_plan_catalog_includes_workspace_aware_plan_codes():
    catalog = get_plan_catalog()
    codes = {entry.code for entry in catalog}

    assert FREE_PLAN_CODE in codes
    assert "personal-starter" in codes
    assert "personal-pro" in codes
    assert "personal-ultra" in codes
    assert "enterprise" in codes

    starter = get_plan_catalog_entry_for_tier(SubscriptionTier.STARTER)
    assert starter.workspace_plan == WorkspacePlan.PERSONAL
    assert starter.prices

    enterprise = get_plan_catalog_entry_for_tier(SubscriptionTier.ENTERPRISE)
    assert enterprise.workspace_plan == WorkspacePlan.ENTERPRISE
    assert enterprise.contact_sales is True


def test_plan_code_round_trips_to_subscription_tier():
    assert get_subscription_tier_for_plan_code("personal-starter") == SubscriptionTier.STARTER
    assert get_subscription_tier_for_plan_code("enterprise") == SubscriptionTier.ENTERPRISE
    assert get_subscription_tier_for_plan_code("unknown-plan") is None


@pytest.mark.asyncio
async def test_sync_workspace_subscription_state_upserts_workspace_subscription():
    workspace = SimpleNamespace(
        id=uuid4(),
        plan=WorkspacePlan.PERSONAL,
        seat_limit=1,
        entitlements=None,
        subscription=None,
    )
    user = SimpleNamespace(id=uuid4(), email="billing@example.com")
    db = AsyncMock()

    with patch(
        "ace_platform.core.subscription_service.ensure_billing_workspace",
        new=AsyncMock(return_value=workspace),
    ):
        subscription = await sync_workspace_subscription_state(
            db,
            user,
            status=WorkspaceSubscriptionStatus.ACTIVE,
            subscription_tier=SubscriptionTier.PRO,
            provider_customer_id="cus_test123",
            provider_subscription_id="sub_test123",
        )

    assert workspace.plan == WorkspacePlan.PERSONAL
    assert subscription.billing_provider == WorkspaceBillingProvider.STRIPE
    assert subscription.status == WorkspaceSubscriptionStatus.ACTIVE
    assert subscription.plan_code == "personal-pro"
    assert subscription.provider_customer_id == "cus_test123"
    assert subscription.provider_subscription_id == "sub_test123"
    assert workspace.entitlements is not None
    assert workspace.entitlements.cloud_sync is True
    assert workspace.entitlements.invite_members is False
    db.flush.assert_awaited_once()
