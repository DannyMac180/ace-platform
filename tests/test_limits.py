"""Tests for usage limits.

These tests verify:
1. Tier limit definitions
2. Usage status calculation
3. Limit checking functions
4. Model access restrictions
5. Spending cap enforcement
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
    can_create_playbook,
    can_use_model,
    check_can_evolve,
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
        """Test free tier has restrictive limits (internal use only)."""
        limits = get_tier_limits(SubscriptionTier.FREE)
        assert limits.monthly_evolution_runs == 10
        assert limits.max_playbooks == 1
        assert limits.can_use_premium_models is False

    def test_starter_tier_limits(self):
        """Test starter tier has correct limits per BILLING_DECISIONS.md."""
        limits = get_tier_limits(SubscriptionTier.STARTER)
        assert limits.monthly_evolution_runs == 100
        assert limits.max_playbooks == 5
        assert limits.can_use_premium_models is True

    def test_pro_tier_higher_than_starter(self):
        """Test pro tier has higher limits than starter."""
        starter = get_tier_limits(SubscriptionTier.STARTER)
        pro = get_tier_limits(SubscriptionTier.PRO)

        assert pro.monthly_evolution_runs > starter.monthly_evolution_runs
        assert pro.max_playbooks > starter.max_playbooks
        assert pro.monthly_evolution_runs == 500

    def test_ultra_tier_higher_than_pro(self):
        """Test ultra tier has higher limits than pro."""
        pro = get_tier_limits(SubscriptionTier.PRO)
        ultra = get_tier_limits(SubscriptionTier.ULTRA)

        assert ultra.monthly_evolution_runs > pro.monthly_evolution_runs
        assert ultra.max_playbooks > pro.max_playbooks
        assert ultra.monthly_evolution_runs == 2000

    def test_enterprise_tier_unlimited(self):
        """Test enterprise tier has unlimited usage."""
        limits = get_tier_limits(SubscriptionTier.ENTERPRISE)
        assert limits.monthly_evolution_runs is None
        assert limits.max_playbooks is None

    def test_tier_limits_immutable(self):
        """Test that TierLimits is immutable."""
        limits = get_tier_limits(SubscriptionTier.FREE)
        with pytest.raises(AttributeError):
            limits.monthly_evolution_runs = 999


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
        mock_db.scalar = AsyncMock(return_value=5)

        # Mock usage summary - low usage
        mock_summary = MagicMock()
        mock_summary.total_tokens = 1234
        mock_summary.total_cost_usd = Decimal("0.50")  # Under $1 limit

        with patch(
            "ace_platform.core.limits.get_user_usage_summary",
            return_value=mock_summary,
        ):
            status = await get_user_usage_status(mock_db, user_id, SubscriptionTier.FREE)

        assert status.is_within_limits is True
        assert status.limit_exceeded is None
        assert status.current_evolution_runs == 5
        assert status.remaining_evolution_runs == 5  # 10 - 5
        assert status.current_total_tokens == 1234
        assert status.current_cost_usd == Decimal("0.50")
        assert status.remaining_cost_usd == Decimal("0.50")  # $1 - $0.50

    @pytest.mark.asyncio
    async def test_usage_status_exceeds_limit(self):
        """Test usage status when evolution runs exceed limit."""
        user_id = uuid4()
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=15)

        mock_summary = MagicMock()
        mock_summary.total_tokens = 1234
        mock_summary.total_cost_usd = Decimal("0.50")  # Under cost limit

        with patch(
            "ace_platform.core.limits.get_user_usage_summary",
            return_value=mock_summary,
        ):
            status = await get_user_usage_status(mock_db, user_id, SubscriptionTier.FREE)

        assert status.is_within_limits is False
        assert status.limit_exceeded == "monthly_evolution_runs"
        assert status.remaining_evolution_runs == 0

    @pytest.mark.asyncio
    async def test_starter_tier_usage_status(self):
        """Test usage status for starter tier (100 runs/month)."""
        user_id = uuid4()
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=50)

        mock_summary = MagicMock()
        mock_summary.total_tokens = 1234
        mock_summary.total_cost_usd = Decimal("4.50")  # Under $9 limit

        with patch(
            "ace_platform.core.limits.get_user_usage_summary",
            return_value=mock_summary,
        ):
            status = await get_user_usage_status(mock_db, user_id, SubscriptionTier.STARTER)

        assert status.is_within_limits is True
        assert status.remaining_evolution_runs == 50  # 100 - 50
        assert status.remaining_cost_usd == Decimal("4.50")  # $9 - $4.50

    @pytest.mark.asyncio
    async def test_enterprise_always_within_limits(self):
        """Test enterprise tier is always within limits."""
        user_id = uuid4()
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=1_000_000)

        mock_summary = MagicMock()
        mock_summary.total_tokens = 1234
        mock_summary.total_cost_usd = Decimal("10000.00")  # Huge cost

        with patch(
            "ace_platform.core.limits.get_user_usage_summary",
            return_value=mock_summary,
        ):
            status = await get_user_usage_status(mock_db, user_id, SubscriptionTier.ENTERPRISE)

        assert status.is_within_limits is True
        assert status.remaining_evolution_runs is None
        assert status.remaining_cost_usd is None  # Enterprise has no cost limit


class TestCheckCanEvolve:
    """Tests for check_can_evolve."""

    @pytest.mark.asyncio
    async def test_can_evolve_within_limits(self):
        """Test evolution allowed when within limits and has payment method."""
        user_id = uuid4()
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=5)

        mock_summary = MagicMock()
        mock_summary.total_tokens = 1234
        mock_summary.total_cost_usd = Decimal("0.50")

        with patch(
            "ace_platform.core.limits.get_user_usage_summary",
            return_value=mock_summary,
        ):
            can_proceed, error = await check_can_evolve(
                mock_db, user_id, SubscriptionTier.FREE, has_payment_method=True
            )

        assert can_proceed is True
        assert error is None

    @pytest.mark.asyncio
    async def test_cannot_evolve_without_payment_method_free_tier(self):
        """Test FREE tier evolution blocked without payment method."""
        user_id = uuid4()
        mock_db = AsyncMock()

        mock_summary = MagicMock()
        mock_summary.total_tokens = 1234
        mock_summary.total_cost_usd = Decimal("0")

        with patch(
            "ace_platform.core.limits.get_user_usage_summary",
            return_value=mock_summary,
        ):
            can_proceed, error = await check_can_evolve(
                mock_db, user_id, SubscriptionTier.FREE, has_payment_method=False
            )

        assert can_proceed is False
        assert "payment method" in error.lower()
        assert "required" in error.lower()

    @pytest.mark.asyncio
    async def test_can_evolve_starter_without_payment_method(self):
        """Test STARTER tier can evolve without explicit payment method (subscription implies card)."""
        user_id = uuid4()
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=5)

        mock_summary = MagicMock()
        mock_summary.total_tokens = 1234
        mock_summary.total_cost_usd = Decimal("0.50")

        with patch(
            "ace_platform.core.limits.get_user_usage_summary",
            return_value=mock_summary,
        ):
            # Starter tier doesn't require has_payment_method check (subscription implies card)
            can_proceed, error = await check_can_evolve(
                mock_db, user_id, SubscriptionTier.STARTER, has_payment_method=False
            )

        assert can_proceed is True
        assert error is None

    @pytest.mark.asyncio
    async def test_cannot_evolve_over_limit(self):
        """Test evolution blocked when over evolution run limit."""
        user_id = uuid4()
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=15)

        mock_summary = MagicMock()
        mock_summary.total_tokens = 1234
        mock_summary.total_cost_usd = Decimal("0.50")  # Under cost limit

        with patch(
            "ace_platform.core.limits.get_user_usage_summary",
            return_value=mock_summary,
        ):
            can_proceed, error = await check_can_evolve(
                mock_db, user_id, SubscriptionTier.FREE, has_payment_method=True
            )

        assert can_proceed is False
        assert "limit reached" in error.lower()
        assert "Upgrade" in error

    @pytest.mark.asyncio
    async def test_cannot_evolve_over_spending_limit(self):
        """Test evolution blocked when over spending limit."""
        user_id = uuid4()
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=5)

        mock_summary = MagicMock()
        mock_summary.total_tokens = 1234
        mock_summary.total_cost_usd = Decimal("1.50")  # Over $1 cost limit for FREE tier

        with patch(
            "ace_platform.core.limits.get_user_usage_summary",
            return_value=mock_summary,
        ):
            can_proceed, error = await check_can_evolve(
                mock_db, user_id, SubscriptionTier.FREE, has_payment_method=True
            )

        assert can_proceed is False
        assert "spending limit" in error.lower()
        assert "Upgrade" in error

    @pytest.mark.asyncio
    async def test_payment_method_check_takes_precedence(self):
        """Test payment method check happens before usage limits check."""
        user_id = uuid4()
        mock_db = AsyncMock()

        # Even with usage under limits, no payment method should block
        mock_summary = MagicMock()
        mock_summary.total_tokens = 1234
        mock_summary.total_cost_usd = Decimal("0")

        with patch(
            "ace_platform.core.limits.get_user_usage_summary",
            return_value=mock_summary,
        ):
            can_proceed, error = await check_can_evolve(
                mock_db, user_id, SubscriptionTier.FREE, has_payment_method=False
            )

        assert can_proceed is False
        assert "payment method" in error.lower()


class TestPlaybookLimits:
    """Tests for playbook creation limits."""

    def test_can_create_playbook_within_limit(self):
        """Test can create playbook when within limit."""
        assert can_create_playbook(SubscriptionTier.STARTER, 3) is True  # 5 max
        assert can_create_playbook(SubscriptionTier.PRO, 15) is True  # 20 max
        assert can_create_playbook(SubscriptionTier.ULTRA, 50) is True  # 100 max

    def test_cannot_create_playbook_at_limit(self):
        """Test cannot create playbook when at limit."""
        assert can_create_playbook(SubscriptionTier.FREE, 1) is False  # 1 max
        assert can_create_playbook(SubscriptionTier.STARTER, 5) is False  # 5 max
        assert can_create_playbook(SubscriptionTier.PRO, 20) is False  # 20 max

    def test_enterprise_unlimited_playbooks(self):
        """Test enterprise can always create playbooks."""
        assert can_create_playbook(SubscriptionTier.ENTERPRISE, 1000) is True


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

    def test_pro_tier_can_use_premium(self):
        """Test pro tier can use premium models."""
        assert can_use_model(SubscriptionTier.PRO, "gpt-4o") is True
        assert can_use_model(SubscriptionTier.PRO, "o1") is True

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
            tier=SubscriptionTier.STARTER,
            limits=get_tier_limits(SubscriptionTier.STARTER),
            current_evolution_runs=50,
            current_total_tokens=1234,
            current_cost_usd=Decimal("4.50"),
            remaining_evolution_runs=50,
            remaining_cost_usd=Decimal("4.50"),
            is_within_limits=True,
            limit_exceeded=None,
        )
        assert status.tier == SubscriptionTier.STARTER
        assert status.is_within_limits is True
        assert status.current_evolution_runs == 50
        assert status.remaining_evolution_runs == 50
        assert status.current_cost_usd == Decimal("4.50")
        assert status.remaining_cost_usd == Decimal("4.50")


class TestSpendingCap:
    """Tests for spending cap functionality."""

    def test_tier_cost_limits(self):
        """Test each tier has correct cost limit."""
        assert get_tier_limits(SubscriptionTier.FREE).monthly_cost_limit_usd == Decimal("1.00")
        assert get_tier_limits(SubscriptionTier.STARTER).monthly_cost_limit_usd == Decimal("9.00")
        assert get_tier_limits(SubscriptionTier.PRO).monthly_cost_limit_usd == Decimal("29.00")
        assert get_tier_limits(SubscriptionTier.ULTRA).monthly_cost_limit_usd == Decimal("79.00")
        assert get_tier_limits(SubscriptionTier.ENTERPRISE).monthly_cost_limit_usd is None

    @pytest.mark.asyncio
    async def test_spending_limit_exceeded_takes_precedence(self):
        """Test spending limit takes precedence over evolution run limit."""
        user_id = uuid4()
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=5)

        mock_summary = MagicMock()
        mock_summary.total_tokens = 1234
        mock_summary.total_cost_usd = Decimal("2.00")  # Over $1 cost limit

        with patch(
            "ace_platform.core.limits.get_user_usage_summary",
            return_value=mock_summary,
        ):
            status = await get_user_usage_status(mock_db, user_id, SubscriptionTier.FREE)

        assert status.is_within_limits is False
        assert status.limit_exceeded == "monthly_cost_limit"

    @pytest.mark.asyncio
    async def test_both_limits_exceeded_returns_cost_limit(self):
        """Test cost limit message returned when both limits exceeded."""
        user_id = uuid4()
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=15)

        mock_summary = MagicMock()
        mock_summary.total_tokens = 1234
        mock_summary.total_cost_usd = Decimal("2.00")  # Over $1 cost limit

        with patch(
            "ace_platform.core.limits.get_user_usage_summary",
            return_value=mock_summary,
        ):
            status = await get_user_usage_status(mock_db, user_id, SubscriptionTier.FREE)

        # Cost limit check takes precedence
        assert status.is_within_limits is False
        assert status.limit_exceeded == "monthly_cost_limit"
