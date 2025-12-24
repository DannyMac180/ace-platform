"""Billing service for Stripe subscription management.

This module provides functions for:
- Creating and managing Stripe customers
- Creating checkout sessions for subscriptions
- Creating billing portal sessions
- Managing subscription state
"""

from dataclasses import dataclass

import stripe
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.config import get_settings
from ace_platform.core.limits import SubscriptionTier
from ace_platform.core.stripe_config import (
    BillingInterval,
    get_price_id_for_tier,
    get_product_config,
    is_stripe_configured,
)
from ace_platform.db.models import User


@dataclass
class CheckoutSessionResult:
    """Result of creating a checkout session."""

    success: bool
    checkout_url: str | None = None
    session_id: str | None = None
    error: str | None = None


@dataclass
class PortalSessionResult:
    """Result of creating a billing portal session."""

    success: bool
    portal_url: str | None = None
    error: str | None = None


def _get_stripe_client() -> stripe.StripeClient:
    """Get configured Stripe client.

    Returns:
        Configured Stripe client instance.

    Raises:
        ValueError: If Stripe is not configured.
    """
    settings = get_settings()
    if not settings.billing_enabled:
        raise ValueError("Billing is not enabled. Set BILLING_ENABLED=true in environment.")
    if not settings.stripe_secret_key:
        raise ValueError("Stripe secret key not configured. Set STRIPE_SECRET_KEY in environment.")
    return stripe.StripeClient(settings.stripe_secret_key)


async def get_or_create_stripe_customer(
    db: AsyncSession,
    user: User,
) -> str:
    """Get existing Stripe customer or create a new one.

    Args:
        db: Database session.
        user: User to get/create customer for.

    Returns:
        Stripe customer ID.

    Raises:
        stripe.StripeError: If Stripe API call fails.
    """
    # Return existing customer if present
    if user.stripe_customer_id:
        return user.stripe_customer_id

    # Create new Stripe customer
    client = _get_stripe_client()
    customer = client.customers.create(
        params={
            "email": user.email,
            "metadata": {
                "user_id": str(user.id),
                "platform": "ace-platform",
            },
        }
    )

    # Update user with Stripe customer ID
    await db.execute(update(User).where(User.id == user.id).values(stripe_customer_id=customer.id))
    await db.commit()

    # Update the user object in memory
    user.stripe_customer_id = customer.id

    return customer.id


async def create_checkout_session(
    db: AsyncSession,
    user: User,
    tier: SubscriptionTier,
    interval: BillingInterval = BillingInterval.MONTHLY,
    success_url: str | None = None,
    cancel_url: str | None = None,
) -> CheckoutSessionResult:
    """Create a Stripe checkout session for subscription.

    Args:
        db: Database session.
        user: User creating the subscription.
        tier: Subscription tier to subscribe to.
        interval: Billing interval (monthly or yearly).
        success_url: URL to redirect to on successful checkout.
        cancel_url: URL to redirect to if checkout is cancelled.

    Returns:
        CheckoutSessionResult with checkout URL or error.
    """
    # Validate tier
    if tier == SubscriptionTier.FREE:
        return CheckoutSessionResult(
            success=False,
            error="Free tier does not require checkout. Use the free tier directly.",
        )

    if tier == SubscriptionTier.ENTERPRISE:
        return CheckoutSessionResult(
            success=False,
            error="Enterprise tier requires custom pricing. Please contact sales.",
        )

    # Check if Stripe is configured
    if not is_stripe_configured():
        return CheckoutSessionResult(
            success=False,
            error="Stripe products are not configured. Please contact support.",
        )

    # Get price ID for tier
    price_id = get_price_id_for_tier(tier, interval)
    if not price_id:
        return CheckoutSessionResult(
            success=False,
            error=f"No price configured for {tier.value} tier.",
        )

    try:
        # Get or create Stripe customer
        customer_id = await get_or_create_stripe_customer(db, user)

        # Get default URLs from settings
        settings = get_settings()
        base_url = f"http://localhost:{settings.api_port}"
        if settings.cors_origins:
            # Use first CORS origin as base URL (typically the frontend)
            base_url = settings.cors_origins[0]

        final_success_url = (
            success_url or f"{base_url}/billing/success?session_id={{CHECKOUT_SESSION_ID}}"
        )
        final_cancel_url = cancel_url or f"{base_url}/billing/cancel"

        # Create checkout session
        client = _get_stripe_client()
        session = client.checkout.sessions.create(
            params={
                "customer": customer_id,
                "mode": "subscription",
                "line_items": [
                    {
                        "price": price_id,
                        "quantity": 1,
                    }
                ],
                "success_url": final_success_url,
                "cancel_url": final_cancel_url,
                "metadata": {
                    "user_id": str(user.id),
                    "tier": tier.value,
                    "interval": interval.value,
                },
                "subscription_data": {
                    "metadata": {
                        "user_id": str(user.id),
                        "tier": tier.value,
                    },
                },
            }
        )

        return CheckoutSessionResult(
            success=True,
            checkout_url=session.url,
            session_id=session.id,
        )

    except stripe.StripeError as e:
        return CheckoutSessionResult(
            success=False,
            error=f"Stripe error: {str(e)}",
        )
    except ValueError as e:
        return CheckoutSessionResult(
            success=False,
            error=str(e),
        )


async def create_billing_portal_session(
    user: User,
    return_url: str | None = None,
) -> PortalSessionResult:
    """Create a Stripe billing portal session.

    Args:
        user: User to create portal session for.
        return_url: URL to redirect to when leaving the portal.

    Returns:
        PortalSessionResult with portal URL or error.
    """
    if not user.stripe_customer_id:
        return PortalSessionResult(
            success=False,
            error="No billing account found. Please subscribe to a plan first.",
        )

    try:
        client = _get_stripe_client()

        # Get default return URL
        settings = get_settings()
        base_url = f"http://localhost:{settings.api_port}"
        if settings.cors_origins:
            base_url = settings.cors_origins[0]

        final_return_url = return_url or f"{base_url}/billing"

        session = client.billing_portal.sessions.create(
            params={
                "customer": user.stripe_customer_id,
                "return_url": final_return_url,
            }
        )

        return PortalSessionResult(
            success=True,
            portal_url=session.url,
        )

    except stripe.StripeError as e:
        return PortalSessionResult(
            success=False,
            error=f"Stripe error: {str(e)}",
        )
    except ValueError as e:
        return PortalSessionResult(
            success=False,
            error=str(e),
        )


def get_subscription_tier_features(tier: SubscriptionTier) -> list[str]:
    """Get feature list for a subscription tier.

    Args:
        tier: Subscription tier.

    Returns:
        List of feature descriptions.
    """
    config = get_product_config(tier)
    if config:
        return list(config.features)

    # Default features for FREE tier
    if tier == SubscriptionTier.FREE:
        return [
            "100 requests/month",
            "100K tokens/month",
            "3 playbooks",
            "Basic models only",
        ]

    return []
