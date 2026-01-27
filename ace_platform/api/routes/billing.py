"""Billing API routes.

This module provides REST API endpoints for billing and subscriptions:
- GET /billing/subscription - Get current subscription info
- POST /billing/subscribe - Subscribe to a plan
- GET /billing/usage - Get usage summary for billing
- POST /billing/portal - Create Stripe billing portal session
- POST /billing/webhook - Handle Stripe webhook events
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.api.auth import require_user
from ace_platform.api.deps import get_db
from ace_platform.core.limits import (
    SubscriptionTier,
    get_billing_period_start,
    get_tier_limits,
    get_user_usage_status,
)
from ace_platform.db.models import User

router = APIRouter(prefix="/billing", tags=["billing"])


# Pydantic Schemas


class TierLimitsResponse(BaseModel):
    """Response schema for tier limits."""

    monthly_requests: int | None
    monthly_tokens: int | None
    monthly_cost_usd: Decimal | None
    max_playbooks: int | None
    max_evolutions_per_day: int | None
    can_use_premium_models: bool
    can_export_data: bool
    priority_support: bool


class SubscriptionResponse(BaseModel):
    """Response schema for subscription info."""

    tier: SubscriptionTier
    status: str  # active, canceled, past_due, etc.
    current_period_start: datetime
    current_period_end: datetime
    limits: TierLimitsResponse
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None


class UsageResponse(BaseModel):
    """Response schema for billing usage."""

    period_start: datetime
    period_end: datetime
    requests_used: int
    requests_limit: int | None
    requests_remaining: int | None
    tokens_used: int
    tokens_limit: int | None
    tokens_remaining: int | None
    cost_usd: Decimal
    cost_limit_usd: Decimal | None
    cost_remaining_usd: Decimal | None
    is_within_limits: bool
    limit_exceeded: str | None


class SubscribeRequest(BaseModel):
    """Request schema for subscribing to a plan."""

    tier: SubscriptionTier = Field(..., description="Subscription tier to subscribe to")
    payment_method_id: str | None = Field(
        None, description="Stripe payment method ID (required for paid tiers)"
    )


class SubscribeResponse(BaseModel):
    """Response schema for subscribe action."""

    success: bool
    message: str
    subscription: SubscriptionResponse | None = None
    checkout_url: str | None = None  # For Stripe checkout redirect


class PortalResponse(BaseModel):
    """Response schema for billing portal."""

    url: str


class CardSetupResponse(BaseModel):
    """Response schema for card setup session."""

    success: bool
    checkout_url: str | None = None
    message: str


class CardStatusResponse(BaseModel):
    """Response schema for card status check."""

    has_payment_method: bool
    payment_method_id: str | None = None


# Dependency type aliases
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(require_user)]


def _get_current_period_end() -> datetime:
    """Get the end of the current billing period (last day of month)."""
    now = datetime.now(UTC)
    # Get first day of next month
    if now.month == 12:
        next_month = datetime(now.year + 1, 1, 1, tzinfo=UTC)
    else:
        next_month = datetime(now.year, now.month + 1, 1, tzinfo=UTC)
    return next_month


def _get_user_tier(user: User) -> SubscriptionTier:
    """Get user's subscription tier.

    For now, users with stripe_customer_id are assumed to be on starter tier,
    otherwise free tier. This will be enhanced when Stripe integration is complete.
    """
    # TODO: Look up actual subscription from Stripe or database
    if user.stripe_customer_id:
        return SubscriptionTier.STARTER
    return SubscriptionTier.FREE


# Route handlers


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    current_user: CurrentUser,
) -> SubscriptionResponse:
    """Get current subscription information.

    Returns the user's subscription tier, status, and limits.
    """
    tier = _get_user_tier(current_user)
    limits = get_tier_limits(tier)

    return SubscriptionResponse(
        tier=tier,
        status="active",
        current_period_start=get_billing_period_start(),
        current_period_end=_get_current_period_end(),
        limits=TierLimitsResponse(
            monthly_requests=limits.monthly_evolution_runs,
            monthly_tokens=None,  # Not tracked separately
            monthly_cost_usd=limits.monthly_cost_limit_usd,
            max_playbooks=limits.max_playbooks,
            max_evolutions_per_day=None,  # Evolution is tracked monthly
            can_use_premium_models=limits.can_use_premium_models,
            can_export_data=limits.can_export_data,
            priority_support=limits.priority_support,
        ),
        stripe_customer_id=current_user.stripe_customer_id,
        stripe_subscription_id=None,  # TODO: Add when Stripe integration complete
    )


@router.get("/usage", response_model=UsageResponse)
async def get_billing_usage(
    db: DbSession,
    current_user: CurrentUser,
) -> UsageResponse:
    """Get usage summary for the current billing period.

    Returns current usage, limits, and remaining quota.
    """
    tier = _get_user_tier(current_user)
    status = await get_user_usage_status(db, current_user.id, tier)

    return UsageResponse(
        period_start=get_billing_period_start(),
        period_end=_get_current_period_end(),
        requests_used=status.current_evolution_runs,
        requests_limit=status.limits.monthly_evolution_runs,
        requests_remaining=status.remaining_evolution_runs,
        tokens_used=0,  # Token tracking not implemented
        tokens_limit=None,
        tokens_remaining=None,
        cost_usd=status.current_cost_usd,
        cost_limit_usd=status.limits.monthly_cost_limit_usd,
        cost_remaining_usd=status.remaining_cost_usd,
        is_within_limits=status.is_within_limits,
        limit_exceeded=status.limit_exceeded,
    )


@router.post("/subscribe", response_model=SubscribeResponse)
async def subscribe(
    db: DbSession,
    current_user: CurrentUser,
    request: SubscribeRequest,
) -> SubscribeResponse:
    """Subscribe to a plan.

    For free tier, immediately activates.
    For paid tiers, returns a Stripe checkout URL for payment.
    """
    from ace_platform.core.billing import create_checkout_session

    # Handle free tier subscription
    if request.tier == SubscriptionTier.FREE:
        limits = get_tier_limits(SubscriptionTier.FREE)
        return SubscribeResponse(
            success=True,
            message="You are now on the Free plan",
            subscription=SubscriptionResponse(
                tier=SubscriptionTier.FREE,
                status="active",
                current_period_start=get_billing_period_start(),
                current_period_end=_get_current_period_end(),
                limits=TierLimitsResponse(
                    monthly_requests=limits.monthly_evolution_runs,
                    monthly_tokens=None,
                    monthly_cost_usd=limits.monthly_cost_limit_usd,
                    max_playbooks=limits.max_playbooks,
                    max_evolutions_per_day=None,
                    can_use_premium_models=limits.can_use_premium_models,
                    can_export_data=limits.can_export_data,
                    priority_support=limits.priority_support,
                ),
                stripe_customer_id=current_user.stripe_customer_id,
            ),
        )

    # For paid tiers, create a Stripe checkout session
    if request.tier in [
        SubscriptionTier.STARTER,
        SubscriptionTier.PRO,
        SubscriptionTier.ULTRA,
    ]:
        # Include 7-day trial for Starter tier if user hasn't used trial before
        include_trial = request.tier == SubscriptionTier.STARTER and not current_user.has_used_trial

        result = await create_checkout_session(
            db=db,
            user=current_user,
            tier=request.tier,
            include_trial=include_trial,
        )

        if result.success:
            return SubscribeResponse(
                success=True,
                message=f"Checkout session created for {request.tier.value} tier",
                subscription=None,
                checkout_url=result.checkout_url,
            )
        else:
            return SubscribeResponse(
                success=False,
                message=result.error or "Failed to create checkout session",
                subscription=None,
                checkout_url=None,
            )

    # Enterprise requires custom handling
    if request.tier == SubscriptionTier.ENTERPRISE:
        return SubscribeResponse(
            success=False,
            message="Enterprise tier requires custom pricing. Please contact sales.",
            subscription=None,
            checkout_url=None,
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Invalid subscription tier: {request.tier}",
    )


@router.post("/portal", response_model=PortalResponse)
async def create_billing_portal(
    current_user: CurrentUser,
) -> PortalResponse:
    """Create a Stripe billing portal session.

    Returns a URL to redirect the user to manage their subscription.
    """
    from ace_platform.core.billing import create_billing_portal_session

    if not current_user.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No billing account found. Please subscribe to a plan first.",
        )

    result = await create_billing_portal_session(user=current_user)

    if result.success and result.portal_url:
        return PortalResponse(url=result.portal_url)

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=result.error or "Failed to create billing portal session",
    )


@router.post("/setup-card", response_model=CardSetupResponse)
async def setup_card(
    db: DbSession,
    current_user: CurrentUser,
) -> CardSetupResponse:
    """Initiate card setup via Stripe Checkout.

    Creates a Stripe Checkout session in 'setup' mode to collect and validate
    a payment method without charging. Returns a checkout URL for redirect.

    This is required for FREE tier users before they can trigger evolutions.
    """
    from ace_platform.core.billing import create_card_setup_session

    # If user already has a payment method, inform them
    if current_user.has_payment_method:
        return CardSetupResponse(
            success=True,
            checkout_url=None,
            message="You already have a payment method on file.",
        )

    result = await create_card_setup_session(db=db, user=current_user)

    if result.success:
        return CardSetupResponse(
            success=True,
            checkout_url=result.checkout_url,
            message="Redirect to Stripe to add your card.",
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=result.error or "Failed to create card setup session",
    )


@router.get("/card-status", response_model=CardStatusResponse)
async def get_card_status(
    current_user: CurrentUser,
) -> CardStatusResponse:
    """Check if the user has a payment method on file.

    Returns the card status and payment method ID if available.
    """
    return CardStatusResponse(
        has_payment_method=current_user.has_payment_method,
        payment_method_id=current_user.stripe_default_payment_method_id,
    )


class WebhookResponse(BaseModel):
    """Response schema for webhook endpoint."""

    received: bool
    message: str


@router.post("/webhook", response_model=WebhookResponse)
async def handle_stripe_webhook(
    request: Request,
    db: DbSession,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
) -> WebhookResponse:
    """Handle Stripe webhook events.

    This endpoint receives webhook events from Stripe for subscription lifecycle
    events (created, updated, cancelled, payment failed/succeeded).

    The endpoint verifies the webhook signature before processing.
    """
    from ace_platform.core.webhooks import (
        handle_webhook_event,
        verify_webhook_signature,
    )

    # Get raw request body for signature verification
    payload = await request.body()

    if not stripe_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe-Signature header",
        )

    # Verify webhook signature
    event = verify_webhook_signature(payload, stripe_signature)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        )

    # Process the event
    result = await handle_webhook_event(db, event)

    if not result.success:
        # Log the error but return 200 to acknowledge receipt
        # Stripe will retry if we return an error status
        return WebhookResponse(
            received=True,
            message=f"Event received but processing failed: {result.message}",
        )

    return WebhookResponse(
        received=True,
        message=result.message,
    )
