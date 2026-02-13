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
from ace_platform.db.models import ProcessedWebhookEvent, SubscriptionStatus, User

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
    event_id = event.id
    logger.info(f"Processing webhook event: {event_type} (id={event_id})")

    # Idempotency check: skip if this event has already been processed
    existing = await db.get(ProcessedWebhookEvent, event_id)
    if existing:
        logger.info(f"Skipping duplicate webhook event: {event_id}")
        return WebhookResult(
            success=True,
            message=f"Duplicate event {event_id} skipped",
            event_type=event_type,
        )

    try:
        if event_type == WebhookEventType.CHECKOUT_SESSION_COMPLETED:
            result = await _handle_checkout_completed(db, event)
        elif event_type == WebhookEventType.SUBSCRIPTION_CREATED:
            result = await _handle_subscription_created(db, event)
        elif event_type == WebhookEventType.SUBSCRIPTION_UPDATED:
            result = await _handle_subscription_updated(db, event)
        elif event_type == WebhookEventType.SUBSCRIPTION_DELETED:
            result = await _handle_subscription_deleted(db, event)
        elif event_type == WebhookEventType.INVOICE_PAYMENT_FAILED:
            result = await _handle_payment_failed(db, event)
        elif event_type == WebhookEventType.INVOICE_PAYMENT_SUCCEEDED:
            result = await _handle_payment_succeeded(db, event)
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

    # Record the event as processed for idempotency
    if result.success:
        try:
            db.add(ProcessedWebhookEvent(stripe_event_id=event_id, event_type=event_type))
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.warning(f"Failed to record processed webhook event {event_id}: {e}")

    return result


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
    Handles both subscription checkouts and setup mode (card validation).
    """
    session = event.data.object
    customer_id = session.customer
    subscription_id = session.subscription
    metadata = session.metadata or {}
    mode = getattr(session, "mode", "subscription")

    logger.info(
        f"Checkout completed: customer={customer_id}, mode={mode}, subscription={subscription_id}"
    )

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

    # Handle setup mode (card validation without charging)
    if mode == "setup":
        return await _handle_setup_mode_checkout(db, event, session, user)

    # Handle subscription checkout
    # Update user with customer and subscription ID
    tier = metadata.get("tier")
    is_trial = metadata.get("is_trial") == "true"

    # Build update values
    update_values: dict = {
        "stripe_customer_id": customer_id,
        "stripe_subscription_id": subscription_id,
        "subscription_tier": tier,
        "subscription_status": SubscriptionStatus.ACTIVE,
    }

    # If this is a trial, mark user as having used their trial and set trial_ends_at
    if is_trial:
        update_values["has_used_trial"] = True
        logger.info(f"User {user.id} started 7-day free trial")

        # Belt-and-suspenders: fetch trial_end from Stripe subscription directly
        # This guards against the race condition where subscription.created fires
        # before the customer ID is committed to the DB
        if subscription_id:
            try:
                settings = get_settings()
                if settings.stripe_secret_key:
                    client = stripe.StripeClient(settings.stripe_secret_key)
                    sub = client.subscriptions.retrieve(subscription_id)
                    if sub.trial_end:
                        trial_ends_at = datetime.fromtimestamp(sub.trial_end, tz=UTC)
                        update_values["trial_ends_at"] = trial_ends_at
                        logger.info(f"Set trial_ends_at={trial_ends_at} from checkout")
            except stripe.StripeError as e:
                logger.warning(f"Failed to fetch subscription for trial_ends_at: {e}")

    await db.execute(update(User).where(User.id == user.id).values(**update_values))
    await db.commit()

    logger.info(f"Updated user {user.id} with subscription {subscription_id}")
    return WebhookResult(
        success=True,
        message="Checkout session processed",
        event_type=event.type,
        user_id=str(user.id),
    )


async def _handle_setup_mode_checkout(
    db: AsyncSession,
    event: stripe.Event,
    session,
    user: User,
) -> WebhookResult:
    """Handle setup mode checkout completion (card validation).

    This is called when a user completes Stripe Checkout in 'setup' mode,
    which validates their card without charging.
    """
    setup_intent_id = session.setup_intent
    customer_id = session.customer

    logger.info(f"Processing setup mode checkout for user {user.id}")

    # Get payment method from the setup intent
    payment_method_id = None
    if setup_intent_id:
        try:
            settings = get_settings()
            if settings.stripe_secret_key:
                client = stripe.StripeClient(settings.stripe_secret_key)
                setup_intent = client.setup_intents.retrieve(setup_intent_id)
                payment_method_id = setup_intent.payment_method
                logger.info(f"Retrieved payment method {payment_method_id} from setup intent")
        except stripe.StripeError as e:
            logger.warning(f"Failed to retrieve setup intent: {e}")

    # Update user with payment method info
    update_values: dict = {
        "stripe_customer_id": customer_id,
        "has_payment_method": True,
    }

    if payment_method_id:
        update_values["stripe_default_payment_method_id"] = payment_method_id

    await db.execute(update(User).where(User.id == user.id).values(**update_values))
    await db.commit()

    # Record metric for card setup completed
    from ace_platform.core.metrics import increment_card_setup_completed

    increment_card_setup_completed()

    logger.info(f"User {user.id} card setup completed, has_payment_method=True")
    return WebhookResult(
        success=True,
        message="Card setup completed",
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

    # Metadata fallback: when checkout.session.completed and subscription.created
    # fire simultaneously, the customer ID may not be committed to the DB yet.
    # Fall back to user_id in subscription metadata (set in billing.py).
    if not user:
        metadata = getattr(subscription, "metadata", None) or {}
        user = await _get_user_by_metadata(db, metadata)
        if user:
            logger.info(
                f"Found user {user.id} via subscription metadata (customer_id lookup failed)"
            )

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

    # Build update values
    update_values: dict = {
        "stripe_subscription_id": subscription.id,
        "subscription_tier": tier,
        "subscription_status": status,
        "subscription_current_period_end": period_end,
    }

    # Check if subscription has a trial period
    if subscription.trial_end:
        # Duplicate trial enforcement: if user already used their trial,
        # end the unauthorized trial immediately (e.g., started via billing portal)
        if user.has_used_trial:
            logger.warning(
                f"User {user.id} attempted duplicate trial on subscription {subscription.id}"
            )
            try:
                settings = get_settings()
                if settings.stripe_secret_key:
                    client = stripe.StripeClient(settings.stripe_secret_key)
                    client.subscriptions.update(
                        subscription.id,
                        params={"trial_end": "now"},
                    )
                    logger.info(f"Ended duplicate trial for user {user.id}")
            except stripe.StripeError as e:
                logger.error(f"Failed to end duplicate trial: {e}")
        else:
            trial_ends_at = datetime.fromtimestamp(subscription.trial_end, tz=UTC)
            update_values["trial_ends_at"] = trial_ends_at
            update_values["has_used_trial"] = True
            logger.info(f"Subscription has trial ending at {trial_ends_at}")

    await db.execute(update(User).where(User.id == user.id).values(**update_values))
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

    # Metadata fallback (same race condition guard as subscription.created)
    if not user:
        metadata = getattr(subscription, "metadata", None) or {}
        user = await _get_user_by_metadata(db, metadata)
        if user:
            logger.info(
                f"Found user {user.id} via subscription metadata (customer_id lookup failed)"
            )

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

    # Build update values
    update_values: dict = {
        "stripe_subscription_id": subscription.id,
        "subscription_tier": tier,
        "subscription_status": status,
        "subscription_current_period_end": period_end,
    }

    # Update trial_ends_at (may be None if trial ended or no trial)
    if subscription.trial_end:
        trial_ends_at = datetime.fromtimestamp(subscription.trial_end, tz=UTC)
        update_values["trial_ends_at"] = trial_ends_at
    else:
        # Trial ended or no trial - clear the trial end date
        update_values["trial_ends_at"] = None

    await db.execute(update(User).where(User.id == user.id).values(**update_values))
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
            trial_ends_at=None,  # Clear trial end date
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
