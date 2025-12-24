"""Tests for usage limits.

These tests verify:
1. Tier limit definitions
2. Usage status calculation
3. Limit checking functions
4. Model access restrictions
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ace_platform.core.limits import (
    TIER_LIMITS,
    SubscriptionTier,
    TierLimits,
    UsageStatus,
    can_use_model,
    check_can_make_request,
    get_billing_period_start,
    get_tier_limits,
    get_user_usage_status,
)


class TestTierLimits:
    """Tests for tier limit definitions."""

    def test_all_tiers_have_limits(self):
        """Test that all tiers have defined limits."""
        for tier in SubscriptionTier:
            assert tier in TIER_LIMITS
            assert isinstance(TIER_LIMITS[tier], TierLimits)

    def test_free_tier_has_limits(self):
        """Test free tier has restrictive limits."""
        limits = get_tier_limits(SubscriptionTier.FREE)
        assert limits.monthly_requests == 100
        assert limits.monthly_tokens == 100_000
        assert limits.max_playbooks == 3
        assert limits.can_use_premium_models is False

    def test_starter_tier_higher_than_free(self):
        """Test starter tier has higher limits than free."""
        free = get_tier_limits(SubscriptionTier.FREE)
        starter = get_tier_limits(SubscriptionTier.STARTER)

        assert starter.monthly_requests > free.monthly_requests
        assert starter.monthly_tokens > free.monthly_tokens
        assert starter.max_playbooks > free.max_playbooks
        assert starter.can_use_premium_models is True

    def test_professional_tier_higher_than_starter(self):
        """Test professional tier has higher limits than starter."""
        starter = get_tier_limits(SubscriptionTier.STARTER)
        pro = get_tier_limits(SubscriptionTier.PROFESSIONAL)

        assert pro.monthly_requests > starter.monthly_requests
        assert pro.monthly_tokens > starter.monthly_tokens
        assert pro.max_playbooks > starter.max_playbooks

    def test_enterprise_tier_unlimited(self):
        """Test enterprise tier has unlimited usage."""
        limits = get_tier_limits(SubscriptionTier.ENTERPRISE)
        assert limits.monthly_requests is None
        assert limits.monthly_tokens is None
        assert limits.monthly_cost_usd is None
        assert limits.max_playbooks is None

    def test_tier_limits_immutable(self):
        """Test that TierLimits is immutable."""
        limits = get_tier_limits(SubscriptionTier.FREE)
        with pytest.raises(AttributeError):
            limits.monthly_requests = 999


class TestBillingPeriod:
    """Tests for billing period calculation."""

    def test_billing_period_start_is_first_of_month(self):
        """Test billing period starts on first of month."""
        start = get_billing_period_start()
        assert start.day == 1
        assert start.hour == 0
        assert start.minute == 0
        assert start.second == 0
        assert start.tzinfo == UTC

    def test_billing_period_is_current_month(self):
        """Test billing period is in current month."""
        start = get_billing_period_start()
        now = datetime.now(UTC)
        assert start.year == now.year
        assert start.month == now.month


class TestUsageStatus:
    """Tests for get_user_usage_status."""

    @pytest.mark.asyncio
    async def test_usage_status_within_limits(self):
        """Test usage status when within limits."""
        user_id = uuid4()
        mock_db = AsyncMock()

        # Mock usage summary - low usage
        mock_summary = MagicMock()
        mock_summary.total_requests = 10
        mock_summary.total_tokens = 5000
        mock_summary.total_cost_usd = Decimal("0.05")

        with patch(
            "ace_platform.core.limits.get_user_usage_summary",
            return_value=mock_summary,
        ):
            status = await get_user_usage_status(mock_db, user_id, SubscriptionTier.FREE)

        assert status.is_within_limits is True
        assert status.limit_exceeded is None
        assert status.current_requests == 10
        assert status.remaining_requests == 90  # 100 - 10

    @pytest.mark.asyncio
    async def test_usage_status_exceeds_requests(self):
        """Test usage status when requests exceed limit."""
        user_id = uuid4()
        mock_db = AsyncMock()

        mock_summary = MagicMock()
        mock_summary.total_requests = 150  # Over 100 limit
        mock_summary.total_tokens = 50000
        mock_summary.total_cost_usd = Decimal("0.50")

        with patch(
            "ace_platform.core.limits.get_user_usage_summary",
            return_value=mock_summary,
        ):
            status = await get_user_usage_status(mock_db, user_id, SubscriptionTier.FREE)

        assert status.is_within_limits is False
        assert status.limit_exceeded == "monthly_requests"
        assert status.remaining_requests == 0

    @pytest.mark.asyncio
    async def test_usage_status_exceeds_tokens(self):
        """Test usage status when tokens exceed limit."""
        user_id = uuid4()
        mock_db = AsyncMock()

        mock_summary = MagicMock()
        mock_summary.total_requests = 50
        mock_summary.total_tokens = 150000  # Over 100k limit
        mock_summary.total_cost_usd = Decimal("0.50")

        with patch(
            "ace_platform.core.limits.get_user_usage_summary",
            return_value=mock_summary,
        ):
            status = await get_user_usage_status(mock_db, user_id, SubscriptionTier.FREE)

        assert status.is_within_limits is False
        assert status.limit_exceeded == "monthly_tokens"

    @pytest.mark.asyncio
    async def test_enterprise_always_within_limits(self):
        """Test enterprise tier is always within limits."""
        user_id = uuid4()
        mock_db = AsyncMock()

        mock_summary = MagicMock()
        mock_summary.total_requests = 1_000_000
        mock_summary.total_tokens = 1_000_000_000
        mock_summary.total_cost_usd = Decimal("10000.00")

        with patch(
            "ace_platform.core.limits.get_user_usage_summary",
            return_value=mock_summary,
        ):
            status = await get_user_usage_status(mock_db, user_id, SubscriptionTier.ENTERPRISE)

        assert status.is_within_limits is True
        assert status.remaining_requests is None
        assert status.remaining_tokens is None


class TestCheckCanMakeRequest:
    """Tests for check_can_make_request."""

    @pytest.mark.asyncio
    async def test_can_make_request_within_limits(self):
        """Test request allowed when within limits."""
        user_id = uuid4()
        mock_db = AsyncMock()

        mock_summary = MagicMock()
        mock_summary.total_requests = 10
        mock_summary.total_tokens = 5000
        mock_summary.total_cost_usd = Decimal("0.05")

        with patch(
            "ace_platform.core.limits.get_user_usage_summary",
            return_value=mock_summary,
        ):
            can_proceed, error = await check_can_make_request(
                mock_db, user_id, SubscriptionTier.FREE
            )

        assert can_proceed is True
        assert error is None

    @pytest.mark.asyncio
    async def test_cannot_make_request_over_limit(self):
        """Test request blocked when over limit."""
        user_id = uuid4()
        mock_db = AsyncMock()

        mock_summary = MagicMock()
        mock_summary.total_requests = 150
        mock_summary.total_tokens = 50000
        mock_summary.total_cost_usd = Decimal("0.50")

        with patch(
            "ace_platform.core.limits.get_user_usage_summary",
            return_value=mock_summary,
        ):
            can_proceed, error = await check_can_make_request(
                mock_db, user_id, SubscriptionTier.FREE
            )

        assert can_proceed is False
        assert "limit exceeded" in error.lower()

    @pytest.mark.asyncio
    async def test_request_blocked_if_estimated_exceeds(self):
        """Test request blocked if estimated tokens exceed remaining."""
        user_id = uuid4()
        mock_db = AsyncMock()

        mock_summary = MagicMock()
        mock_summary.total_requests = 10
        mock_summary.total_tokens = 95000  # 5k remaining
        mock_summary.total_cost_usd = Decimal("0.50")

        with patch(
            "ace_platform.core.limits.get_user_usage_summary",
            return_value=mock_summary,
        ):
            can_proceed, error = await check_can_make_request(
                mock_db,
                user_id,
                SubscriptionTier.FREE,
                estimated_tokens=10000,  # Request 10k but only 5k remaining
            )

        assert can_proceed is False
        assert "token limit" in error.lower()


class TestModelAccess:
    """Tests for model access restrictions."""

    def test_free_tier_cannot_use_premium(self):
        """Test free tier cannot use premium models."""
        assert can_use_model(SubscriptionTier.FREE, "gpt-4o-mini") is True
        assert can_use_model(SubscriptionTier.FREE, "gpt-3.5-turbo") is True
        assert can_use_model(SubscriptionTier.FREE, "o1") is False
        assert can_use_model(SubscriptionTier.FREE, "o1-mini") is False
        assert can_use_model(SubscriptionTier.FREE, "gpt-4-turbo") is False

    def test_starter_tier_can_use_premium(self):
        """Test starter tier can use premium models."""
        assert can_use_model(SubscriptionTier.STARTER, "gpt-4o") is True
        assert can_use_model(SubscriptionTier.STARTER, "o1") is True
        assert can_use_model(SubscriptionTier.STARTER, "gpt-4-turbo") is True

    def test_enterprise_can_use_all_models(self):
        """Test enterprise tier can use all models."""
        assert can_use_model(SubscriptionTier.ENTERPRISE, "gpt-4o") is True
        assert can_use_model(SubscriptionTier.ENTERPRISE, "o1") is True
        assert can_use_model(SubscriptionTier.ENTERPRISE, "gpt-4-turbo") is True


class TestDataclasses:
    """Tests for dataclass structure."""

    def test_usage_status_fields(self):
        """Test UsageStatus has expected fields."""
        status = UsageStatus(
            tier=SubscriptionTier.FREE,
            limits=get_tier_limits(SubscriptionTier.FREE),
            current_requests=10,
            current_tokens=5000,
            current_cost_usd=Decimal("0.05"),
            remaining_requests=90,
            remaining_tokens=95000,
            remaining_cost_usd=Decimal("0.95"),
            is_within_limits=True,
            limit_exceeded=None,
        )
        assert status.tier == SubscriptionTier.FREE
        assert status.is_within_limits is True
