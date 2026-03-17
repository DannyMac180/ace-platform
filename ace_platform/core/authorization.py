"""Shared server-side authorization decisions for premium access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ace_platform.core.limits import SubscriptionTier, get_tier_limits

if TYPE_CHECKING:
    from ace_platform.db.models import User


PAYMENT_REQUIRED_STATUS = 402
FORBIDDEN_STATUS = 403


@dataclass(frozen=True)
class AuthorizationDecision:
    """Result of evaluating whether a user can access a protected capability."""

    allowed: bool
    detail: str | None = None
    status_code: int = FORBIDDEN_STATUS


def allow() -> AuthorizationDecision:
    """Return an allowed authorization decision."""
    return AuthorizationDecision(allowed=True)


def deny(detail: str, status_code: int = FORBIDDEN_STATUS) -> AuthorizationDecision:
    """Return a denied authorization decision."""
    return AuthorizationDecision(allowed=False, detail=detail, status_code=status_code)


def get_user_tier(user: User) -> SubscriptionTier:
    """Get the subscription tier for a user, defaulting to FREE."""
    subscription_tier = getattr(user, "subscription_tier", None)
    if not subscription_tier:
        return SubscriptionTier.FREE
    try:
        return SubscriptionTier(subscription_tier)
    except ValueError:
        return SubscriptionTier.FREE


def check_active_subscription(user: User) -> AuthorizationDecision:
    """Allow active subscriptions and free-tier users; reject broken billing states."""
    if getattr(user, "is_admin", False):
        return allow()

    subscription_status = getattr(user, "subscription_status", None)
    if subscription_status in {"none", None}:
        return allow()
    if subscription_status == "active":
        return allow()
    if subscription_status == "past_due":
        return deny(
            "Your subscription payment is past due. Please update your payment method.",
            status_code=PAYMENT_REQUIRED_STATUS,
        )
    if subscription_status == "canceled":
        return deny(
            "Your subscription has been canceled. Please resubscribe to continue.",
            status_code=PAYMENT_REQUIRED_STATUS,
        )
    if subscription_status == "unpaid":
        return deny(
            "Your subscription is unpaid. Please update your payment method.",
            status_code=PAYMENT_REQUIRED_STATUS,
        )
    return deny("Invalid subscription status")


def check_paid_access(user: User) -> AuthorizationDecision:
    """Allow only active, non-free subscriptions."""
    if getattr(user, "is_admin", False):
        return allow()

    subscription_status = getattr(user, "subscription_status", None)
    user_tier = get_user_tier(user)

    if subscription_status == "active" and user_tier != SubscriptionTier.FREE:
        return allow()
    if subscription_status in {"none", None} or user_tier == SubscriptionTier.FREE:
        return deny(
            "Start your free trial or subscribe to continue.",
            status_code=PAYMENT_REQUIRED_STATUS,
        )
    if subscription_status == "past_due":
        return deny(
            "Your subscription payment is past due. Please update your payment method.",
            status_code=PAYMENT_REQUIRED_STATUS,
        )
    if subscription_status == "canceled":
        return deny(
            "Your subscription has been canceled. Please resubscribe to continue.",
            status_code=PAYMENT_REQUIRED_STATUS,
        )
    if subscription_status == "unpaid":
        return deny(
            "Your subscription is unpaid. Please update your payment method.",
            status_code=PAYMENT_REQUIRED_STATUS,
        )
    return deny(
        "Invalid subscription status",
        status_code=PAYMENT_REQUIRED_STATUS,
    )


def check_minimum_tier(user: User, minimum_tier: SubscriptionTier) -> AuthorizationDecision:
    """Require a minimum subscription tier after basic subscription validation."""
    subscription_decision = check_active_subscription(user)
    if not subscription_decision.allowed:
        return subscription_decision

    tier_order = [
        SubscriptionTier.FREE,
        SubscriptionTier.STARTER,
        SubscriptionTier.PRO,
        SubscriptionTier.ULTRA,
        SubscriptionTier.ENTERPRISE,
    ]
    user_tier = get_user_tier(user)

    if tier_order.index(user_tier) < tier_order.index(minimum_tier):
        return deny(
            f"This feature requires a {minimum_tier.value} subscription or higher. "
            f"Your current tier is {user_tier.value}.",
            status_code=PAYMENT_REQUIRED_STATUS,
        )

    return allow()


def check_feature_access(user: User, feature: str) -> AuthorizationDecision:
    """Require a specific entitlement flag from the user's tier limits."""
    subscription_decision = check_active_subscription(user)
    if not subscription_decision.allowed:
        return subscription_decision

    user_tier = get_user_tier(user)
    limits = get_tier_limits(user_tier)

    if not getattr(limits, feature, False):
        return deny(
            "This feature requires an upgraded subscription. "
            f"Your current tier ({user_tier.value}) does not include {feature.replace('_', ' ')}.",
            status_code=PAYMENT_REQUIRED_STATUS,
        )

    return allow()
