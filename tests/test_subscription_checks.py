"""Tests for subscription check dependencies and route protection."""

from unittest.mock import MagicMock

import pytest

from ace_platform.api.auth import (
    SubscriptionError,
    get_user_tier,
    require_active_subscription,
    require_capability,
    require_feature,
    require_paid_access,
    require_tier,
)
from ace_platform.config import Settings
from ace_platform.core.limits import SubscriptionTier
from ace_platform.core.rollouts import is_capability_enabled_for_user, is_plan_available_for_user
from ace_platform.db.models import SubscriptionStatus, User


def _make_user(**kwargs) -> MagicMock:
    """Create a mock User with is_admin=False by default."""
    user = MagicMock(spec=User)
    user.is_admin = kwargs.pop("is_admin", False)
    for key, value in kwargs.items():
        setattr(user, key, value)
    return user


class TestGetUserTier:
    """Tests for get_user_tier function."""

    def test_returns_free_for_none_tier(self):
        """Returns FREE tier when user has no subscription_tier."""
        user = _make_user(subscription_tier=None)

        result = get_user_tier(user)

        assert result == SubscriptionTier.FREE

    def test_returns_free_for_empty_tier(self):
        """Returns FREE tier when user has empty subscription_tier."""
        user = _make_user(subscription_tier="")

        result = get_user_tier(user)

        assert result == SubscriptionTier.FREE

    def test_returns_free_for_invalid_tier(self):
        """Returns FREE tier when user has invalid subscription_tier."""
        user = _make_user(subscription_tier="invalid_tier")

        result = get_user_tier(user)

        assert result == SubscriptionTier.FREE

    def test_returns_starter_tier(self):
        """Returns STARTER tier when user has starter subscription."""
        user = _make_user(subscription_tier="starter")

        result = get_user_tier(user)

        assert result == SubscriptionTier.STARTER

    def test_returns_professional_tier(self):
        """Returns PRO tier when user has professional subscription."""
        user = _make_user(subscription_tier="pro")

        result = get_user_tier(user)

        assert result == SubscriptionTier.PRO

    def test_returns_enterprise_tier(self):
        """Returns ENTERPRISE tier when user has enterprise subscription."""
        user = _make_user(subscription_tier="enterprise")

        result = get_user_tier(user)

        assert result == SubscriptionTier.ENTERPRISE


class TestRequireActiveSubscription:
    """Tests for require_active_subscription dependency."""

    @pytest.mark.asyncio
    async def test_allows_none_status(self):
        """Allows users with NONE subscription status (free tier)."""
        user = _make_user(subscription_status=SubscriptionStatus.NONE)

        result = await require_active_subscription(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_allows_active_status(self):
        """Allows users with ACTIVE subscription status."""
        user = _make_user(subscription_status=SubscriptionStatus.ACTIVE)

        result = await require_active_subscription(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_admin_bypasses_subscription_check(self):
        """Admin users bypass all subscription status checks."""
        user = _make_user(
            is_admin=True,
            subscription_status=SubscriptionStatus.CANCELED,
        )

        result = await require_active_subscription(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_rejects_past_due_status(self):
        """Rejects users with PAST_DUE subscription status."""
        user = _make_user(subscription_status=SubscriptionStatus.PAST_DUE)

        with pytest.raises(SubscriptionError) as exc_info:
            await require_active_subscription(user)

        assert exc_info.value.status_code == 402
        assert "past due" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_rejects_canceled_status(self):
        """Rejects users with CANCELED subscription status."""
        user = _make_user(subscription_status=SubscriptionStatus.CANCELED)

        with pytest.raises(SubscriptionError) as exc_info:
            await require_active_subscription(user)

        assert exc_info.value.status_code == 402
        assert "canceled" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_rejects_unpaid_status(self):
        """Rejects users with UNPAID subscription status."""
        user = _make_user(subscription_status=SubscriptionStatus.UNPAID)

        with pytest.raises(SubscriptionError) as exc_info:
            await require_active_subscription(user)

        assert exc_info.value.status_code == 402
        assert "unpaid" in exc_info.value.detail.lower()


class TestRequirePaidAccess:
    """Tests for require_paid_access dependency."""

    @pytest.mark.asyncio
    async def test_admin_bypasses_paid_access(self):
        """Admin users bypass all paid access checks."""
        user = _make_user(
            is_admin=True,
            subscription_status=SubscriptionStatus.NONE,
            subscription_tier=None,
        )

        result = await require_paid_access(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_allows_active_paid_tier(self):
        """Allows users with ACTIVE status and a paid tier."""
        user = _make_user(
            subscription_status=SubscriptionStatus.ACTIVE,
            subscription_tier="starter",
        )

        result = await require_paid_access(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_rejects_none_status(self):
        """Rejects users with NONE subscription status."""
        user = _make_user(
            subscription_status=SubscriptionStatus.NONE,
            subscription_tier=None,
        )

        with pytest.raises(SubscriptionError) as exc_info:
            await require_paid_access(user)

        assert exc_info.value.status_code == 402
        assert "subscribe" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_rejects_active_without_paid_tier(self):
        """Rejects users with ACTIVE status but missing/invalid tier."""
        user = _make_user(
            subscription_status=SubscriptionStatus.ACTIVE,
            subscription_tier=None,
        )

        with pytest.raises(SubscriptionError) as exc_info:
            await require_paid_access(user)

        assert exc_info.value.status_code == 402
        assert "subscribe" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_rejects_past_due_status(self):
        """Rejects users with PAST_DUE subscription status."""
        user = _make_user(
            subscription_status=SubscriptionStatus.PAST_DUE,
            subscription_tier="starter",
        )

        with pytest.raises(SubscriptionError) as exc_info:
            await require_paid_access(user)

        assert exc_info.value.status_code == 402
        assert "past due" in exc_info.value.detail.lower()


class TestRequireTier:
    """Tests for require_tier dependency factory."""

    @pytest.mark.asyncio
    async def test_allows_matching_tier(self):
        """Allows access when user has matching tier."""
        user = _make_user(
            subscription_status=SubscriptionStatus.ACTIVE,
            subscription_tier="starter",
        )

        checker = require_tier(SubscriptionTier.STARTER)
        result = await checker(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_allows_higher_tier(self):
        """Allows access when user has higher tier than required."""
        user = _make_user(
            subscription_status=SubscriptionStatus.ACTIVE,
            subscription_tier="pro",
        )

        checker = require_tier(SubscriptionTier.STARTER)
        result = await checker(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_rejects_lower_tier(self):
        """Rejects access when user has lower tier than required."""
        user = _make_user(
            subscription_status=SubscriptionStatus.ACTIVE,
            subscription_tier="free",
        )

        checker = require_tier(SubscriptionTier.STARTER)

        with pytest.raises(SubscriptionError) as exc_info:
            await checker(user)

        assert exc_info.value.status_code == 402
        assert "starter" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_free_user_for_free_tier(self):
        """Allows free user for routes requiring FREE tier."""
        user = _make_user(
            subscription_status=SubscriptionStatus.NONE,
            subscription_tier=None,
        )

        checker = require_tier(SubscriptionTier.FREE)
        result = await checker(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_enterprise_required(self):
        """Rejects professional user for enterprise-only features."""
        user = _make_user(
            subscription_status=SubscriptionStatus.ACTIVE,
            subscription_tier="pro",
        )

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
        user = _make_user(
            subscription_status=SubscriptionStatus.ACTIVE,
            subscription_tier="starter",
        )

        checker = require_feature("can_export_data")
        result = await checker(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_rejects_feature_unavailable(self):
        """Rejects access when tier lacks the required feature."""
        user = _make_user(
            subscription_status=SubscriptionStatus.NONE,
            subscription_tier=None,
        )

        checker = require_feature("can_export_data")

        with pytest.raises(SubscriptionError) as exc_info:
            await checker(user)

        assert exc_info.value.status_code == 402
        assert "can export data" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_premium_models_on_starter(self):
        """Allows premium models for starter tier."""
        user = _make_user(
            subscription_status=SubscriptionStatus.ACTIVE,
            subscription_tier="starter",
        )

        checker = require_feature("can_use_premium_models")
        result = await checker(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_premium_models_on_free(self):
        """Rejects premium models for free tier."""
        user = _make_user(
            subscription_status=SubscriptionStatus.NONE,
            subscription_tier=None,
        )

        checker = require_feature("can_use_premium_models")

        with pytest.raises(SubscriptionError) as exc_info:
            await checker(user)

        assert exc_info.value.status_code == 402

    @pytest.mark.asyncio
    async def test_priority_support_on_professional(self):
        """Allows priority support for professional tier."""
        user = _make_user(
            subscription_status=SubscriptionStatus.ACTIVE,
            subscription_tier="pro",
        )

        checker = require_feature("priority_support")
        result = await checker(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_priority_support_on_starter(self):
        """Rejects priority support for starter tier."""
        user = _make_user(
            subscription_status=SubscriptionStatus.ACTIVE,
            subscription_tier="starter",
        )

        checker = require_feature("priority_support")

        with pytest.raises(SubscriptionError) as exc_info:
            await checker(user)

        assert exc_info.value.status_code == 402


class TestRequireCapability:
    """Tests for rollout-aware capability checks."""

    @pytest.mark.asyncio
    async def test_allows_enabled_capability(self, monkeypatch):
        """Allows access when rollout evaluation enables the capability."""
        import ace_platform.api.auth as auth_module

        user = _make_user(
            subscription_status=SubscriptionStatus.ACTIVE,
            subscription_tier="starter",
        )

        monkeypatch.setattr(
            auth_module,
            "is_capability_enabled_for_user",
            lambda current_user, feature: current_user is user and feature == "shared_workspace",
        )

        checker = require_capability("shared_workspace")
        result = await checker(user)

        assert result == user

    @pytest.mark.asyncio
    async def test_rejects_disabled_capability(self, monkeypatch):
        """Rejects access when rollout evaluation disables the capability."""
        import ace_platform.api.auth as auth_module

        user = _make_user(
            subscription_status=SubscriptionStatus.ACTIVE,
            subscription_tier="starter",
        )

        monkeypatch.setattr(
            auth_module,
            "is_capability_enabled_for_user",
            lambda _current_user, _feature: False,
        )

        checker = require_capability("shared_workspace")

        with pytest.raises(SubscriptionError) as exc_info:
            await checker(user)

        assert exc_info.value.status_code == 403
        assert "shared workspace" in exc_info.value.detail.lower()


class TestRolloutControls:
    """Tests for environment-aware plan and capability rollout evaluation."""

    def test_plan_rollout_respects_environment(self):
        """Plans can be opened in a specific environment before GA."""
        settings = Settings(
            environment="staging",
            jwt_secret_key="staging-secret",
            session_secret_key="staging-session-secret",
            session_cookie_secure=True,
            pre_ga_rollouts={
                "plan:enterprise": {
                    "environments": ["staging"],
                }
            },
        )

        assert (
            is_plan_available_for_user(None, SubscriptionTier.ENTERPRISE, settings=settings) is True
        )

        prod_settings = Settings(
            environment="production",
            jwt_secret_key="prod-secret",
            session_secret_key="prod-session-secret",
            session_cookie_secure=True,
            pre_ga_rollouts={
                "plan:enterprise": {
                    "environments": ["staging"],
                }
            },
        )

        assert (
            is_plan_available_for_user(None, SubscriptionTier.ENTERPRISE, settings=prod_settings)
            is False
        )

    def test_capability_rollout_targets_selected_users(self):
        """Capabilities can be allowlisted for selected users before GA."""
        settings = Settings(
            environment="production",
            jwt_secret_key="prod-secret",
            session_secret_key="prod-session-secret",
            session_cookie_secure=True,
            pre_ga_rollouts={
                "capability:managed_inference": {
                    "emails": ["beta@example.com"],
                }
            },
        )

        allowlisted_user = _make_user(
            email="beta@example.com",
            subscription_status=SubscriptionStatus.ACTIVE,
            subscription_tier="starter",
        )
        other_user = _make_user(
            email="other@example.com",
            subscription_status=SubscriptionStatus.ACTIVE,
            subscription_tier="starter",
        )

        assert (
            is_capability_enabled_for_user(
                allowlisted_user,
                "managed_inference",
                settings=settings,
            )
            is True
        )
        assert (
            is_capability_enabled_for_user(
                other_user,
                "managed_inference",
                settings=settings,
            )
            is False
        )


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
