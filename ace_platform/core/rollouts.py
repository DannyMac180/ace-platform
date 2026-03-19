"""Environment-aware rollout controls for pre-GA plans and capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, get_args

from ace_core.contracts import Feature
from ace_platform.config import Settings, get_settings
from ace_platform.core.limits import SubscriptionTier

if TYPE_CHECKING:
    from ace_platform.db.models import User


FEATURE_NAMES: tuple[Feature, ...] = get_args(Feature)

_DEFAULT_PLAN_AVAILABILITY: dict[SubscriptionTier, bool] = {
    SubscriptionTier.FREE: True,
    SubscriptionTier.STARTER: True,
    SubscriptionTier.PRO: True,
    SubscriptionTier.ULTRA: True,
    SubscriptionTier.ENTERPRISE: True,
}

_BASE_TIER_CAPABILITIES: dict[SubscriptionTier, frozenset[Feature]] = {
    SubscriptionTier.FREE: frozenset(),
    SubscriptionTier.STARTER: frozenset({"managed_inference", "hosted_evals"}),
    SubscriptionTier.PRO: frozenset({"managed_inference", "hosted_evals"}),
    SubscriptionTier.ULTRA: frozenset({"managed_inference", "hosted_evals"}),
    SubscriptionTier.ENTERPRISE: frozenset(
        {
            "managed_inference",
            "hosted_evals",
            "invite_members",
            "shared_workspace",
            "approvals",
            "rbac",
            "sso",
            "audit_logs",
        }
    ),
}


@dataclass(frozen=True)
class RolloutRule:
    """One rollout rule keyed by a plan or capability token."""

    enabled: bool = False
    environments: frozenset[str] = frozenset()
    emails: frozenset[str] = frozenset()
    user_ids: frozenset[str] = frozenset()


def _normalize_values(values: object) -> frozenset[str]:
    if values in (None, ""):
        return frozenset()
    if isinstance(values, str):
        return frozenset({values.strip().lower()}) if values.strip() else frozenset()
    if isinstance(values, list | tuple | set | frozenset):
        normalized = []
        for value in values:
            if value is None:
                continue
            text = str(value).strip().lower()
            if text:
                normalized.append(text)
        return frozenset(normalized)
    return frozenset({str(values).strip().lower()}) if str(values).strip() else frozenset()


def _coerce_rule(raw: object) -> RolloutRule:
    if not isinstance(raw, dict):
        return RolloutRule()
    return RolloutRule(
        enabled=bool(raw.get("enabled", False)),
        environments=_normalize_values(raw.get("environments")),
        emails=_normalize_values(raw.get("emails")),
        user_ids=_normalize_values(raw.get("user_ids")),
    )


def _normalize_environment(environment: str) -> str:
    return environment.strip().lower()


def _get_user_tier(user: User | None) -> SubscriptionTier:
    if user is None:
        return SubscriptionTier.FREE
    if getattr(user, "is_admin", False):
        return SubscriptionTier.ENTERPRISE
    tier_value = getattr(user, "subscription_tier", None)
    if not tier_value:
        return SubscriptionTier.FREE
    try:
        return SubscriptionTier(str(tier_value).lower())
    except ValueError:
        return SubscriptionTier.FREE


def _get_rollout_rules(settings: Settings | None = None) -> dict[str, RolloutRule]:
    active_settings = settings or get_settings()
    return {
        str(key).strip().lower(): _coerce_rule(value)
        for key, value in active_settings.pre_ga_rollouts.items()
    }


def plan_rollout_key(tier: SubscriptionTier) -> str:
    """Build the rollout key for a plan."""
    return f"plan:{tier.value}"


def capability_rollout_key(feature: Feature) -> str:
    """Build the rollout key for a capability."""
    return f"capability:{feature}"


def is_rollout_enabled(
    key: str,
    user: User | None = None,
    settings: Settings | None = None,
) -> bool:
    """Check whether a rollout key is enabled for the current environment or user."""
    active_settings = settings or get_settings()
    rule = _get_rollout_rules(active_settings).get(key.strip().lower())
    if rule is None:
        return False

    if getattr(user, "is_admin", False):
        return True

    environment = _normalize_environment(active_settings.environment)
    if rule.enabled or environment in rule.environments:
        return True

    if user is None:
        return False

    user_id = getattr(user, "id", None)
    if user_id is not None and str(user_id).strip().lower() in rule.user_ids:
        return True

    email = getattr(user, "email", None)
    if email is not None and str(email).strip().lower() in rule.emails:
        return True

    return False


def get_available_plans(
    user: User | None = None,
    settings: Settings | None = None,
) -> dict[str, bool]:
    """Return plan availability for the current user."""
    active_settings = settings or get_settings()
    configured_rules = _get_rollout_rules(active_settings)
    availability: dict[str, bool] = {}

    for tier, default_available in _DEFAULT_PLAN_AVAILABILITY.items():
        key = plan_rollout_key(tier)
        if key in configured_rules:
            availability[tier.value] = is_rollout_enabled(key, user, active_settings)
        else:
            availability[tier.value] = default_available

    return availability


def is_plan_available_for_user(
    user: User | None,
    tier: SubscriptionTier,
    settings: Settings | None = None,
) -> bool:
    """Return whether a plan is available for the current user."""
    return get_available_plans(user, settings).get(tier.value, False)


def get_user_capabilities(
    user: User | None,
    settings: Settings | None = None,
) -> dict[str, bool]:
    """Return capability availability for the current user."""
    active_settings = settings or get_settings()
    configured_rules = _get_rollout_rules(active_settings)
    tier = _get_user_tier(user)
    base_capabilities = _BASE_TIER_CAPABILITIES[tier]
    capabilities = {feature: feature in base_capabilities for feature in FEATURE_NAMES}

    for feature in FEATURE_NAMES:
        key = capability_rollout_key(feature)
        if key in configured_rules:
            capabilities[feature] = is_rollout_enabled(key, user, active_settings)

    return capabilities


def is_capability_enabled_for_user(
    user: User | None,
    feature: Feature,
    settings: Settings | None = None,
) -> bool:
    """Return whether a capability is enabled for the current user."""
    return get_user_capabilities(user, settings).get(feature, False)
