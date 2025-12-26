"""Tests for subscription check dependencies and route protection."""

from unittest.mock import MagicMock

import pytest

from ace_platform.api.auth import (
    SubscriptionError,
    get_user_tier,
    require_active_subscription,
    require_feature,
    require_tier,
)
from ace_platform.core.limits import SubscriptionTier
from ace_platform.db.models import SubscriptionStatus, User


class TestGetUserTier:
    """Tests for get_user_tier function."""

    def test_returns_free_for_none_tier(self):
        """Returns FREE tier when user has no subscription_tier."""
        user = MagicMock(spec=User)
        user.subscription_tier = None

        result = get_user_tier(user)

        assert result == SubscriptionTier.FREE

    def test_returns_free_for_empty_tier(self):
        """Returns FREE tier when user has empty subscription_tier."""
        user = MagicMock(spec=User)
        user.subscription_tier = ""

        result = get_user_tier(user)

        assert result == SubscriptionTier.FREE

    def test_returns_free_for_invalid_tier(self):
        """Returns FREE tier when user has invalid subscription_tier."""
        user = MagicMock(spec=User)
        user.subscription_tier = "invalid_tier"

        result = get_user_tier(user)

        assert result == SubscriptionTier.FREE

    def test_returns_starter_tier(self):
        """Returns STARTER tier when user has starter subscription."""
        user = MagicMock(spec=User)
        user.subscription_tier = "starter"

        result = get_user_tier(user)

        assert result == SubscriptionTier.STARTER

    def test_returns_professional_tier(self):
        """Returns PROFESSIONAL tier when user has professional subscription."""
        user = MagicMock(spec=User)
        user.subscription_tier = "professional"

        result = get_user_tier(user)

        assert result == SubscriptionTier.PROFESSIONAL

    def test_returns_enterprise_tier(self):
        """Returns ENTERPRISE tier when user has enterprise subscription."""
        user = MagicMock(spec=User)
        user.subscription_tier = "enterprise"

        result = get_user_tier(user)

        assert result == SubscriptionTier.ENTERPRISE


class TestRequireActiveSubscription:
    """Tests for require_active_subscription dependency."""

    @pytest.mark.asyncio
    async def test_allows_none_status(self):
        """Allows users with NONE subscription status (free tier)."""
        user = MagicMock(spec=User)
        user.subscription_status = SubscriptionStatus.NONE

        result = await require_active_subscription(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_allows_active_status(self):
        """Allows users with ACTIVE subscription status."""
        user = MagicMock(spec=User)
        user.subscription_status = SubscriptionStatus.ACTIVE

        result = await require_active_subscription(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_rejects_past_due_status(self):
        """Rejects users with PAST_DUE subscription status."""
        user = MagicMock(spec=User)
        user.subscription_status = SubscriptionStatus.PAST_DUE

        with pytest.raises(SubscriptionError) as exc_info:
            await require_active_subscription(user)

        assert exc_info.value.status_code == 402
        assert "past due" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_rejects_canceled_status(self):
        """Rejects users with CANCELED subscription status."""
        user = MagicMock(spec=User)
        user.subscription_status = SubscriptionStatus.CANCELED

        with pytest.raises(SubscriptionError) as exc_info:
            await require_active_subscription(user)

        assert exc_info.value.status_code == 402
        assert "canceled" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_rejects_unpaid_status(self):
        """Rejects users with UNPAID subscription status."""
        user = MagicMock(spec=User)
        user.subscription_status = SubscriptionStatus.UNPAID

        with pytest.raises(SubscriptionError) as exc_info:
            await require_active_subscription(user)

        assert exc_info.value.status_code == 402
        assert "unpaid" in exc_info.value.detail.lower()


class TestRequireTier:
    """Tests for require_tier dependency factory."""

    @pytest.mark.asyncio
    async def test_allows_matching_tier(self):
        """Allows access when user has matching tier."""
        user = MagicMock(spec=User)
        user.subscription_status = SubscriptionStatus.ACTIVE
        user.subscription_tier = "starter"

        checker = require_tier(SubscriptionTier.STARTER)
        result = await checker(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_allows_higher_tier(self):
        """Allows access when user has higher tier than required."""
        user = MagicMock(spec=User)
        user.subscription_status = SubscriptionStatus.ACTIVE
        user.subscription_tier = "professional"

        checker = require_tier(SubscriptionTier.STARTER)
        result = await checker(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_rejects_lower_tier(self):
        """Rejects access when user has lower tier than required."""
        user = MagicMock(spec=User)
        user.subscription_status = SubscriptionStatus.ACTIVE
        user.subscription_tier = "free"

        checker = require_tier(SubscriptionTier.STARTER)

        with pytest.raises(SubscriptionError) as exc_info:
            await checker(user)

        assert exc_info.value.status_code == 402
        assert "starter" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_free_user_for_free_tier(self):
        """Allows free user for routes requiring FREE tier."""
        user = MagicMock(spec=User)
        user.subscription_status = SubscriptionStatus.NONE
        user.subscription_tier = None

        checker = require_tier(SubscriptionTier.FREE)
        result = await checker(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_enterprise_required(self):
        """Rejects professional user for enterprise-only features."""
        user = MagicMock(spec=User)
        user.subscription_status = SubscriptionStatus.ACTIVE
        user.subscription_tier = "professional"

        checker = require_tier(SubscriptionTier.ENTERPRISE)

        with pytest.raises(SubscriptionError) as exc_info:
            await checker(user)

        assert exc_info.value.status_code == 402
        assert "enterprise" in exc_info.value.detail.lower()


class TestRequireFeature:
    """Tests for require_feature dependency factory."""

    @pytest.mark.asyncio
    async def test_allows_feature_available(self):
        """Allows access when tier has the required feature."""
        user = MagicMock(spec=User)
        user.subscription_status = SubscriptionStatus.ACTIVE
        user.subscription_tier = "starter"  # Starter has can_export_data

        checker = require_feature("can_export_data")
        result = await checker(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_rejects_feature_unavailable(self):
        """Rejects access when tier lacks the required feature."""
        user = MagicMock(spec=User)
        user.subscription_status = SubscriptionStatus.NONE
        user.subscription_tier = None  # Free tier lacks can_export_data

        checker = require_feature("can_export_data")

        with pytest.raises(SubscriptionError) as exc_info:
            await checker(user)

        assert exc_info.value.status_code == 402
        assert "can export data" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_premium_models_on_starter(self):
        """Allows premium models for starter tier."""
        user = MagicMock(spec=User)
        user.subscription_status = SubscriptionStatus.ACTIVE
        user.subscription_tier = "starter"

        checker = require_feature("can_use_premium_models")
        result = await checker(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_premium_models_on_free(self):
        """Rejects premium models for free tier."""
        user = MagicMock(spec=User)
        user.subscription_status = SubscriptionStatus.NONE
        user.subscription_tier = None

        checker = require_feature("can_use_premium_models")

        with pytest.raises(SubscriptionError) as exc_info:
            await checker(user)

        assert exc_info.value.status_code == 402

    @pytest.mark.asyncio
    async def test_priority_support_on_professional(self):
        """Allows priority support for professional tier."""
        user = MagicMock(spec=User)
        user.subscription_status = SubscriptionStatus.ACTIVE
        user.subscription_tier = "professional"

        checker = require_feature("priority_support")
        result = await checker(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_priority_support_on_starter(self):
        """Rejects priority support for starter tier."""
        user = MagicMock(spec=User)
        user.subscription_status = SubscriptionStatus.ACTIVE
        user.subscription_tier = "starter"  # Starter lacks priority_support

        checker = require_feature("priority_support")

        with pytest.raises(SubscriptionError) as exc_info:
            await checker(user)

        assert exc_info.value.status_code == 402


class TestSubscriptionError:
    """Tests for SubscriptionError exception."""

    def test_default_status_code(self):
        """Uses 403 as default status code."""
        error = SubscriptionError("Test error")

        assert error.status_code == 403
        assert error.detail == "Test error"

    def test_custom_status_code(self):
        """Allows custom status code."""
        error = SubscriptionError("Payment required", status_code=402)

        assert error.status_code == 402
        assert error.detail == "Payment required"
