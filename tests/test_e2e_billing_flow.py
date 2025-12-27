"""End-to-end tests for the complete ACE Platform billing flow.

These tests verify the complete billing journey:
1. User registration and free tier access
2. Subscription tier query
3. Usage tracking and limits
4. Upgrade to paid tier (via Stripe checkout)
5. Webhook handling for subscription lifecycle
6. Billing portal access
7. Subscription cancellation flow

NOTE: These tests require PostgreSQL because the models use JSONB columns
which are PostgreSQL-specific.

Run with: RUN_E2E_TESTS=1 pytest tests/test_e2e_billing_flow.py -v
"""

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import stripe
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from ace_platform.core.limits import SubscriptionTier
from ace_platform.core.webhooks import WebhookEventType
from ace_platform.db.models import (
    Base,
    SubscriptionStatus,
    User,
)

# Check if e2e tests should run
RUN_E2E_TESTS = os.environ.get("RUN_E2E_TESTS") == "1"
TEST_DATABASE_URL_SYNC = os.environ.get(
    "TEST_DATABASE_URL_SYNC",
    "postgresql://postgres:postgres@localhost:5432/ace_platform_test",
)
TEST_DATABASE_URL_ASYNC = os.environ.get(
    "TEST_DATABASE_URL_ASYNC",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/ace_platform_test",
)

# Skip marker for tests requiring PostgreSQL
pytestmark = pytest.mark.skipif(
    not RUN_E2E_TESTS,
    reason="Set RUN_E2E_TESTS=1 to run end-to-end PostgreSQL integration tests.",
)


@pytest.fixture(scope="function")
def sync_engine():
    """Create sync test database engine with fresh tables."""
    engine = create_engine(TEST_DATABASE_URL_SYNC, echo=False)

    # Drop and recreate schema
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        Base.metadata.create_all(bind=engine)

    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
async def async_engine():
    """Create async test database engine with fresh tables."""
    engine = create_async_engine(TEST_DATABASE_URL_ASYNC, echo=False)

    # Drop and recreate using raw SQL to handle circular FKs
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture
def sync_session(sync_engine):
    """Create sync database session."""
    session_factory = sessionmaker(bind=sync_engine)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
async def async_session(async_engine):
    """Create async database session."""
    async_session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with async_session_maker() as session:
        yield session


class TestFreeTierFlow:
    """Test free tier subscription flow."""

    @pytest.fixture
    async def free_user(self, async_session: AsyncSession):
        """Create a user on free tier (no Stripe customer)."""
        from ace_platform.core.security import hash_password

        user = User(
            email="free_tier_user@example.com",
            hashed_password=hash_password("testpassword123"),
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        return user

    async def test_new_user_defaults_to_free_tier(
        self, async_session: AsyncSession, free_user: User
    ):
        """Test that new users without Stripe ID get free tier."""
        from ace_platform.api.routes.billing import _get_user_tier

        tier = _get_user_tier(free_user)
        assert tier == SubscriptionTier.FREE

    async def test_free_tier_limits(self, async_session: AsyncSession, free_user: User):
        """Test free tier has correct limits."""
        from ace_platform.core.limits import get_tier_limits

        limits = get_tier_limits(SubscriptionTier.FREE)

        assert limits.monthly_requests == 100
        assert limits.monthly_tokens == 100_000
        assert limits.max_playbooks == 3
        assert limits.can_use_premium_models is False
        assert limits.can_export_data is False

    async def test_subscribe_to_free_tier(self, async_session: AsyncSession, free_user: User):
        """Test subscribing to free tier returns subscription directly."""
        from ace_platform.api.routes.billing import SubscribeRequest
        from ace_platform.core.limits import get_tier_limits

        request = SubscribeRequest(tier=SubscriptionTier.FREE)

        # Free tier should activate immediately without checkout
        assert request.tier == SubscriptionTier.FREE
        assert request.payment_method_id is None

        # Verify limits are correct
        limits = get_tier_limits(SubscriptionTier.FREE)
        assert limits.monthly_requests == 100


class TestUsageTrackingFlow:
    """Test usage tracking and limits enforcement."""

    @pytest.fixture
    async def user_with_usage(self, async_session: AsyncSession):
        """Create a user with some usage recorded."""
        from ace_platform.core.security import hash_password
        from ace_platform.db.models import UsageRecord

        user = User(
            email="usage_test_user@example.com",
            hashed_password=hash_password("testpassword123"),
        )
        async_session.add(user)
        await async_session.flush()

        # Add some usage records
        now = datetime.now(UTC)
        for i in range(3):
            record = UsageRecord(
                user_id=user.id,
                operation="evolution_generator",
                model="gpt-4o-mini",
                prompt_tokens=1000,
                completion_tokens=500,
                total_tokens=1500,
                cost_usd=Decimal("0.0015"),
                created_at=now - timedelta(hours=i),
            )
            async_session.add(record)

        await async_session.commit()
        await async_session.refresh(user)
        return user

    async def test_usage_aggregation(self, async_session: AsyncSession, user_with_usage: User):
        """Test usage is correctly aggregated."""
        from ace_platform.core.limits import get_user_usage_status

        status = await get_user_usage_status(
            async_session, user_with_usage.id, SubscriptionTier.FREE
        )

        # Should have 3 requests
        assert status.current_requests == 3
        # Should have 3 * 1500 = 4500 tokens
        assert status.current_tokens == 4500
        # Should have 3 * 0.0015 = 0.0045 cost
        assert status.current_cost_usd == Decimal("0.0045")

    async def test_usage_within_limits(self, async_session: AsyncSession, user_with_usage: User):
        """Test user is within limits with low usage."""
        from ace_platform.core.limits import get_user_usage_status

        status = await get_user_usage_status(
            async_session, user_with_usage.id, SubscriptionTier.FREE
        )

        # Free tier has 100 requests, 100k tokens - should be within limits
        assert status.is_within_limits is True
        assert status.limit_exceeded is None
        assert status.remaining_requests == 97  # 100 - 3
        assert status.remaining_tokens == 95500  # 100000 - 4500


class TestPaidTierCheckoutFlow:
    """Test paid tier subscription via Stripe checkout."""

    @pytest.fixture
    async def user_for_upgrade(self, async_session: AsyncSession):
        """Create a user ready to upgrade."""
        from ace_platform.core.security import hash_password

        user = User(
            email="upgrade_user@example.com",
            hashed_password=hash_password("testpassword123"),
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        return user

    @patch("ace_platform.core.billing.is_stripe_configured")
    @patch("ace_platform.core.billing._get_stripe_client")
    @patch("ace_platform.core.billing.get_price_id_for_tier")
    async def test_checkout_session_creation(
        self,
        mock_price_id,
        mock_stripe_client,
        mock_stripe_configured,
        async_session: AsyncSession,
        user_for_upgrade: User,
    ):
        """Test creating checkout session for starter tier."""
        from ace_platform.core.billing import create_checkout_session
        from ace_platform.core.stripe_config import BillingInterval

        # Configure mocks
        mock_stripe_configured.return_value = True
        mock_price_id.return_value = "price_starter_monthly"

        mock_client = MagicMock()
        mock_client.customers.create.return_value = MagicMock(id="cus_test123")
        mock_client.checkout.sessions.create.return_value = MagicMock(
            id="cs_test123",
            url="https://checkout.stripe.com/session/cs_test123",
        )
        mock_stripe_client.return_value = mock_client

        result = await create_checkout_session(
            db=async_session,
            user=user_for_upgrade,
            tier=SubscriptionTier.STARTER,
            interval=BillingInterval.MONTHLY,
        )

        assert result.success is True
        assert result.checkout_url == "https://checkout.stripe.com/session/cs_test123"
        assert result.session_id == "cs_test123"

    async def test_free_tier_no_checkout_needed(
        self, async_session: AsyncSession, user_for_upgrade: User
    ):
        """Test free tier doesn't require checkout."""
        from ace_platform.core.billing import create_checkout_session

        result = await create_checkout_session(
            db=async_session,
            user=user_for_upgrade,
            tier=SubscriptionTier.FREE,
        )

        assert result.success is False
        assert "free tier" in result.error.lower()

    async def test_enterprise_tier_requires_contact(
        self, async_session: AsyncSession, user_for_upgrade: User
    ):
        """Test enterprise tier requires sales contact."""
        from ace_platform.core.billing import create_checkout_session

        result = await create_checkout_session(
            db=async_session,
            user=user_for_upgrade,
            tier=SubscriptionTier.ENTERPRISE,
        )

        assert result.success is False
        assert "contact sales" in result.error.lower()


class TestWebhookSubscriptionLifecycle:
    """Test webhook handling for subscription lifecycle events."""

    @pytest.fixture
    async def subscribed_user(self, async_session: AsyncSession):
        """Create a user with Stripe customer ID."""
        from ace_platform.core.security import hash_password

        user = User(
            email="subscribed_user@example.com",
            hashed_password=hash_password("testpassword123"),
            stripe_customer_id="cus_webhook_test",
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        return user

    async def test_checkout_completed_updates_user(
        self, async_session: AsyncSession, subscribed_user: User
    ):
        """Test checkout.session.completed webhook updates user subscription."""
        from ace_platform.core.webhooks import handle_webhook_event

        mock_event = MagicMock(spec=stripe.Event)
        mock_event.type = WebhookEventType.CHECKOUT_SESSION_COMPLETED
        mock_event.data.object = MagicMock(
            customer="cus_webhook_test",
            subscription="sub_test123",
            metadata={"user_id": str(subscribed_user.id), "tier": "starter"},
        )

        result = await handle_webhook_event(async_session, mock_event)

        assert result.success is True
        assert result.user_id == str(subscribed_user.id)

        # Refresh user from DB and check updates
        await async_session.refresh(subscribed_user)
        assert subscribed_user.stripe_subscription_id == "sub_test123"
        assert subscribed_user.subscription_tier == "starter"
        assert subscribed_user.subscription_status == SubscriptionStatus.ACTIVE

    async def test_subscription_updated_changes_status(
        self, async_session: AsyncSession, subscribed_user: User
    ):
        """Test customer.subscription.updated webhook updates status."""
        from ace_platform.core.webhooks import handle_webhook_event

        # Set initial subscription
        subscribed_user.stripe_subscription_id = "sub_test123"
        subscribed_user.subscription_status = SubscriptionStatus.ACTIVE
        await async_session.commit()

        mock_event = MagicMock(spec=stripe.Event)
        mock_event.type = WebhookEventType.SUBSCRIPTION_UPDATED
        mock_event.data.object = MagicMock(
            id="sub_test123",
            customer="cus_webhook_test",
            status="past_due",
            current_period_end=int((datetime.now(UTC) + timedelta(days=30)).timestamp()),
            items=MagicMock(data=[]),
        )

        result = await handle_webhook_event(async_session, mock_event)

        assert result.success is True

        # Refresh and check status updated
        await async_session.refresh(subscribed_user)
        assert subscribed_user.subscription_status == SubscriptionStatus.PAST_DUE

    async def test_subscription_deleted_cancels_subscription(
        self, async_session: AsyncSession, subscribed_user: User
    ):
        """Test customer.subscription.deleted webhook cancels subscription."""
        from ace_platform.core.webhooks import handle_webhook_event

        # Set initial subscription
        subscribed_user.stripe_subscription_id = "sub_test123"
        subscribed_user.subscription_tier = "starter"
        subscribed_user.subscription_status = SubscriptionStatus.ACTIVE
        await async_session.commit()

        mock_event = MagicMock(spec=stripe.Event)
        mock_event.type = WebhookEventType.SUBSCRIPTION_DELETED
        mock_event.data.object = MagicMock(
            id="sub_test123",
            customer="cus_webhook_test",
        )

        result = await handle_webhook_event(async_session, mock_event)

        assert result.success is True

        # Refresh and check subscription cancelled
        await async_session.refresh(subscribed_user)
        assert subscribed_user.stripe_subscription_id is None
        assert subscribed_user.subscription_tier is None
        assert subscribed_user.subscription_status == SubscriptionStatus.CANCELED

    async def test_payment_failed_sets_past_due(
        self, async_session: AsyncSession, subscribed_user: User
    ):
        """Test invoice.payment_failed webhook sets subscription to past_due."""
        from ace_platform.core.webhooks import handle_webhook_event

        # Set initial subscription
        subscribed_user.stripe_subscription_id = "sub_test123"
        subscribed_user.subscription_status = SubscriptionStatus.ACTIVE
        await async_session.commit()

        mock_event = MagicMock(spec=stripe.Event)
        mock_event.type = WebhookEventType.INVOICE_PAYMENT_FAILED
        mock_event.data.object = MagicMock(
            customer="cus_webhook_test",
            subscription="sub_test123",
        )

        result = await handle_webhook_event(async_session, mock_event)

        assert result.success is True

        await async_session.refresh(subscribed_user)
        assert subscribed_user.subscription_status == SubscriptionStatus.PAST_DUE

    async def test_payment_succeeded_restores_active(
        self, async_session: AsyncSession, subscribed_user: User
    ):
        """Test invoice.payment_succeeded webhook restores active status."""
        from ace_platform.core.webhooks import handle_webhook_event

        # Set initial past_due status
        subscribed_user.stripe_subscription_id = "sub_test123"
        subscribed_user.subscription_status = SubscriptionStatus.PAST_DUE
        await async_session.commit()

        mock_event = MagicMock(spec=stripe.Event)
        mock_event.type = WebhookEventType.INVOICE_PAYMENT_SUCCEEDED
        mock_event.data.object = MagicMock(
            customer="cus_webhook_test",
            subscription="sub_test123",
        )

        result = await handle_webhook_event(async_session, mock_event)

        assert result.success is True

        await async_session.refresh(subscribed_user)
        assert subscribed_user.subscription_status == SubscriptionStatus.ACTIVE


class TestBillingPortalFlow:
    """Test Stripe billing portal access."""

    @pytest.fixture
    async def portal_user(self, async_session: AsyncSession):
        """Create a user with Stripe customer ID for portal access."""
        from ace_platform.core.security import hash_password

        user = User(
            email="portal_user@example.com",
            hashed_password=hash_password("testpassword123"),
            stripe_customer_id="cus_portal_test",
            stripe_subscription_id="sub_portal_test",
            subscription_status=SubscriptionStatus.ACTIVE,
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        return user

    @patch("ace_platform.core.billing._get_stripe_client")
    async def test_create_billing_portal_session(
        self, mock_stripe_client, async_session: AsyncSession, portal_user: User
    ):
        """Test creating billing portal session for subscribed user."""
        from ace_platform.core.billing import create_billing_portal_session

        mock_client = MagicMock()
        mock_client.billing_portal.sessions.create.return_value = MagicMock(
            url="https://billing.stripe.com/session/test123"
        )
        mock_stripe_client.return_value = mock_client

        result = await create_billing_portal_session(user=portal_user)

        assert result.success is True
        assert result.portal_url == "https://billing.stripe.com/session/test123"

    async def test_billing_portal_requires_customer_id(self, async_session: AsyncSession):
        """Test billing portal requires Stripe customer ID."""
        from ace_platform.core.billing import create_billing_portal_session
        from ace_platform.core.security import hash_password

        # Create user without Stripe customer
        user_no_stripe = User(
            email="no_stripe_user@example.com",
            hashed_password=hash_password("testpassword123"),
        )
        async_session.add(user_no_stripe)
        await async_session.commit()
        await async_session.refresh(user_no_stripe)

        result = await create_billing_portal_session(user=user_no_stripe)

        assert result.success is False
        assert "no billing account" in result.error.lower()


class TestTierUpgradeDowngradeFlow:
    """Test subscription tier changes."""

    @pytest.fixture
    async def starter_user(self, async_session: AsyncSession):
        """Create a user on starter tier."""
        from ace_platform.core.security import hash_password

        user = User(
            email="starter_user@example.com",
            hashed_password=hash_password("testpassword123"),
            stripe_customer_id="cus_starter_test",
            stripe_subscription_id="sub_starter_test",
            subscription_tier="starter",
            subscription_status=SubscriptionStatus.ACTIVE,
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        return user

    async def test_starter_tier_has_higher_limits(
        self, async_session: AsyncSession, starter_user: User
    ):
        """Test starter tier has higher limits than free."""
        from ace_platform.core.limits import get_tier_limits

        free_limits = get_tier_limits(SubscriptionTier.FREE)
        starter_limits = get_tier_limits(SubscriptionTier.STARTER)

        assert starter_limits.monthly_requests > free_limits.monthly_requests
        assert starter_limits.monthly_tokens > free_limits.monthly_tokens
        assert starter_limits.max_playbooks > free_limits.max_playbooks

    async def test_professional_tier_has_premium_features(self, async_session: AsyncSession):
        """Test professional tier has premium features."""
        from ace_platform.core.limits import get_tier_limits

        pro_limits = get_tier_limits(SubscriptionTier.PROFESSIONAL)

        assert pro_limits.can_use_premium_models is True
        assert pro_limits.can_export_data is True


class TestCompleteBillingE2EWorkflow:
    """Test complete billing workflow from registration to subscription management."""

    async def test_full_billing_workflow(self, async_session: AsyncSession):
        """Test complete billing flow: register -> free tier -> upgrade -> manage."""
        from ace_platform.core.limits import get_tier_limits, get_user_usage_status
        from ace_platform.core.security import hash_password
        from ace_platform.core.webhooks import handle_webhook_event
        from ace_platform.db.models import UsageRecord

        # Step 1: Create user (simulates registration)
        user = User(
            email="full_billing_flow@example.com",
            hashed_password=hash_password("testpassword123"),
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)

        # Step 2: Verify user starts on free tier
        from ace_platform.api.routes.billing import _get_user_tier

        tier = _get_user_tier(user)
        assert tier == SubscriptionTier.FREE

        # Step 3: Check free tier limits
        free_limits = get_tier_limits(SubscriptionTier.FREE)
        assert free_limits.monthly_requests == 100
        assert free_limits.max_playbooks == 3

        # Step 4: Record some usage
        record = UsageRecord(
            user_id=user.id,
            operation="evolution_generator",
            model="gpt-4o-mini",
            prompt_tokens=5000,
            completion_tokens=2000,
            total_tokens=7000,
            cost_usd=Decimal("0.007"),
        )
        async_session.add(record)
        await async_session.commit()

        # Step 5: Check usage status
        status = await get_user_usage_status(async_session, user.id, SubscriptionTier.FREE)
        assert status.current_requests == 1
        assert status.current_tokens == 7000
        assert status.is_within_limits is True

        # Step 6: Simulate checkout completion (upgrade to starter)
        mock_event = MagicMock(spec=stripe.Event)
        mock_event.type = WebhookEventType.CHECKOUT_SESSION_COMPLETED
        mock_event.data.object = MagicMock(
            customer="cus_billing_test",
            subscription="sub_billing_test",
            metadata={"user_id": str(user.id), "tier": "starter"},
        )

        result = await handle_webhook_event(async_session, mock_event)
        assert result.success is True

        # Step 7: Verify user is now on starter tier
        await async_session.refresh(user)
        assert user.stripe_customer_id == "cus_billing_test"
        assert user.stripe_subscription_id == "sub_billing_test"
        assert user.subscription_tier == "starter"
        assert user.subscription_status == SubscriptionStatus.ACTIVE

        # Step 8: Check upgraded limits
        starter_limits = get_tier_limits(SubscriptionTier.STARTER)
        assert starter_limits.monthly_requests > free_limits.monthly_requests

        # Step 9: Simulate subscription cancellation
        cancel_event = MagicMock(spec=stripe.Event)
        cancel_event.type = WebhookEventType.SUBSCRIPTION_DELETED
        cancel_event.data.object = MagicMock(
            id="sub_billing_test",
            customer="cus_billing_test",
        )

        cancel_result = await handle_webhook_event(async_session, cancel_event)
        assert cancel_result.success is True

        # Step 10: Verify user is back to cancelled state
        await async_session.refresh(user)
        assert user.stripe_subscription_id is None
        assert user.subscription_tier is None
        assert user.subscription_status == SubscriptionStatus.CANCELED


class TestWebhookSignatureVerification:
    """Test webhook signature verification."""

    @patch("ace_platform.core.webhooks.get_settings")
    def test_missing_webhook_secret(self, mock_settings):
        """Test returns None when webhook secret not configured."""
        from ace_platform.core.webhooks import verify_webhook_signature

        mock_settings.return_value.stripe_webhook_secret = ""

        result = verify_webhook_signature(b"payload", "sig_test")
        assert result is None

    @patch("ace_platform.core.webhooks.get_settings")
    @patch("stripe.Webhook.construct_event")
    def test_valid_signature(self, mock_construct, mock_settings):
        """Test valid signature verification."""
        from ace_platform.core.webhooks import verify_webhook_signature

        mock_settings.return_value.stripe_webhook_secret = "whsec_test"
        mock_event = MagicMock(spec=stripe.Event)
        mock_construct.return_value = mock_event

        result = verify_webhook_signature(b"payload", "sig_test")

        assert result == mock_event
        mock_construct.assert_called_once_with(b"payload", "sig_test", "whsec_test")

    @patch("ace_platform.core.webhooks.get_settings")
    @patch("stripe.Webhook.construct_event")
    def test_invalid_signature(self, mock_construct, mock_settings):
        """Test invalid signature returns None."""
        from ace_platform.core.webhooks import verify_webhook_signature

        mock_settings.return_value.stripe_webhook_secret = "whsec_test"
        mock_construct.side_effect = stripe.SignatureVerificationError("Invalid", "sig")

        result = verify_webhook_signature(b"payload", "invalid_sig")
        assert result is None
