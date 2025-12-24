"""Stripe webhook handler.

This module handles Stripe webhook events for subscription lifecycle:
- checkout.session.completed: Subscription created via checkout
- customer.subscription.created: New subscription created
- customer.subscription.updated: Subscription updated (plan change, renewal)
- customer.subscription.deleted: Subscription cancelled
- invoice.payment_failed: Payment failed
- invoice.payment_succeeded: Payment succeeded
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum

import stripe
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.config import get_settings
from ace_platform.core.stripe_config import get_tier_from_price_id
from ace_platform.db.models import SubscriptionStatus, User

logger = logging.getLogger(__name__)


class WebhookEventType(str, Enum):
    """Stripe webhook event types we handle."""

    CHECKOUT_SESSION_COMPLETED = "checkout.session.completed"
    SUBSCRIPTION_CREATED = "customer.subscription.created"
    SUBSCRIPTION_UPDATED = "customer.subscription.updated"
    SUBSCRIPTION_DELETED = "customer.subscription.deleted"
    INVOICE_PAYMENT_FAILED = "invoice.payment_failed"
    INVOICE_PAYMENT_SUCCEEDED = "invoice.payment_succeeded"


@dataclass
class WebhookResult:
    """Result of processing a webhook event."""

    success: bool
    message: str
    event_type: str | None = None
    user_id: str | None = None


def verify_webhook_signature(payload: bytes, signature: str) -> stripe.Event | None:
    """Verify Stripe webhook signature and construct event.

    Args:
        payload: Raw request body bytes.
        signature: Stripe-Signature header value.

    Returns:
        Verified Stripe Event, or None if verification fails.
    """
    settings = get_settings()
    if not settings.stripe_webhook_secret:
        logger.error("Stripe webhook secret not configured")
        return None

    try:
        event = stripe.Webhook.construct_event(
            payload,
            signature,
            settings.stripe_webhook_secret,
        )
        return event
    except stripe.SignatureVerificationError as e:
        logger.warning(f"Webhook signature verification failed: {e}")
        return None
    except ValueError as e:
        logger.warning(f"Invalid webhook payload: {e}")
        return None


async def handle_webhook_event(
    db: AsyncSession,
    event: stripe.Event,
) -> WebhookResult:
    """Handle a verified Stripe webhook event.

    Args:
        db: Database session.
        event: Verified Stripe event.

    Returns:
        WebhookResult indicating success or failure.
    """
    event_type = event.type
    logger.info(f"Processing webhook event: {event_type}")

    try:
        if event_type == WebhookEventType.CHECKOUT_SESSION_COMPLETED:
            return await _handle_checkout_completed(db, event)
        elif event_type == WebhookEventType.SUBSCRIPTION_CREATED:
            return await _handle_subscription_created(db, event)
        elif event_type == WebhookEventType.SUBSCRIPTION_UPDATED:
            return await _handle_subscription_updated(db, event)
        elif event_type == WebhookEventType.SUBSCRIPTION_DELETED:
            return await _handle_subscription_deleted(db, event)
        elif event_type == WebhookEventType.INVOICE_PAYMENT_FAILED:
            return await _handle_payment_failed(db, event)
        elif event_type == WebhookEventType.INVOICE_PAYMENT_SUCCEEDED:
            return await _handle_payment_succeeded(db, event)
        else:
            # Unhandled event type - acknowledge receipt
            logger.debug(f"Ignoring unhandled event type: {event_type}")
            return WebhookResult(
                success=True,
                message=f"Event type {event_type} acknowledged but not handled",
                event_type=event_type,
            )
    except Exception as e:
        logger.exception(f"Error handling webhook event {event_type}: {e}")
        return WebhookResult(
            success=False,
            message=f"Error processing event: {str(e)}",
            event_type=event_type,
        )


async def _get_user_by_customer_id(
    db: AsyncSession,
    customer_id: str,
) -> User | None:
    """Look up user by Stripe customer ID."""
    result = await db.execute(select(User).where(User.stripe_customer_id == customer_id))
    return result.scalar_one_or_none()


async def _get_user_by_metadata(
    db: AsyncSession,
    metadata: dict,
) -> User | None:
    """Look up user by user_id in metadata."""
    user_id = metadata.get("user_id")
    if not user_id:
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


def _map_stripe_status(stripe_status: str) -> SubscriptionStatus:
    """Map Stripe subscription status to our status enum."""
    status_map = {
        "active": SubscriptionStatus.ACTIVE,
        "past_due": SubscriptionStatus.PAST_DUE,
        "canceled": SubscriptionStatus.CANCELED,
        "unpaid": SubscriptionStatus.UNPAID,
        "incomplete": SubscriptionStatus.NONE,
        "incomplete_expired": SubscriptionStatus.CANCELED,
        "trialing": SubscriptionStatus.ACTIVE,
        "paused": SubscriptionStatus.NONE,
    }
    return status_map.get(stripe_status, SubscriptionStatus.NONE)


def _get_subscription_tier(subscription: stripe.Subscription) -> str | None:
    """Extract tier from subscription items."""
    if not subscription.items or not subscription.items.data:
        return None

    # Get the first item's price ID
    first_item = subscription.items.data[0]
    price_id = first_item.price.id if first_item.price else None

    if price_id:
        tier = get_tier_from_price_id(price_id)
        return tier.value if tier else None

    return None


async def _handle_checkout_completed(
    db: AsyncSession,
    event: stripe.Event,
) -> WebhookResult:
    """Handle checkout.session.completed event.

    This fires when a customer completes Stripe Checkout.
    """
    session = event.data.object
    customer_id = session.customer
    subscription_id = session.subscription
    metadata = session.metadata or {}

    logger.info(f"Checkout completed: customer={customer_id}, subscription={subscription_id}")

    # Find user by metadata or customer ID
    user = await _get_user_by_metadata(db, metadata)
    if not user:
        user = await _get_user_by_customer_id(db, customer_id)

    if not user:
        logger.warning(f"No user found for checkout session: {session.id}")
        return WebhookResult(
            success=False,
            message="User not found for checkout session",
            event_type=event.type,
        )

    # Update user with customer and subscription ID
    tier = metadata.get("tier")
    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            stripe_customer_id=customer_id,
            stripe_subscription_id=subscription_id,
            subscription_tier=tier,
            subscription_status=SubscriptionStatus.ACTIVE,
        )
    )
    await db.commit()

    logger.info(f"Updated user {user.id} with subscription {subscription_id}")
    return WebhookResult(
        success=True,
        message="Checkout session processed",
        event_type=event.type,
        user_id=str(user.id),
    )


async def _handle_subscription_created(
    db: AsyncSession,
    event: stripe.Event,
) -> WebhookResult:
    """Handle customer.subscription.created event."""
    subscription = event.data.object
    customer_id = subscription.customer

    user = await _get_user_by_customer_id(db, customer_id)
    if not user:
        logger.warning(f"No user found for customer: {customer_id}")
        return WebhookResult(
            success=False,
            message="User not found for customer",
            event_type=event.type,
        )

    tier = _get_subscription_tier(subscription)
    status = _map_stripe_status(subscription.status)
    period_end = datetime.fromtimestamp(subscription.current_period_end, tz=UTC)

    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            stripe_subscription_id=subscription.id,
            subscription_tier=tier,
            subscription_status=status,
            subscription_current_period_end=period_end,
        )
    )
    await db.commit()

    logger.info(f"Subscription created for user {user.id}: {subscription.id}")
    return WebhookResult(
        success=True,
        message="Subscription created",
        event_type=event.type,
        user_id=str(user.id),
    )


async def _handle_subscription_updated(
    db: AsyncSession,
    event: stripe.Event,
) -> WebhookResult:
    """Handle customer.subscription.updated event.

    This fires on renewals, plan changes, and status changes.
    """
    subscription = event.data.object
    customer_id = subscription.customer

    user = await _get_user_by_customer_id(db, customer_id)
    if not user:
        logger.warning(f"No user found for customer: {customer_id}")
        return WebhookResult(
            success=False,
            message="User not found for customer",
            event_type=event.type,
        )

    tier = _get_subscription_tier(subscription)
    status = _map_stripe_status(subscription.status)
    period_end = datetime.fromtimestamp(subscription.current_period_end, tz=UTC)

    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            stripe_subscription_id=subscription.id,
            subscription_tier=tier,
            subscription_status=status,
            subscription_current_period_end=period_end,
        )
    )
    await db.commit()

    logger.info(f"Subscription updated for user {user.id}: status={status}")
    return WebhookResult(
        success=True,
        message="Subscription updated",
        event_type=event.type,
        user_id=str(user.id),
    )


async def _handle_subscription_deleted(
    db: AsyncSession,
    event: stripe.Event,
) -> WebhookResult:
    """Handle customer.subscription.deleted event.

    This fires when a subscription is cancelled (at period end or immediately).
    """
    subscription = event.data.object
    customer_id = subscription.customer

    user = await _get_user_by_customer_id(db, customer_id)
    if not user:
        logger.warning(f"No user found for customer: {customer_id}")
        return WebhookResult(
            success=False,
            message="User not found for customer",
            event_type=event.type,
        )

    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            stripe_subscription_id=None,
            subscription_tier=None,
            subscription_status=SubscriptionStatus.CANCELED,
            subscription_current_period_end=None,
        )
    )
    await db.commit()

    logger.info(f"Subscription cancelled for user {user.id}")
    return WebhookResult(
        success=True,
        message="Subscription cancelled",
        event_type=event.type,
        user_id=str(user.id),
    )


async def _handle_payment_failed(
    db: AsyncSession,
    event: stripe.Event,
) -> WebhookResult:
    """Handle invoice.payment_failed event.

    This fires when a subscription payment fails.
    """
    invoice = event.data.object
    customer_id = invoice.customer
    subscription_id = invoice.subscription

    if not subscription_id:
        # One-time invoice, not subscription
        return WebhookResult(
            success=True,
            message="Non-subscription invoice payment failed",
            event_type=event.type,
        )

    user = await _get_user_by_customer_id(db, customer_id)
    if not user:
        logger.warning(f"No user found for customer: {customer_id}")
        return WebhookResult(
            success=False,
            message="User not found for customer",
            event_type=event.type,
        )

    # Update status to past_due
    await db.execute(
        update(User)
        .where(User.id == user.id)
        .values(subscription_status=SubscriptionStatus.PAST_DUE)
    )
    await db.commit()

    logger.warning(f"Payment failed for user {user.id}, subscription {subscription_id}")
    return WebhookResult(
        success=True,
        message="Payment failure recorded",
        event_type=event.type,
        user_id=str(user.id),
    )


async def _handle_payment_succeeded(
    db: AsyncSession,
    event: stripe.Event,
) -> WebhookResult:
    """Handle invoice.payment_succeeded event.

    This fires when a subscription payment succeeds (including renewals).
    """
    invoice = event.data.object
    customer_id = invoice.customer
    subscription_id = invoice.subscription

    if not subscription_id:
        # One-time invoice, not subscription
        return WebhookResult(
            success=True,
            message="Non-subscription invoice payment succeeded",
            event_type=event.type,
        )

    user = await _get_user_by_customer_id(db, customer_id)
    if not user:
        logger.warning(f"No user found for customer: {customer_id}")
        return WebhookResult(
            success=False,
            message="User not found for customer",
            event_type=event.type,
        )

    # Restore active status if it was past_due
    if user.subscription_status == SubscriptionStatus.PAST_DUE:
        await db.execute(
            update(User)
            .where(User.id == user.id)
            .values(subscription_status=SubscriptionStatus.ACTIVE)
        )
        await db.commit()
        logger.info(f"Payment succeeded, restored active status for user {user.id}")

    return WebhookResult(
        success=True,
        message="Payment success recorded",
        event_type=event.type,
        user_id=str(user.id),
    )
