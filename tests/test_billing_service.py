"""Tests for billing service.

These tests verify:
1. Stripe customer creation
2. Checkout session creation
3. Billing portal session creation
4. Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from ace_platform.core.billing import (
    CheckoutSessionResult,
    PortalSessionResult,
    create_billing_portal_session,
    create_checkout_session,
    get_or_create_stripe_customer,
    get_subscription_tier_features,
)
from ace_platform.core.limits import SubscriptionTier


class TestCheckoutSessionResult:
    """Tests for CheckoutSessionResult dataclass."""

    def test_success_result(self):
        """Test successful checkout session result."""
        result = CheckoutSessionResult(
            success=True,
            checkout_url="https://checkout.stripe.com/session123",
            session_id="cs_test_123",
        )
        assert result.success is True
        assert result.checkout_url is not None
        assert result.error is None

    def test_error_result(self):
        """Test error checkout session result."""
        result = CheckoutSessionResult(
            success=False,
            error="Stripe not configured",
        )
        assert result.success is False
        assert result.checkout_url is None
        assert result.error == "Stripe not configured"


class TestPortalSessionResult:
    """Tests for PortalSessionResult dataclass."""

    def test_success_result(self):
        """Test successful portal session result."""
        result = PortalSessionResult(
            success=True,
            portal_url="https://billing.stripe.com/session123",
        )
        assert result.success is True
        assert result.portal_url is not None

    def test_error_result(self):
        """Test error portal session result."""
        result = PortalSessionResult(
            success=False,
            error="No customer found",
        )
        assert result.success is False
        assert result.portal_url is None


class TestGetOrCreateStripeCustomer:
    """Tests for get_or_create_stripe_customer function."""

    @pytest.mark.asyncio
    async def test_returns_existing_customer_id(self):
        """Test returns existing customer ID without creating new one."""
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.stripe_customer_id = "cus_existing123"

        result = await get_or_create_stripe_customer(mock_db, mock_user)

        assert result == "cus_existing123"
        # Should not have called execute (no DB update)
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    @patch("ace_platform.core.billing._get_stripe_client")
    async def test_creates_new_customer(self, mock_get_client):
        """Test creates new Stripe customer when none exists."""
        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = uuid4()
        mock_user.email = "test@example.com"
        mock_user.stripe_customer_id = None

        # Mock Stripe client
        mock_client = MagicMock()
        mock_customer = MagicMock()
        mock_customer.id = "cus_new123"
        mock_client.customers.create.return_value = mock_customer
        mock_get_client.return_value = mock_client

        result = await get_or_create_stripe_customer(mock_db, mock_user)

        assert result == "cus_new123"
        mock_client.customers.create.assert_called_once()
        mock_db.execute.assert_called_once()
        mock_db.commit.assert_called_once()


class TestCreateCheckoutSession:
    """Tests for create_checkout_session function."""

    @pytest.mark.asyncio
    async def test_free_tier_returns_error(self):
        """Test free tier doesn't create checkout session."""
        mock_db = AsyncMock()
        mock_user = MagicMock()

        result = await create_checkout_session(
            db=mock_db,
            user=mock_user,
            tier=SubscriptionTier.FREE,
        )

        assert result.success is False
        assert "Free tier" in result.error

    @pytest.mark.asyncio
    async def test_enterprise_tier_returns_error(self):
        """Test enterprise tier requires custom pricing."""
        mock_db = AsyncMock()
        mock_user = MagicMock()

        result = await create_checkout_session(
            db=mock_db,
            user=mock_user,
            tier=SubscriptionTier.ENTERPRISE,
        )

        assert result.success is False
        assert "custom pricing" in result.error.lower()

    @pytest.mark.asyncio
    @patch("ace_platform.core.billing.is_stripe_configured")
    async def test_stripe_not_configured(self, mock_configured):
        """Test returns error when Stripe not configured."""
        mock_configured.return_value = False
        mock_db = AsyncMock()
        mock_user = MagicMock()

        result = await create_checkout_session(
            db=mock_db,
            user=mock_user,
            tier=SubscriptionTier.STARTER,
        )

        assert result.success is False
        assert "not configured" in result.error.lower()

    @pytest.mark.asyncio
    @patch("ace_platform.core.billing.get_price_id_for_tier")
    @patch("ace_platform.core.billing.is_stripe_configured")
    async def test_no_price_configured(self, mock_configured, mock_get_price):
        """Test returns error when no price ID configured."""
        mock_configured.return_value = True
        mock_get_price.return_value = None
        mock_db = AsyncMock()
        mock_user = MagicMock()

        result = await create_checkout_session(
            db=mock_db,
            user=mock_user,
            tier=SubscriptionTier.STARTER,
        )

        assert result.success is False
        assert "No price configured" in result.error

    @pytest.mark.asyncio
    @patch("ace_platform.core.billing._get_stripe_client")
    @patch("ace_platform.core.billing.get_or_create_stripe_customer")
    @patch("ace_platform.core.billing.get_price_id_for_tier")
    @patch("ace_platform.core.billing.is_stripe_configured")
    async def test_successful_checkout_session(
        self, mock_configured, mock_get_price, mock_get_customer, mock_get_client
    ):
        """Test successful checkout session creation."""
        mock_configured.return_value = True
        mock_get_price.return_value = "price_starter123"
        mock_get_customer.return_value = "cus_test123"

        # Mock Stripe client
        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/test"
        mock_session.id = "cs_test123"
        mock_client.checkout.sessions.create.return_value = mock_session
        mock_get_client.return_value = mock_client

        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await create_checkout_session(
            db=mock_db,
            user=mock_user,
            tier=SubscriptionTier.STARTER,
        )

        assert result.success is True
        assert result.checkout_url == "https://checkout.stripe.com/test"
        assert result.session_id == "cs_test123"

    @pytest.mark.asyncio
    @patch("ace_platform.core.billing._get_stripe_client")
    @patch("ace_platform.core.billing.get_or_create_stripe_customer")
    @patch("ace_platform.core.billing.get_price_id_for_tier")
    @patch("ace_platform.core.billing.is_stripe_configured")
    async def test_stripe_error_handling(
        self, mock_configured, mock_get_price, mock_get_customer, mock_get_client
    ):
        """Test Stripe error handling."""
        import stripe

        mock_configured.return_value = True
        mock_get_price.return_value = "price_starter123"
        mock_get_customer.return_value = "cus_test123"

        # Mock Stripe client to raise error
        mock_client = MagicMock()
        mock_client.checkout.sessions.create.side_effect = stripe.StripeError("API error")
        mock_get_client.return_value = mock_client

        mock_db = AsyncMock()
        mock_user = MagicMock()
        mock_user.id = uuid4()

        result = await create_checkout_session(
            db=mock_db,
            user=mock_user,
            tier=SubscriptionTier.STARTER,
        )

        assert result.success is False
        assert "Stripe error" in result.error


class TestCreateBillingPortalSession:
    """Tests for create_billing_portal_session function."""

    @pytest.mark.asyncio
    async def test_no_customer_id(self):
        """Test returns error when user has no Stripe customer ID."""
        mock_user = MagicMock()
        mock_user.stripe_customer_id = None

        result = await create_billing_portal_session(user=mock_user)

        assert result.success is False
        assert "No billing account" in result.error

    @pytest.mark.asyncio
    @patch("ace_platform.core.billing._get_stripe_client")
    async def test_successful_portal_session(self, mock_get_client):
        """Test successful portal session creation."""
        mock_user = MagicMock()
        mock_user.stripe_customer_id = "cus_test123"

        # Mock Stripe client
        mock_client = MagicMock()
        mock_session = MagicMock()
        mock_session.url = "https://billing.stripe.com/portal"
        mock_client.billing_portal.sessions.create.return_value = mock_session
        mock_get_client.return_value = mock_client

        result = await create_billing_portal_session(user=mock_user)

        assert result.success is True
        assert result.portal_url == "https://billing.stripe.com/portal"

    @pytest.mark.asyncio
    @patch("ace_platform.core.billing._get_stripe_client")
    async def test_stripe_error_handling(self, mock_get_client):
        """Test Stripe error handling in portal session."""
        import stripe

        mock_user = MagicMock()
        mock_user.stripe_customer_id = "cus_test123"

        # Mock Stripe client to raise error
        mock_client = MagicMock()
        mock_client.billing_portal.sessions.create.side_effect = stripe.StripeError("Portal error")
        mock_get_client.return_value = mock_client

        result = await create_billing_portal_session(user=mock_user)

        assert result.success is False
        assert "Stripe error" in result.error


class TestGetSubscriptionTierFeatures:
    """Tests for get_subscription_tier_features function."""

    def test_free_tier_features(self):
        """Test free tier has default features."""
        features = get_subscription_tier_features(SubscriptionTier.FREE)

        assert len(features) > 0
        assert any("100 requests" in f for f in features)

    @patch("ace_platform.core.billing.get_product_config")
    def test_paid_tier_features(self, mock_get_config):
        """Test paid tier returns product features."""
        mock_config = MagicMock()
        mock_config.features = ("Feature 1", "Feature 2", "Feature 3")
        mock_get_config.return_value = mock_config

        features = get_subscription_tier_features(SubscriptionTier.STARTER)

        assert len(features) == 3
        assert "Feature 1" in features

    @patch("ace_platform.core.billing.get_product_config")
    def test_no_config_returns_empty(self, mock_get_config):
        """Test returns empty list when no config found."""
        mock_get_config.return_value = None

        # For a tier that's not FREE and has no config
        features = get_subscription_tier_features(SubscriptionTier.STARTER)

        assert features == []
