"""Workspace-aware subscription helpers for billing integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.core.limits import SubscriptionTier
from ace_platform.core.stripe_config import BillingInterval, get_product_config
from ace_platform.core.workspaces import (
    bootstrap_workspace_for_user,
    get_default_workspace_for_user,
    get_personal_workspace_for_user,
)
from ace_platform.db.models import (
    User,
    Workspace,
    WorkspaceBillingProvider,
    WorkspaceEntitlement,
    WorkspacePlan,
    WorkspaceSubscription,
    WorkspaceSubscriptionStatus,
)

FREE_PLAN_CODE = "personal-free"

_PLAN_CODES: dict[SubscriptionTier, str] = {
    SubscriptionTier.FREE: FREE_PLAN_CODE,
    SubscriptionTier.STARTER: "personal-starter",
    SubscriptionTier.PRO: "personal-pro",
    SubscriptionTier.ULTRA: "personal-ultra",
    SubscriptionTier.ENTERPRISE: "enterprise",
}

_FREE_FEATURES = (
    "Hosted personal workspace",
    "Cloud sync",
    "Hosted backups",
    "Basic managed inference",
)


@dataclass(frozen=True, slots=True)
class BillingPlanCatalogPrice:
    """One billable price inside the plan catalog."""

    interval: BillingInterval
    price_id: str | None
    unit_amount: int | None
    currency: str = "usd"


@dataclass(frozen=True, slots=True)
class BillingPlanCatalogEntry:
    """One plan catalog entry exposed to billing-aware services."""

    code: str
    workspace_plan: WorkspacePlan
    subscription_tier: SubscriptionTier
    display_name: str
    description: str
    features: tuple[str, ...]
    prices: tuple[BillingPlanCatalogPrice, ...]
    contact_sales: bool = False


def _workspace_plan_for_tier(tier: SubscriptionTier) -> WorkspacePlan:
    if tier == SubscriptionTier.ENTERPRISE:
        return WorkspacePlan.ENTERPRISE
    return WorkspacePlan.PERSONAL


def get_plan_code_for_tier(tier: SubscriptionTier) -> str:
    """Return the canonical catalog code for a billing tier."""

    return _PLAN_CODES[tier]


def get_plan_catalog() -> tuple[BillingPlanCatalogEntry, ...]:
    """Return the current billing plan catalog."""

    catalog = [
        BillingPlanCatalogEntry(
            code=FREE_PLAN_CODE,
            workspace_plan=WorkspacePlan.PERSONAL,
            subscription_tier=SubscriptionTier.FREE,
            display_name="ACE Free",
            description="Internal fallback tier for unbilled hosted accounts.",
            features=_FREE_FEATURES,
            prices=(),
        )
    ]

    for tier in (
        SubscriptionTier.STARTER,
        SubscriptionTier.PRO,
        SubscriptionTier.ULTRA,
        SubscriptionTier.ENTERPRISE,
    ):
        product = get_product_config(tier)
        if product is None:
            continue

        prices: list[BillingPlanCatalogPrice] = []
        if tier != SubscriptionTier.ENTERPRISE:
            prices.append(
                BillingPlanCatalogPrice(
                    interval=BillingInterval.MONTHLY,
                    price_id=product.monthly_price.price_id or None,
                    unit_amount=product.monthly_price.unit_amount,
                    currency=product.monthly_price.currency,
                )
            )
            if product.yearly_price is not None:
                prices.append(
                    BillingPlanCatalogPrice(
                        interval=BillingInterval.YEARLY,
                        price_id=product.yearly_price.price_id or None,
                        unit_amount=product.yearly_price.unit_amount,
                        currency=product.yearly_price.currency,
                    )
                )

        catalog.append(
            BillingPlanCatalogEntry(
                code=get_plan_code_for_tier(tier),
                workspace_plan=_workspace_plan_for_tier(tier),
                subscription_tier=tier,
                display_name=product.name,
                description=product.description,
                features=product.features,
                prices=tuple(prices),
                contact_sales=tier == SubscriptionTier.ENTERPRISE,
            )
        )

    return tuple(catalog)


def get_plan_catalog_entry_for_tier(
    tier: SubscriptionTier,
) -> BillingPlanCatalogEntry:
    """Resolve one catalog entry by subscription tier."""

    for entry in get_plan_catalog():
        if entry.subscription_tier == tier:
            return entry
    raise KeyError(f"Unknown billing tier: {tier.value}")


def get_plan_catalog_entry_for_code(
    code: str | None,
) -> BillingPlanCatalogEntry | None:
    """Resolve one catalog entry by catalog code."""

    if not code:
        return None

    normalized = code.strip().lower()
    for entry in get_plan_catalog():
        if entry.code == normalized:
            return entry
    return None


def get_subscription_tier_for_plan_code(code: str | None) -> SubscriptionTier | None:
    """Resolve a subscription tier from a catalog code."""

    entry = get_plan_catalog_entry_for_code(code)
    if entry is None:
        return None
    return entry.subscription_tier


async def ensure_billing_workspace(
    db: AsyncSession,
    user: User,
) -> Workspace:
    """Return the workspace that should receive billing state updates."""

    workspace = await get_personal_workspace_for_user(db, user.id)
    if workspace is None:
        workspace = await get_default_workspace_for_user(db, user.id)
    if workspace is None:
        workspace, _ = await bootstrap_workspace_for_user(db, user)
        await db.flush()
    return workspace


def _apply_workspace_entitlements(workspace: Workspace, plan: WorkspacePlan) -> None:
    defaults = WorkspaceEntitlement.defaults_for_plan(plan)
    if workspace.entitlements is None:
        workspace.entitlements = WorkspaceEntitlement(
            workspace_id=workspace.id,
            **defaults,
        )
        return

    for field_name, value in defaults.items():
        setattr(workspace.entitlements, field_name, value)


async def sync_workspace_subscription_state(
    db: AsyncSession,
    user: User,
    *,
    status: WorkspaceSubscriptionStatus,
    subscription_tier: SubscriptionTier | None = None,
    plan_code: str | None = None,
    billing_provider: WorkspaceBillingProvider = WorkspaceBillingProvider.STRIPE,
    provider_customer_id: str | None = None,
    provider_subscription_id: str | None = None,
    current_period_end: datetime | None = None,
    trial_ends_at: datetime | None = None,
) -> WorkspaceSubscription:
    """Upsert workspace-level billing state for the user's billing workspace."""

    workspace = await ensure_billing_workspace(db, user)

    plan_entry = get_plan_catalog_entry_for_code(plan_code)
    if plan_entry is None and subscription_tier is not None:
        plan_entry = get_plan_catalog_entry_for_tier(subscription_tier)
    if plan_entry is None and workspace.subscription is not None:
        plan_entry = get_plan_catalog_entry_for_code(workspace.subscription.plan_code)
    if plan_entry is None:
        plan_entry = get_plan_catalog_entry_for_tier(SubscriptionTier.FREE)

    workspace.plan = plan_entry.workspace_plan
    if workspace.plan == WorkspacePlan.PERSONAL:
        workspace.seat_limit = 1
    _apply_workspace_entitlements(workspace, plan_entry.workspace_plan)

    resolved_plan_code = plan_code or plan_entry.code
    if workspace.subscription is None:
        workspace.subscription = WorkspaceSubscription(
            workspace_id=workspace.id,
            billing_provider=billing_provider,
            status=status,
            plan_code=resolved_plan_code,
            provider_customer_id=provider_customer_id,
            provider_subscription_id=provider_subscription_id,
            current_period_end=current_period_end,
            trial_ends_at=trial_ends_at,
        )
    else:
        workspace.subscription.billing_provider = billing_provider
        workspace.subscription.status = status
        workspace.subscription.plan_code = resolved_plan_code
        workspace.subscription.provider_customer_id = provider_customer_id
        workspace.subscription.provider_subscription_id = provider_subscription_id
        workspace.subscription.current_period_end = current_period_end
        workspace.subscription.trial_ends_at = trial_ends_at

    await db.flush()
    return workspace.subscription
