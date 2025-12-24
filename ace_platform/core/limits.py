"""Usage limits based on subscription tier.

This module defines subscription tiers and their usage limits,
and provides functions to check if users are within their limits.

Tiers:
- free: Limited usage for trial/free users
- starter: Basic paid tier
- professional: Higher limits for power users
- enterprise: Custom/unlimited usage
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.core.metering import get_user_usage_summary


class SubscriptionTier(str, Enum):
    """Subscription tier levels."""

    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


@dataclass(frozen=True)
class TierLimits:
    """Usage limits for a subscription tier."""

    # Monthly limits
    monthly_requests: int | None  # None = unlimited
    monthly_tokens: int | None
    monthly_cost_usd: Decimal | None

    # Per-playbook limits
    max_playbooks: int | None
    max_evolutions_per_day: int | None

    # Feature flags
    can_use_premium_models: bool
    can_export_data: bool
    priority_support: bool


# Define limits for each tier
TIER_LIMITS: dict[SubscriptionTier, TierLimits] = {
    SubscriptionTier.FREE: TierLimits(
        monthly_requests=100,
        monthly_tokens=100_000,
        monthly_cost_usd=Decimal("1.00"),
        max_playbooks=3,
        max_evolutions_per_day=5,
        can_use_premium_models=False,
        can_export_data=False,
        priority_support=False,
    ),
    SubscriptionTier.STARTER: TierLimits(
        monthly_requests=1_000,
        monthly_tokens=1_000_000,
        monthly_cost_usd=Decimal("10.00"),
        max_playbooks=10,
        max_evolutions_per_day=20,
        can_use_premium_models=True,
        can_export_data=True,
        priority_support=False,
    ),
    SubscriptionTier.PROFESSIONAL: TierLimits(
        monthly_requests=10_000,
        monthly_tokens=10_000_000,
        monthly_cost_usd=Decimal("100.00"),
        max_playbooks=50,
        max_evolutions_per_day=100,
        can_use_premium_models=True,
        can_export_data=True,
        priority_support=True,
    ),
    SubscriptionTier.ENTERPRISE: TierLimits(
        monthly_requests=None,  # Unlimited
        monthly_tokens=None,
        monthly_cost_usd=None,
        max_playbooks=None,
        max_evolutions_per_day=None,
        can_use_premium_models=True,
        can_export_data=True,
        priority_support=True,
    ),
}


@dataclass
class UsageStatus:
    """Current usage status for a user."""

    tier: SubscriptionTier
    limits: TierLimits

    # Current usage (this billing period)
    current_requests: int
    current_tokens: int
    current_cost_usd: Decimal

    # Remaining quota (None if unlimited)
    remaining_requests: int | None
    remaining_tokens: int | None
    remaining_cost_usd: Decimal | None

    # Status flags
    is_within_limits: bool
    limit_exceeded: str | None  # Which limit was exceeded, if any


def get_tier_limits(tier: SubscriptionTier) -> TierLimits:
    """Get limits for a subscription tier.

    Args:
        tier: The subscription tier.

    Returns:
        TierLimits for the tier.
    """
    return TIER_LIMITS[tier]


def get_billing_period_start() -> datetime:
    """Get the start of the current billing period.

    Returns the first day of the current month at midnight UTC.

    Returns:
        Start datetime of billing period.
    """
    now = datetime.now(UTC)
    return datetime(now.year, now.month, 1, tzinfo=UTC)


async def get_user_usage_status(
    db: AsyncSession,
    user_id: UUID,
    tier: SubscriptionTier = SubscriptionTier.FREE,
) -> UsageStatus:
    """Get current usage status for a user.

    Args:
        db: Database session.
        user_id: User ID to check.
        tier: User's subscription tier.

    Returns:
        UsageStatus with current usage and remaining quota.
    """
    limits = get_tier_limits(tier)
    period_start = get_billing_period_start()
    now = datetime.now(UTC)

    # Get current usage
    summary = await get_user_usage_summary(db, user_id, period_start, now)

    # Calculate remaining quota
    remaining_requests = None
    remaining_tokens = None
    remaining_cost_usd = None

    if limits.monthly_requests is not None:
        remaining_requests = max(0, limits.monthly_requests - summary.total_requests)
    if limits.monthly_tokens is not None:
        remaining_tokens = max(0, limits.monthly_tokens - summary.total_tokens)
    if limits.monthly_cost_usd is not None:
        remaining_cost_usd = max(Decimal("0"), limits.monthly_cost_usd - summary.total_cost_usd)

    # Check if within limits
    limit_exceeded = None
    is_within_limits = True

    if limits.monthly_requests is not None and summary.total_requests >= limits.monthly_requests:
        is_within_limits = False
        limit_exceeded = "monthly_requests"
    elif limits.monthly_tokens is not None and summary.total_tokens >= limits.monthly_tokens:
        is_within_limits = False
        limit_exceeded = "monthly_tokens"
    elif limits.monthly_cost_usd is not None and summary.total_cost_usd >= limits.monthly_cost_usd:
        is_within_limits = False
        limit_exceeded = "monthly_cost"

    return UsageStatus(
        tier=tier,
        limits=limits,
        current_requests=summary.total_requests,
        current_tokens=summary.total_tokens,
        current_cost_usd=summary.total_cost_usd,
        remaining_requests=remaining_requests,
        remaining_tokens=remaining_tokens,
        remaining_cost_usd=remaining_cost_usd,
        is_within_limits=is_within_limits,
        limit_exceeded=limit_exceeded,
    )


async def check_can_make_request(
    db: AsyncSession,
    user_id: UUID,
    tier: SubscriptionTier = SubscriptionTier.FREE,
    estimated_tokens: int = 0,
) -> tuple[bool, str | None]:
    """Check if a user can make a new request.

    Args:
        db: Database session.
        user_id: User ID to check.
        tier: User's subscription tier.
        estimated_tokens: Estimated tokens for the request.

    Returns:
        Tuple of (can_proceed, error_message).
        If can_proceed is False, error_message contains the reason.
    """
    status = await get_user_usage_status(db, user_id, tier)

    if not status.is_within_limits:
        return False, f"Usage limit exceeded: {status.limit_exceeded}"

    # Check if estimated tokens would exceed limit
    if status.remaining_tokens is not None and estimated_tokens > status.remaining_tokens:
        return False, f"Request would exceed token limit (remaining: {status.remaining_tokens})"

    return True, None


def can_use_model(tier: SubscriptionTier, model: str) -> bool:
    """Check if a tier can use a specific model.

    Premium models (o1, gpt-4) require paid tiers.

    Args:
        tier: User's subscription tier.
        model: Model name to check.

    Returns:
        True if the tier can use the model.
    """
    limits = get_tier_limits(tier)

    # Free tier can only use mini/cheap models
    if not limits.can_use_premium_models:
        premium_prefixes = ("o1", "gpt-4-turbo", "gpt-4-0")
        if any(model.startswith(prefix) for prefix in premium_prefixes):
            return False

    return True
