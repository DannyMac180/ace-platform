"""Billing API routes.

This module provides REST API endpoints for billing and subscriptions:
- GET /billing/subscription - Get current subscription info
- POST /billing/subscribe - Subscribe to a plan
- GET /billing/usage - Get usage summary for billing
- POST /billing/portal - Create Stripe billing portal session
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
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
            monthly_requests=limits.monthly_requests,
            monthly_tokens=limits.monthly_tokens,
            monthly_cost_usd=limits.monthly_cost_usd,
            max_playbooks=limits.max_playbooks,
            max_evolutions_per_day=limits.max_evolutions_per_day,
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
        requests_used=status.current_requests,
        requests_limit=status.limits.monthly_requests,
        requests_remaining=status.remaining_requests,
        tokens_used=status.current_tokens,
        tokens_limit=status.limits.monthly_tokens,
        tokens_remaining=status.remaining_tokens,
        cost_usd=status.current_cost_usd,
        cost_limit_usd=status.limits.monthly_cost_usd,
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
                    monthly_requests=limits.monthly_requests,
                    monthly_tokens=limits.monthly_tokens,
                    monthly_cost_usd=limits.monthly_cost_usd,
                    max_playbooks=limits.max_playbooks,
                    max_evolutions_per_day=limits.max_evolutions_per_day,
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
        SubscriptionTier.PROFESSIONAL,
    ]:
        result = await create_checkout_session(
            db=db,
            user=current_user,
            tier=request.tier,
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
