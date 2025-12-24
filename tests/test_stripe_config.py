"""Tests for Stripe products and prices configuration.

These tests verify:
1. Price configuration dataclass
2. Product configuration dataclass
3. Tier lookup functions
4. Settings loading
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from ace_platform.core.limits import SubscriptionTier
from ace_platform.core.stripe_config import (
    PROFESSIONAL_MONTHLY_PRICE_CENTS,
    PROFESSIONAL_YEARLY_PRICE_CENTS,
    STARTER_MONTHLY_PRICE_CENTS,
    STARTER_YEARLY_PRICE_CENTS,
    BillingInterval,
    PriceConfig,
    ProductConfig,
    StripeProductSettings,
    get_all_products,
    get_price_id_for_tier,
    get_product_config,
    get_tier_from_price_id,
    get_tier_from_product_id,
    is_stripe_configured,
)


class TestPriceConfig:
    """Tests for PriceConfig dataclass."""

    def test_price_config_defaults(self):
        """Test PriceConfig with default values."""
        price = PriceConfig(
            price_id="price_test123",
            unit_amount=1000,
        )
        assert price.price_id == "price_test123"
        assert price.unit_amount == 1000
        assert price.currency == "usd"
        assert price.interval == BillingInterval.MONTHLY
        assert price.product_id is None

    def test_price_config_custom_values(self):
        """Test PriceConfig with custom values."""
        price = PriceConfig(
            price_id="price_yearly",
            unit_amount=10000,
            currency="eur",
            interval=BillingInterval.YEARLY,
            product_id="prod_test",
        )
        assert price.currency == "eur"
        assert price.interval == BillingInterval.YEARLY
        assert price.product_id == "prod_test"

    def test_amount_decimal(self):
        """Test amount_decimal property conversion."""
        price = PriceConfig(price_id="price_test", unit_amount=1000)
        assert price.amount_decimal == Decimal("10.00")

        price_fractional = PriceConfig(price_id="price_test", unit_amount=999)
        assert price_fractional.amount_decimal == Decimal("9.99")

    def test_price_config_immutable(self):
        """Test that PriceConfig is immutable (frozen)."""
        price = PriceConfig(price_id="price_test", unit_amount=1000)
        with pytest.raises(AttributeError):
            price.unit_amount = 2000


class TestProductConfig:
    """Tests for ProductConfig dataclass."""

    def test_product_config_minimal(self):
        """Test ProductConfig with minimal required values."""
        product = ProductConfig(
            product_id="prod_test",
            name="Test Product",
            description="A test product",
            tier=SubscriptionTier.STARTER,
            monthly_price=PriceConfig(price_id="price_monthly", unit_amount=1000),
        )
        assert product.product_id == "prod_test"
        assert product.name == "Test Product"
        assert product.tier == SubscriptionTier.STARTER
        assert product.yearly_price is None
        assert product.features == ()

    def test_product_config_full(self):
        """Test ProductConfig with all values."""
        product = ProductConfig(
            product_id="prod_full",
            name="Full Product",
            description="A fully configured product",
            tier=SubscriptionTier.PROFESSIONAL,
            monthly_price=PriceConfig(price_id="price_monthly", unit_amount=10000),
            yearly_price=PriceConfig(
                price_id="price_yearly",
                unit_amount=100000,
                interval=BillingInterval.YEARLY,
            ),
            features=("Feature 1", "Feature 2", "Feature 3"),
        )
        assert product.yearly_price is not None
        assert len(product.features) == 3

    def test_product_config_immutable(self):
        """Test that ProductConfig is immutable (frozen)."""
        product = ProductConfig(
            product_id="prod_test",
            name="Test",
            description="Test",
            tier=SubscriptionTier.STARTER,
            monthly_price=PriceConfig(price_id="price_test", unit_amount=1000),
        )
        with pytest.raises(AttributeError):
            product.name = "New Name"


class TestBillingInterval:
    """Tests for BillingInterval enum."""

    def test_billing_interval_values(self):
        """Test BillingInterval enum values."""
        assert BillingInterval.MONTHLY.value == "month"
        assert BillingInterval.YEARLY.value == "year"

    def test_billing_interval_is_string(self):
        """Test BillingInterval is a string enum."""
        assert isinstance(BillingInterval.MONTHLY, str)
        assert BillingInterval.MONTHLY == "month"


class TestPricingConstants:
    """Tests for pricing constants."""

    def test_starter_pricing(self):
        """Test Starter tier pricing constants."""
        assert STARTER_MONTHLY_PRICE_CENTS == 1000  # $10/month
        assert STARTER_YEARLY_PRICE_CENTS == 10000  # $100/year

    def test_professional_pricing(self):
        """Test Professional tier pricing constants."""
        assert PROFESSIONAL_MONTHLY_PRICE_CENTS == 10000  # $100/month
        assert PROFESSIONAL_YEARLY_PRICE_CENTS == 100000  # $1000/year

    def test_yearly_discount(self):
        """Test that yearly pricing includes a discount."""
        # Yearly should be equivalent to 10 months (2 months free)
        starter_yearly_equivalent = STARTER_MONTHLY_PRICE_CENTS * 12
        assert STARTER_YEARLY_PRICE_CENTS < starter_yearly_equivalent

        professional_yearly_equivalent = PROFESSIONAL_MONTHLY_PRICE_CENTS * 12
        assert PROFESSIONAL_YEARLY_PRICE_CENTS < professional_yearly_equivalent


class TestGetProductConfig:
    """Tests for get_product_config function."""

    def test_free_tier_returns_none(self):
        """Test FREE tier has no Stripe product."""
        config = get_product_config(SubscriptionTier.FREE)
        assert config is None

    @patch("ace_platform.core.stripe_config.get_stripe_product_settings")
    def test_starter_tier_config(self, mock_settings):
        """Test STARTER tier returns correct config."""
        mock_settings.return_value = StripeProductSettings(
            stripe_starter_product_id="prod_starter",
            stripe_starter_monthly_price_id="price_starter_monthly",
            stripe_starter_yearly_price_id="price_starter_yearly",
        )

        config = get_product_config(SubscriptionTier.STARTER)

        assert config is not None
        assert config.product_id == "prod_starter"
        assert config.name == "ACE Starter"
        assert config.tier == SubscriptionTier.STARTER
        assert config.monthly_price.price_id == "price_starter_monthly"
        assert config.monthly_price.unit_amount == STARTER_MONTHLY_PRICE_CENTS
        assert config.yearly_price is not None
        assert config.yearly_price.price_id == "price_starter_yearly"

    @patch("ace_platform.core.stripe_config.get_stripe_product_settings")
    def test_professional_tier_config(self, mock_settings):
        """Test PROFESSIONAL tier returns correct config."""
        mock_settings.return_value = StripeProductSettings(
            stripe_professional_product_id="prod_pro",
            stripe_professional_monthly_price_id="price_pro_monthly",
        )

        config = get_product_config(SubscriptionTier.PROFESSIONAL)

        assert config is not None
        assert config.product_id == "prod_pro"
        assert config.name == "ACE Professional"
        assert config.tier == SubscriptionTier.PROFESSIONAL
        assert config.monthly_price.unit_amount == PROFESSIONAL_MONTHLY_PRICE_CENTS
        assert "Priority support" in config.features

    @patch("ace_platform.core.stripe_config.get_stripe_product_settings")
    def test_enterprise_tier_config(self, mock_settings):
        """Test ENTERPRISE tier returns config with custom pricing."""
        mock_settings.return_value = StripeProductSettings(
            stripe_enterprise_product_id="prod_enterprise",
        )

        config = get_product_config(SubscriptionTier.ENTERPRISE)

        assert config is not None
        assert config.product_id == "prod_enterprise"
        assert config.name == "ACE Enterprise"
        assert config.tier == SubscriptionTier.ENTERPRISE
        # Enterprise has custom pricing (empty price_id)
        assert config.monthly_price.price_id == ""
        assert "Unlimited requests" in config.features


class TestGetPriceIdForTier:
    """Tests for get_price_id_for_tier function."""

    def test_free_tier_returns_none(self):
        """Test FREE tier has no price ID."""
        price_id = get_price_id_for_tier(SubscriptionTier.FREE)
        assert price_id is None

    @patch("ace_platform.core.stripe_config.get_stripe_product_settings")
    def test_starter_monthly_price(self, mock_settings):
        """Test getting Starter monthly price ID."""
        mock_settings.return_value = StripeProductSettings(
            stripe_starter_product_id="prod_starter",
            stripe_starter_monthly_price_id="price_starter_monthly",
        )

        price_id = get_price_id_for_tier(SubscriptionTier.STARTER, BillingInterval.MONTHLY)
        assert price_id == "price_starter_monthly"

    @patch("ace_platform.core.stripe_config.get_stripe_product_settings")
    def test_starter_yearly_price(self, mock_settings):
        """Test getting Starter yearly price ID."""
        mock_settings.return_value = StripeProductSettings(
            stripe_starter_product_id="prod_starter",
            stripe_starter_monthly_price_id="price_starter_monthly",
            stripe_starter_yearly_price_id="price_starter_yearly",
        )

        price_id = get_price_id_for_tier(SubscriptionTier.STARTER, BillingInterval.YEARLY)
        assert price_id == "price_starter_yearly"

    @patch("ace_platform.core.stripe_config.get_stripe_product_settings")
    def test_yearly_fallback_to_monthly(self, mock_settings):
        """Test yearly falls back to monthly if yearly not configured."""
        mock_settings.return_value = StripeProductSettings(
            stripe_starter_product_id="prod_starter",
            stripe_starter_monthly_price_id="price_starter_monthly",
            stripe_starter_yearly_price_id="",  # No yearly price
        )

        price_id = get_price_id_for_tier(SubscriptionTier.STARTER, BillingInterval.YEARLY)
        # Falls back to monthly when yearly is not configured
        assert price_id == "price_starter_monthly"


class TestTierLookup:
    """Tests for tier lookup functions."""

    @patch("ace_platform.core.stripe_config.get_stripe_product_settings")
    def test_get_tier_from_price_id_monthly(self, mock_settings):
        """Test looking up tier from monthly price ID."""
        mock_settings.return_value = StripeProductSettings(
            stripe_starter_product_id="prod_starter",
            stripe_starter_monthly_price_id="price_starter_monthly",
            stripe_professional_product_id="prod_pro",
            stripe_professional_monthly_price_id="price_pro_monthly",
        )

        tier = get_tier_from_price_id("price_starter_monthly")
        assert tier == SubscriptionTier.STARTER

        tier = get_tier_from_price_id("price_pro_monthly")
        assert tier == SubscriptionTier.PROFESSIONAL

    @patch("ace_platform.core.stripe_config.get_stripe_product_settings")
    def test_get_tier_from_price_id_yearly(self, mock_settings):
        """Test looking up tier from yearly price ID."""
        mock_settings.return_value = StripeProductSettings(
            stripe_starter_product_id="prod_starter",
            stripe_starter_monthly_price_id="price_starter_monthly",
            stripe_starter_yearly_price_id="price_starter_yearly",
        )

        tier = get_tier_from_price_id("price_starter_yearly")
        assert tier == SubscriptionTier.STARTER

    @patch("ace_platform.core.stripe_config.get_stripe_product_settings")
    def test_get_tier_from_price_id_unknown(self, mock_settings):
        """Test looking up unknown price ID returns None."""
        mock_settings.return_value = StripeProductSettings()

        tier = get_tier_from_price_id("price_unknown")
        assert tier is None

    @patch("ace_platform.core.stripe_config.get_stripe_product_settings")
    def test_get_tier_from_product_id(self, mock_settings):
        """Test looking up tier from product ID."""
        mock_settings.return_value = StripeProductSettings(
            stripe_starter_product_id="prod_starter",
            stripe_starter_monthly_price_id="price_starter",
            stripe_professional_product_id="prod_pro",
            stripe_professional_monthly_price_id="price_pro",
        )

        tier = get_tier_from_product_id("prod_starter")
        assert tier == SubscriptionTier.STARTER

        tier = get_tier_from_product_id("prod_pro")
        assert tier == SubscriptionTier.PROFESSIONAL

    @patch("ace_platform.core.stripe_config.get_stripe_product_settings")
    def test_get_tier_from_product_id_unknown(self, mock_settings):
        """Test looking up unknown product ID returns None."""
        mock_settings.return_value = StripeProductSettings()

        tier = get_tier_from_product_id("prod_unknown")
        assert tier is None


class TestIsStripeConfigured:
    """Tests for is_stripe_configured function."""

    @patch("ace_platform.core.stripe_config.get_stripe_product_settings")
    def test_not_configured_when_empty(self, mock_settings):
        """Test returns False when no IDs configured."""
        mock_settings.return_value = StripeProductSettings()

        assert is_stripe_configured() is False

    @patch("ace_platform.core.stripe_config.get_stripe_product_settings")
    def test_not_configured_partial(self, mock_settings):
        """Test returns False when only partially configured."""
        mock_settings.return_value = StripeProductSettings(
            stripe_starter_product_id="prod_starter",
            # Missing price ID
        )

        assert is_stripe_configured() is False

    @patch("ace_platform.core.stripe_config.get_stripe_product_settings")
    def test_configured_when_starter_complete(self, mock_settings):
        """Test returns True when Starter tier is fully configured."""
        mock_settings.return_value = StripeProductSettings(
            stripe_starter_product_id="prod_starter",
            stripe_starter_monthly_price_id="price_starter_monthly",
        )

        assert is_stripe_configured() is True


class TestGetAllProducts:
    """Tests for get_all_products function."""

    @patch("ace_platform.core.stripe_config.get_stripe_product_settings")
    def test_get_all_products(self, mock_settings):
        """Test getting all configured products."""
        mock_settings.return_value = StripeProductSettings(
            stripe_starter_product_id="prod_starter",
            stripe_starter_monthly_price_id="price_starter",
            stripe_professional_product_id="prod_pro",
            stripe_professional_monthly_price_id="price_pro",
            stripe_enterprise_product_id="prod_enterprise",
        )

        products = get_all_products()

        assert len(products) == 3
        tiers = [p.tier for p in products]
        assert SubscriptionTier.STARTER in tiers
        assert SubscriptionTier.PROFESSIONAL in tiers
        assert SubscriptionTier.ENTERPRISE in tiers
        # FREE tier is not included
        assert SubscriptionTier.FREE not in tiers

    @patch("ace_platform.core.stripe_config.get_stripe_product_settings")
    def test_get_all_products_empty_settings(self, mock_settings):
        """Test get_all_products with no configured products."""
        mock_settings.return_value = StripeProductSettings()

        products = get_all_products()

        # Still returns configs, just with empty IDs
        assert len(products) == 3
