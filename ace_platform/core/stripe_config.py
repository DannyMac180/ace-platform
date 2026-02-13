"""Stripe products and prices configuration.

This module defines the Stripe product and price configuration for
subscription tiers. It provides utilities to look up prices and
manage Stripe product synchronization.

Products and prices should be created in Stripe Dashboard or via API,
then their IDs configured via environment variables.

Pricing (per BILLING_DECISIONS.md):
- Starter: $9/month, $90/year (100 evolution runs/month)
- Pro: $29/month, $290/year (500 evolution runs/month)
- Ultra: $79/month, $790/year (2,000 evolution runs/month)
- Enterprise: Custom pricing (unlimited)
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ace_platform.core.limits import SubscriptionTier


class BillingInterval(str, Enum):
    """Billing interval for subscription prices."""

    MONTHLY = "month"
    YEARLY = "year"


@dataclass(frozen=True)
class PriceConfig:
    """Configuration for a Stripe price.

    Attributes:
        price_id: Stripe price ID (from Stripe Dashboard).
        unit_amount: Price in cents (e.g., 900 = $9.00).
        currency: ISO currency code (default: usd).
        interval: Billing interval (month or year).
        product_id: Stripe product ID this price belongs to.
    """

    price_id: str
    unit_amount: int  # In cents
    currency: str = "usd"
    interval: BillingInterval = BillingInterval.MONTHLY
    product_id: str | None = None

    @property
    def amount_decimal(self) -> Decimal:
        """Get price as a Decimal dollar amount."""
        return Decimal(self.unit_amount) / 100


@dataclass(frozen=True)
class ProductConfig:
    """Configuration for a Stripe product.

    Attributes:
        product_id: Stripe product ID.
        name: Display name for the product.
        description: Product description.
        tier: Corresponding subscription tier.
        monthly_price: Monthly price configuration.
        yearly_price: Optional yearly price configuration (with discount).
        features: List of features included in this tier.
    """

    product_id: str
    name: str
    description: str
    tier: SubscriptionTier
    monthly_price: PriceConfig
    yearly_price: PriceConfig | None = None
    features: tuple[str, ...] = ()


class StripeProductSettings(BaseSettings):
    """Stripe product and price IDs from environment.

    These IDs are created in Stripe Dashboard and configured here.
    Use test mode IDs for development and live mode IDs for production.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Starter tier ($9/month)
    stripe_starter_product_id: str = Field(
        default="",
        description="Stripe product ID for Starter tier",
    )
    stripe_starter_monthly_price_id: str = Field(
        default="",
        description="Stripe price ID for Starter monthly subscription",
    )
    stripe_starter_yearly_price_id: str = Field(
        default="",
        description="Stripe price ID for Starter yearly subscription",
    )

    # Pro tier ($29/month)
    stripe_pro_product_id: str = Field(
        default="",
        description="Stripe product ID for Pro tier",
    )
    stripe_pro_monthly_price_id: str = Field(
        default="",
        description="Stripe price ID for Pro monthly subscription",
    )
    stripe_pro_yearly_price_id: str = Field(
        default="",
        description="Stripe price ID for Pro yearly subscription",
    )

    # Ultra tier ($79/month)
    stripe_ultra_product_id: str = Field(
        default="",
        description="Stripe product ID for Ultra tier",
    )
    stripe_ultra_monthly_price_id: str = Field(
        default="",
        description="Stripe price ID for Ultra monthly subscription",
    )
    stripe_ultra_yearly_price_id: str = Field(
        default="",
        description="Stripe price ID for Ultra yearly subscription",
    )

    # Enterprise tier (custom pricing)
    stripe_enterprise_product_id: str = Field(
        default="",
        description="Stripe product ID for Enterprise tier",
    )

    # Founding member coupon (20% off for life, first 100 customers, Pro/Ultra only)
    stripe_founding_member_coupon_id: str = Field(
        default="",
        description="Stripe coupon ID for founding member discount (Pro/Ultra only)",
    )


# Pricing constants (in cents) - per BILLING_DECISIONS.md
STARTER_MONTHLY_PRICE_CENTS = 900  # $9.00/month
STARTER_YEARLY_PRICE_CENTS = 9000  # $90.00/year (2 months free)
PRO_MONTHLY_PRICE_CENTS = 2900  # $29.00/month
PRO_YEARLY_PRICE_CENTS = 29000  # $290.00/year (2 months free)
ULTRA_MONTHLY_PRICE_CENTS = 7900  # $79.00/month
ULTRA_YEARLY_PRICE_CENTS = 79000  # $790.00/year (2 months free)


def get_stripe_product_settings() -> StripeProductSettings:
    """Get Stripe product settings from environment."""
    return StripeProductSettings()


def get_product_config(tier: SubscriptionTier) -> ProductConfig | None:
    """Get product configuration for a subscription tier.

    Args:
        tier: The subscription tier to get config for.

    Returns:
        ProductConfig if the tier has a Stripe product, None otherwise.
        FREE tier returns None (no Stripe product - internal use only).
        ENTERPRISE tier returns config but requires custom handling.
    """
    settings = get_stripe_product_settings()

    if tier == SubscriptionTier.FREE:
        # Free tier has no Stripe product (internal use only)
        return None

    if tier == SubscriptionTier.STARTER:
        return ProductConfig(
            product_id=settings.stripe_starter_product_id,
            name="ACE Starter",
            description="Get started with self-improving AI playbooks",
            tier=SubscriptionTier.STARTER,
            monthly_price=PriceConfig(
                price_id=settings.stripe_starter_monthly_price_id,
                unit_amount=STARTER_MONTHLY_PRICE_CENTS,
                product_id=settings.stripe_starter_product_id,
            ),
            yearly_price=PriceConfig(
                price_id=settings.stripe_starter_yearly_price_id,
                unit_amount=STARTER_YEARLY_PRICE_CENTS,
                interval=BillingInterval.YEARLY,
                product_id=settings.stripe_starter_product_id,
            )
            if settings.stripe_starter_yearly_price_id
            else None,
            features=(
                "100 evolution runs/month",
                "5 playbooks",
                "API access",
                "Premium models",
            ),
        )

    if tier == SubscriptionTier.PRO:
        return ProductConfig(
            product_id=settings.stripe_pro_product_id,
            name="ACE Pro",
            description="For power users who need more evolutions",
            tier=SubscriptionTier.PRO,
            monthly_price=PriceConfig(
                price_id=settings.stripe_pro_monthly_price_id,
                unit_amount=PRO_MONTHLY_PRICE_CENTS,
                product_id=settings.stripe_pro_product_id,
            ),
            yearly_price=PriceConfig(
                price_id=settings.stripe_pro_yearly_price_id,
                unit_amount=PRO_YEARLY_PRICE_CENTS,
                interval=BillingInterval.YEARLY,
                product_id=settings.stripe_pro_product_id,
            )
            if settings.stripe_pro_yearly_price_id
            else None,
            features=(
                "500 evolution runs/month",
                "20 playbooks",
                "API access",
                "Premium models",
                "Priority support",
            ),
        )

    if tier == SubscriptionTier.ULTRA:
        return ProductConfig(
            product_id=settings.stripe_ultra_product_id,
            name="ACE Ultra",
            description="High-volume tier for teams and power users",
            tier=SubscriptionTier.ULTRA,
            monthly_price=PriceConfig(
                price_id=settings.stripe_ultra_monthly_price_id,
                unit_amount=ULTRA_MONTHLY_PRICE_CENTS,
                product_id=settings.stripe_ultra_product_id,
            ),
            yearly_price=PriceConfig(
                price_id=settings.stripe_ultra_yearly_price_id,
                unit_amount=ULTRA_YEARLY_PRICE_CENTS,
                interval=BillingInterval.YEARLY,
                product_id=settings.stripe_ultra_product_id,
            )
            if settings.stripe_ultra_yearly_price_id
            else None,
            features=(
                "2,000 evolution runs/month",
                "100 playbooks",
                "API access",
                "Premium models",
                "Priority support",
            ),
        )

    if tier == SubscriptionTier.ENTERPRISE:
        return ProductConfig(
            product_id=settings.stripe_enterprise_product_id,
            name="ACE Enterprise",
            description="Custom solutions for large organizations",
            tier=SubscriptionTier.ENTERPRISE,
            monthly_price=PriceConfig(
                price_id="",  # Custom pricing - handled separately
                unit_amount=0,
                product_id=settings.stripe_enterprise_product_id,
            ),
            features=(
                "Unlimited evolution runs",
                "Unlimited playbooks",
                "API access",
                "Premium models",
                "Priority support",
                "Dedicated account manager",
                "Custom integrations",
            ),
        )

    return None


def get_price_id_for_tier(
    tier: SubscriptionTier,
    interval: BillingInterval = BillingInterval.MONTHLY,
) -> str | None:
    """Get the Stripe price ID for a subscription tier.

    Args:
        tier: The subscription tier.
        interval: Billing interval (monthly or yearly).

    Returns:
        Stripe price ID if available, None otherwise.
    """
    config = get_product_config(tier)
    if not config:
        return None

    if interval == BillingInterval.YEARLY and config.yearly_price:
        return config.yearly_price.price_id
    return config.monthly_price.price_id


def get_tier_from_price_id(price_id: str) -> SubscriptionTier | None:
    """Look up subscription tier from a Stripe price ID.

    Args:
        price_id: Stripe price ID from webhook or API.

    Returns:
        Corresponding SubscriptionTier, or None if not found.
    """
    for tier in [
        SubscriptionTier.STARTER,
        SubscriptionTier.PRO,
        SubscriptionTier.ULTRA,
        SubscriptionTier.ENTERPRISE,
    ]:
        config = get_product_config(tier)
        if not config:
            continue
        if config.monthly_price.price_id == price_id:
            return tier
        if config.yearly_price and config.yearly_price.price_id == price_id:
            return tier
    return None


def get_tier_from_product_id(product_id: str) -> SubscriptionTier | None:
    """Look up subscription tier from a Stripe product ID.

    Args:
        product_id: Stripe product ID from webhook or API.

    Returns:
        Corresponding SubscriptionTier, or None if not found.
    """
    for tier in [
        SubscriptionTier.STARTER,
        SubscriptionTier.PRO,
        SubscriptionTier.ULTRA,
        SubscriptionTier.ENTERPRISE,
    ]:
        config = get_product_config(tier)
        if config and config.product_id == product_id:
            return tier
    return None


def is_stripe_configured() -> bool:
    """Check if Stripe products are configured.

    Returns:
        True if at least the Starter tier has product and price IDs configured.
    """
    settings = get_stripe_product_settings()
    return bool(settings.stripe_starter_product_id and settings.stripe_starter_monthly_price_id)


def get_all_products() -> list[ProductConfig]:
    """Get all configured product configurations.

    Returns:
        List of ProductConfig for all tiers that have Stripe products.
    """
    products = []
    for tier in [
        SubscriptionTier.STARTER,
        SubscriptionTier.PRO,
        SubscriptionTier.ULTRA,
        SubscriptionTier.ENTERPRISE,
    ]:
        config = get_product_config(tier)
        if config:
            products.append(config)
    return products
