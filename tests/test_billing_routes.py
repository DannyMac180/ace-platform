"""Tests for billing API routes.

These tests verify:
1. Route registration
2. Authentication requirements
3. Response schema validation
4. Subscription and billing functionality
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ace_platform.api.routes.billing import (
    PortalResponse,
    SubscribeRequest,
    SubscribeResponse,
    SubscriptionResponse,
    TierLimitsResponse,
    UsageResponse,
)
from ace_platform.core.limits import SubscriptionTier


class TestBillingSchemas:
    """Tests for Pydantic schemas."""

    def test_tier_limits_response(self):
        """Test tier limits response schema."""
        response = TierLimitsResponse(
            monthly_requests=100,
            monthly_tokens=100_000,
            monthly_cost_usd=Decimal("1.00"),
            max_playbooks=3,
            max_evolutions_per_day=5,
            can_use_premium_models=False,
            can_export_data=False,
            priority_support=False,
        )
        assert response.monthly_requests == 100
        assert response.monthly_tokens == 100_000
        assert response.can_use_premium_models is False

    def test_tier_limits_response_unlimited(self):
        """Test tier limits response with unlimited values."""
        response = TierLimitsResponse(
            monthly_requests=None,
            monthly_tokens=None,
            monthly_cost_usd=None,
            max_playbooks=None,
            max_evolutions_per_day=None,
            can_use_premium_models=True,
            can_export_data=True,
            priority_support=True,
        )
        assert response.monthly_requests is None
        assert response.monthly_tokens is None
        assert response.can_use_premium_models is True

    def test_subscription_response(self):
        """Test subscription response schema."""
        now = datetime.now(UTC)
        response = SubscriptionResponse(
            tier=SubscriptionTier.STARTER,
            status="active",
            current_period_start=now,
            current_period_end=now,
            limits=TierLimitsResponse(
                monthly_requests=1000,
                monthly_tokens=1_000_000,
                monthly_cost_usd=Decimal("10.00"),
                max_playbooks=10,
                max_evolutions_per_day=20,
                can_use_premium_models=True,
                can_export_data=True,
                priority_support=False,
            ),
            stripe_customer_id="cus_test123",
            stripe_subscription_id="sub_test123",
        )
        assert response.tier == SubscriptionTier.STARTER
        assert response.status == "active"
        assert response.stripe_customer_id == "cus_test123"

    def test_subscription_response_no_stripe(self):
        """Test subscription response without Stripe IDs."""
        now = datetime.now(UTC)
        response = SubscriptionResponse(
            tier=SubscriptionTier.FREE,
            status="active",
            current_period_start=now,
            current_period_end=now,
            limits=TierLimitsResponse(
                monthly_requests=100,
                monthly_tokens=100_000,
                monthly_cost_usd=Decimal("1.00"),
                max_playbooks=3,
                max_evolutions_per_day=5,
                can_use_premium_models=False,
                can_export_data=False,
                priority_support=False,
            ),
        )
        assert response.tier == SubscriptionTier.FREE
        assert response.stripe_customer_id is None
        assert response.stripe_subscription_id is None

    def test_usage_response(self):
        """Test usage response schema."""
        now = datetime.now(UTC)
        response = UsageResponse(
            period_start=now,
            period_end=now,
            requests_used=50,
            requests_limit=100,
            requests_remaining=50,
            tokens_used=50000,
            tokens_limit=100_000,
            tokens_remaining=50000,
            cost_usd=Decimal("0.50"),
            cost_limit_usd=Decimal("1.00"),
            cost_remaining_usd=Decimal("0.50"),
            is_within_limits=True,
            limit_exceeded=None,
        )
        assert response.requests_used == 50
        assert response.is_within_limits is True
        assert response.limit_exceeded is None

    def test_usage_response_over_limit(self):
        """Test usage response when over limit."""
        now = datetime.now(UTC)
        response = UsageResponse(
            period_start=now,
            period_end=now,
            requests_used=150,
            requests_limit=100,
            requests_remaining=0,
            tokens_used=50000,
            tokens_limit=100_000,
            tokens_remaining=50000,
            cost_usd=Decimal("0.50"),
            cost_limit_usd=Decimal("1.00"),
            cost_remaining_usd=Decimal("0.50"),
            is_within_limits=False,
            limit_exceeded="monthly_requests",
        )
        assert response.is_within_limits is False
        assert response.limit_exceeded == "monthly_requests"

    def test_subscribe_request(self):
        """Test subscribe request schema."""
        request = SubscribeRequest(
            tier=SubscriptionTier.STARTER,
            payment_method_id="pm_test123",
        )
        assert request.tier == SubscriptionTier.STARTER
        assert request.payment_method_id == "pm_test123"

    def test_subscribe_request_free_tier(self):
        """Test subscribe request for free tier (no payment method)."""
        request = SubscribeRequest(tier=SubscriptionTier.FREE)
        assert request.tier == SubscriptionTier.FREE
        assert request.payment_method_id is None

    def test_subscribe_response_success(self):
        """Test subscribe response for successful subscription."""
        now = datetime.now(UTC)
        response = SubscribeResponse(
            success=True,
            message="You are now on the Free plan",
            subscription=SubscriptionResponse(
                tier=SubscriptionTier.FREE,
                status="active",
                current_period_start=now,
                current_period_end=now,
                limits=TierLimitsResponse(
                    monthly_requests=100,
                    monthly_tokens=100_000,
                    monthly_cost_usd=Decimal("1.00"),
                    max_playbooks=3,
                    max_evolutions_per_day=5,
                    can_use_premium_models=False,
                    can_export_data=False,
                    priority_support=False,
                ),
            ),
        )
        assert response.success is True
        assert response.subscription is not None
        assert response.checkout_url is None

    def test_subscribe_response_checkout_required(self):
        """Test subscribe response requiring checkout."""
        response = SubscribeResponse(
            success=False,
            message="Stripe integration required",
            subscription=None,
            checkout_url=None,
        )
        assert response.success is False
        assert response.subscription is None

    def test_portal_response(self):
        """Test portal response schema."""
        response = PortalResponse(url="https://billing.stripe.com/session/123")
        assert response.url == "https://billing.stripe.com/session/123"


class TestBillingRoutesIntegration:
    """Integration tests for billing routes."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_billing_routes_registered(self, app):
        """Test that billing routes are registered."""
        routes = [route.path for route in app.routes]
        assert "/billing/subscription" in routes
        assert "/billing/usage" in routes
        assert "/billing/subscribe" in routes
        assert "/billing/portal" in routes

    def test_subscription_requires_auth(self, client):
        """Test that subscription endpoint requires authentication."""
        response = client.get("/billing/subscription")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_usage_requires_auth(self, client):
        """Test that usage endpoint requires authentication."""
        response = client.get("/billing/usage")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_subscribe_requires_auth(self, client):
        """Test that subscribe endpoint requires authentication."""
        response = client.post(
            "/billing/subscribe",
            json={"tier": "starter"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_portal_requires_auth(self, client):
        """Test that portal endpoint requires authentication."""
        response = client.post("/billing/portal")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_subscription_with_invalid_token(self, client):
        """Test subscription with invalid token."""
        response = client.get(
            "/billing/subscription",
            headers={"Authorization": "Bearer invalid.token"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_subscribe_with_invalid_token(self, client):
        """Test subscribe with invalid token."""
        response = client.post(
            "/billing/subscribe",
            headers={"Authorization": "Bearer invalid.token"},
            json={"tier": "free"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestBillingRouteValidation:
    """Tests for request validation."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_subscribe_invalid_tier(self, client):
        """Test subscribe with invalid tier value."""
        response = client.post(
            "/billing/subscribe",
            json={"tier": "invalid_tier"},
        )
        # Will fail auth first, but if it had auth it would fail validation
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_subscribe_valid_tiers(self, client):
        """Test subscribe accepts valid tier values."""
        # Just validate the tiers are correct values
        valid_tiers = ["free", "starter", "professional", "enterprise"]
        for tier in valid_tiers:
            response = client.post(
                "/billing/subscribe",
                json={"tier": tier},
            )
            # Should fail auth, not validation
            assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestSubscriptionTierHelpers:
    """Tests for subscription tier helper functions."""

    def test_get_user_tier_free(self):
        """Test user without Stripe ID gets free tier."""
        from ace_platform.api.routes.billing import _get_user_tier

        user = MagicMock()
        user.stripe_customer_id = None

        tier = _get_user_tier(user)
        assert tier == SubscriptionTier.FREE

    def test_get_user_tier_starter_with_stripe(self):
        """Test user with Stripe ID gets starter tier."""
        from ace_platform.api.routes.billing import _get_user_tier

        user = MagicMock()
        user.stripe_customer_id = "cus_test123"

        tier = _get_user_tier(user)
        assert tier == SubscriptionTier.STARTER

    def test_get_current_period_end(self):
        """Test billing period end calculation."""
        from ace_platform.api.routes.billing import _get_current_period_end

        period_end = _get_current_period_end()

        # Should be first of next month
        assert period_end.day == 1
        assert period_end.hour == 0
        assert period_end.minute == 0
        assert period_end.second == 0
        assert period_end.tzinfo == UTC

        # Should be after current time
        now = datetime.now(UTC)
        assert period_end > now or (period_end.month == now.month and period_end.day == 1)
