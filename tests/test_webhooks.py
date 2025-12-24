"""Tests for Stripe webhook handler.

These tests verify:
1. Webhook signature verification
2. Event handling for subscription lifecycle
3. User subscription status updates
4. Error handling
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import stripe

from ace_platform.core.webhooks import (
    WebhookEventType,
    WebhookResult,
    _get_subscription_tier,
    _get_user_by_customer_id,
    _map_stripe_status,
    handle_webhook_event,
    verify_webhook_signature,
)
from ace_platform.db.models import SubscriptionStatus


class TestWebhookResult:
    """Tests for WebhookResult dataclass."""

    def test_success_result(self):
        """Test successful webhook result."""
        result = WebhookResult(
            success=True,
            message="Event processed",
            event_type="checkout.session.completed",
            user_id="user-123",
        )
        assert result.success is True
        assert result.message == "Event processed"

    def test_error_result(self):
        """Test error webhook result."""
        result = WebhookResult(
            success=False,
            message="User not found",
            event_type="customer.subscription.created",
        )
        assert result.success is False
        assert result.user_id is None


class TestWebhookEventType:
    """Tests for WebhookEventType enum."""

    def test_event_types(self):
        """Test webhook event type values."""
        assert WebhookEventType.CHECKOUT_SESSION_COMPLETED == "checkout.session.completed"
        assert WebhookEventType.SUBSCRIPTION_CREATED == "customer.subscription.created"
        assert WebhookEventType.SUBSCRIPTION_UPDATED == "customer.subscription.updated"
        assert WebhookEventType.SUBSCRIPTION_DELETED == "customer.subscription.deleted"
        assert WebhookEventType.INVOICE_PAYMENT_FAILED == "invoice.payment_failed"
        assert WebhookEventType.INVOICE_PAYMENT_SUCCEEDED == "invoice.payment_succeeded"


class TestMapStripeStatus:
    """Tests for _map_stripe_status function."""

    def test_active_status(self):
        """Test active status mapping."""
        assert _map_stripe_status("active") == SubscriptionStatus.ACTIVE

    def test_past_due_status(self):
        """Test past_due status mapping."""
        assert _map_stripe_status("past_due") == SubscriptionStatus.PAST_DUE

    def test_canceled_status(self):
        """Test canceled status mapping."""
        assert _map_stripe_status("canceled") == SubscriptionStatus.CANCELED

    def test_unpaid_status(self):
        """Test unpaid status mapping."""
        assert _map_stripe_status("unpaid") == SubscriptionStatus.UNPAID

    def test_trialing_status(self):
        """Test trialing maps to active."""
        assert _map_stripe_status("trialing") == SubscriptionStatus.ACTIVE

    def test_unknown_status(self):
        """Test unknown status maps to NONE."""
        assert _map_stripe_status("unknown") == SubscriptionStatus.NONE


class TestVerifyWebhookSignature:
    """Tests for verify_webhook_signature function."""

    @patch("ace_platform.core.webhooks.get_settings")
    def test_missing_webhook_secret(self, mock_settings):
        """Test returns None when webhook secret not configured."""
        mock_settings.return_value.stripe_webhook_secret = ""

        result = verify_webhook_signature(b"payload", "sig_test")
        assert result is None

    @patch("ace_platform.core.webhooks.get_settings")
    @patch("stripe.Webhook.construct_event")
    def test_successful_verification(self, mock_construct, mock_settings):
        """Test successful signature verification."""
        mock_settings.return_value.stripe_webhook_secret = "whsec_test"
        mock_event = MagicMock(spec=stripe.Event)
        mock_construct.return_value = mock_event

        result = verify_webhook_signature(b"payload", "sig_test")

        assert result == mock_event
        mock_construct.assert_called_once_with(b"payload", "sig_test", "whsec_test")

    @patch("ace_platform.core.webhooks.get_settings")
    @patch("stripe.Webhook.construct_event")
    def test_signature_verification_error(self, mock_construct, mock_settings):
        """Test returns None on signature verification error."""
        mock_settings.return_value.stripe_webhook_secret = "whsec_test"
        mock_construct.side_effect = stripe.SignatureVerificationError("Invalid", "sig")

        result = verify_webhook_signature(b"payload", "sig_test")
        assert result is None

    @patch("ace_platform.core.webhooks.get_settings")
    @patch("stripe.Webhook.construct_event")
    def test_invalid_payload_error(self, mock_construct, mock_settings):
        """Test returns None on invalid payload."""
        mock_settings.return_value.stripe_webhook_secret = "whsec_test"
        mock_construct.side_effect = ValueError("Invalid JSON")

        result = verify_webhook_signature(b"invalid", "sig_test")
        assert result is None


class TestGetUserByCustomerId:
    """Tests for _get_user_by_customer_id function."""

    @pytest.mark.asyncio
    async def test_user_found(self):
        """Test finding user by customer ID."""
        mock_user = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        result = await _get_user_by_customer_id(mock_db, "cus_test123")

        assert result == mock_user

    @pytest.mark.asyncio
    async def test_user_not_found(self):
        """Test user not found returns None."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result

        result = await _get_user_by_customer_id(mock_db, "cus_nonexistent")

        assert result is None


class TestGetSubscriptionTier:
    """Tests for _get_subscription_tier function."""

    @patch("ace_platform.core.webhooks.get_tier_from_price_id")
    def test_tier_from_price_id(self, mock_get_tier):
        """Test extracting tier from subscription."""
        from ace_platform.core.limits import SubscriptionTier

        mock_get_tier.return_value = SubscriptionTier.STARTER

        mock_subscription = MagicMock()
        mock_item = MagicMock()
        mock_item.price.id = "price_test123"
        mock_subscription.items.data = [mock_item]

        result = _get_subscription_tier(mock_subscription)

        assert result == "starter"

    def test_no_items(self):
        """Test returns None when no items."""
        mock_subscription = MagicMock()
        mock_subscription.items = None

        result = _get_subscription_tier(mock_subscription)
        assert result is None


class TestHandleWebhookEvent:
    """Tests for handle_webhook_event function."""

    @pytest.mark.asyncio
    async def test_unhandled_event_type(self):
        """Test unhandled event types are acknowledged."""
        mock_db = AsyncMock()
        mock_event = MagicMock()
        mock_event.type = "unhandled.event.type"

        result = await handle_webhook_event(mock_db, mock_event)

        assert result.success is True
        assert "acknowledged" in result.message.lower()

    @pytest.mark.asyncio
    @patch("ace_platform.core.webhooks._handle_checkout_completed")
    async def test_checkout_completed_event(self, mock_handler):
        """Test checkout.session.completed event routing."""
        mock_handler.return_value = WebhookResult(success=True, message="OK")
        mock_db = AsyncMock()
        mock_event = MagicMock()
        mock_event.type = WebhookEventType.CHECKOUT_SESSION_COMPLETED

        result = await handle_webhook_event(mock_db, mock_event)

        mock_handler.assert_called_once_with(mock_db, mock_event)
        assert result.success is True

    @pytest.mark.asyncio
    @patch("ace_platform.core.webhooks._handle_subscription_created")
    async def test_subscription_created_event(self, mock_handler):
        """Test customer.subscription.created event routing."""
        mock_handler.return_value = WebhookResult(success=True, message="OK")
        mock_db = AsyncMock()
        mock_event = MagicMock()
        mock_event.type = WebhookEventType.SUBSCRIPTION_CREATED

        result = await handle_webhook_event(mock_db, mock_event)

        mock_handler.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    @patch("ace_platform.core.webhooks._handle_subscription_updated")
    async def test_subscription_updated_event(self, mock_handler):
        """Test customer.subscription.updated event routing."""
        mock_handler.return_value = WebhookResult(success=True, message="OK")
        mock_db = AsyncMock()
        mock_event = MagicMock()
        mock_event.type = WebhookEventType.SUBSCRIPTION_UPDATED

        result = await handle_webhook_event(mock_db, mock_event)

        mock_handler.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    @patch("ace_platform.core.webhooks._handle_subscription_deleted")
    async def test_subscription_deleted_event(self, mock_handler):
        """Test customer.subscription.deleted event routing."""
        mock_handler.return_value = WebhookResult(success=True, message="OK")
        mock_db = AsyncMock()
        mock_event = MagicMock()
        mock_event.type = WebhookEventType.SUBSCRIPTION_DELETED

        result = await handle_webhook_event(mock_db, mock_event)

        mock_handler.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    @patch("ace_platform.core.webhooks._handle_payment_failed")
    async def test_payment_failed_event(self, mock_handler):
        """Test invoice.payment_failed event routing."""
        mock_handler.return_value = WebhookResult(success=True, message="OK")
        mock_db = AsyncMock()
        mock_event = MagicMock()
        mock_event.type = WebhookEventType.INVOICE_PAYMENT_FAILED

        result = await handle_webhook_event(mock_db, mock_event)

        mock_handler.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    @patch("ace_platform.core.webhooks._handle_payment_succeeded")
    async def test_payment_succeeded_event(self, mock_handler):
        """Test invoice.payment_succeeded event routing."""
        mock_handler.return_value = WebhookResult(success=True, message="OK")
        mock_db = AsyncMock()
        mock_event = MagicMock()
        mock_event.type = WebhookEventType.INVOICE_PAYMENT_SUCCEEDED

        result = await handle_webhook_event(mock_db, mock_event)

        mock_handler.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    @patch("ace_platform.core.webhooks._handle_checkout_completed")
    async def test_handler_exception(self, mock_handler):
        """Test exception handling in event processing."""
        mock_handler.side_effect = Exception("Database error")
        mock_db = AsyncMock()
        mock_event = MagicMock()
        mock_event.type = WebhookEventType.CHECKOUT_SESSION_COMPLETED

        result = await handle_webhook_event(mock_db, mock_event)

        assert result.success is False
        assert "error" in result.message.lower()


class TestWebhookRouteIntegration:
    """Integration tests for webhook route."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        from fastapi.testclient import TestClient

        return TestClient(app)

    def test_webhook_route_registered(self, app):
        """Test that webhook route is registered."""
        routes = [route.path for route in app.routes]
        assert "/billing/webhook" in routes

    def test_webhook_missing_signature(self, client):
        """Test webhook without signature header."""
        response = client.post(
            "/billing/webhook",
            content=b'{"type": "test"}',
        )
        assert response.status_code == 400
        assert "Stripe-Signature" in response.json()["error"]["message"]

    @patch("ace_platform.core.webhooks.verify_webhook_signature")
    def test_webhook_invalid_signature(self, mock_verify, client):
        """Test webhook with invalid signature."""
        mock_verify.return_value = None

        response = client.post(
            "/billing/webhook",
            content=b'{"type": "test"}',
            headers={"Stripe-Signature": "invalid_sig"},
        )
        assert response.status_code == 400
        assert "Invalid webhook signature" in response.json()["error"]["message"]
