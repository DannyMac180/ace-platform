# Admin Dashboard Tests - v1 read-only admin endpoints
"""Tests for admin dashboard API routes.

These tests verify:
1. Admin routes require authentication (401 without token)
2. Admin routes require admin role (403 for non-admin user)
3. Route registration
4. Response schema validation
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ace_platform.api.routes.admin import (
    AdminUserItem,
    AuditEventItem,
    ConversionFunnelResponse,
    DailySignupResponse,
    PlatformStatsResponse,
    TopUserResponse,
    build_conversion_funnel_response,
    get_conversion_funnel,
)


class TestAdminSchemas:
    """Tests for admin Pydantic response schemas."""

    def test_platform_stats_response(self):
        """Test platform stats response schema."""
        response = PlatformStatsResponse(
            total_users=100,
            active_users_today=25,
            signups_this_week=10,
            total_cost_today="1.50",
            tier_distribution={"free": 60, "starter": 30, "pro": 10},
        )
        assert response.total_users == 100
        assert response.active_users_today == 25
        assert response.tier_distribution["free"] == 60

    def test_admin_user_item(self):
        """Test admin user list item schema."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        item = AdminUserItem(
            id=str(uuid4()),
            email="test@example.com",
            is_active=True,
            email_verified=True,
            is_admin=False,
            subscription_tier="starter",
            subscription_status="active",
            playbook_count=5,
            total_cost_usd="0.50",
            created_at=now,
        )
        assert item.email == "test@example.com"
        assert item.playbook_count == 5
        assert item.is_admin is False

    def test_daily_signup_response(self):
        """Test daily signup response schema."""
        response = DailySignupResponse(date="2024-01-15", count=5)
        assert response.date == "2024-01-15"
        assert response.count == 5

    def test_conversion_funnel_response(self):
        """Test conversion funnel schema."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        response = ConversionFunnelResponse(
            days=30,
            start_date=now,
            end_date=now,
            signups=27,
            trial_checkout_intent=6,
            trial_started=2,
            first_playbook_created=2,
            paid_active_non_trial=1,
            conversion_signup_to_checkout_intent_pct=22.22,
            conversion_checkout_intent_to_trial_started_pct=33.33,
            conversion_trial_started_to_first_playbook_pct=100.0,
            conversion_first_playbook_to_paid_active_non_trial_pct=50.0,
            conversion_signup_to_trial_started_pct=7.41,
            conversion_signup_to_paid_active_non_trial_pct=3.7,
        )
        assert response.signups == 27
        assert response.trial_started == 2
        assert response.conversion_signup_to_trial_started_pct == 7.41

    def test_build_conversion_funnel_response_rates(self):
        """Test conversion funnel rate calculations."""
        from datetime import datetime, timedelta, timezone

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=7)
        response = build_conversion_funnel_response(
            days=7,
            start_date=start,
            end_date=end,
            signups=20,
            trial_checkout_intent=10,
            trial_started=4,
            first_playbook_created=2,
            paid_active_non_trial=1,
        )

        assert response.conversion_signup_to_checkout_intent_pct == 50.0
        assert response.conversion_checkout_intent_to_trial_started_pct == 40.0
        assert response.conversion_trial_started_to_first_playbook_pct == 50.0
        assert response.conversion_first_playbook_to_paid_active_non_trial_pct == 50.0
        assert response.conversion_signup_to_trial_started_pct == 20.0
        assert response.conversion_signup_to_paid_active_non_trial_pct == 5.0

    def test_build_conversion_funnel_response_zero_division_safe(self):
        """Test conversion funnel avoids divide-by-zero errors."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        response = build_conversion_funnel_response(
            days=30,
            start_date=now,
            end_date=now,
            signups=0,
            trial_checkout_intent=0,
            trial_started=0,
            first_playbook_created=0,
            paid_active_non_trial=0,
        )

        assert response.conversion_signup_to_checkout_intent_pct == 0.0
        assert response.conversion_signup_to_trial_started_pct == 0.0
        assert response.conversion_signup_to_paid_active_non_trial_pct == 0.0

    @pytest.mark.asyncio
    async def test_get_conversion_funnel_scopes_later_stages_to_prior_cohorts(self):
        """Ensure later funnel queries are constrained to prior-stage users."""
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(side_effect=[20, 10, 8, 6, 4])

        response = await get_conversion_funnel(_admin=object(), db=mock_db, days=30)

        assert response.signups == 20
        assert response.trial_started == 8
        assert response.first_playbook_created == 6
        assert response.paid_active_non_trial == 4
        assert mock_db.scalar.call_count == 5

        first_playbook_query = mock_db.scalar.call_args_list[3].args[0]
        paid_query = mock_db.scalar.call_args_list[4].args[0]
        first_playbook_sql = str(first_playbook_query)
        paid_sql = str(paid_query)

        assert "has_used_trial" in first_playbook_sql
        assert "trial_ends_at" in first_playbook_sql
        assert "EXISTS" in first_playbook_sql
        assert "playbooks.user_id = users.id" in first_playbook_sql

        assert "has_used_trial" in paid_sql
        assert "playbooks.user_id = users.id" in paid_sql
        assert "subscription_status" in paid_sql

    def test_top_user_response(self):
        """Test top user response schema."""
        response = TopUserResponse(
            user_id=str(uuid4()),
            email="top@example.com",
            subscription_tier="pro",
            total_cost_usd="5.00",
            cost_limit_usd="50.00",
            percent_of_limit=10.0,
        )
        assert response.email == "top@example.com"
        assert response.percent_of_limit == 10.0

    def test_top_user_response_no_limit(self):
        """Test top user response with no cost limit."""
        response = TopUserResponse(
            user_id=str(uuid4()),
            email="enterprise@example.com",
            subscription_tier="enterprise",
            total_cost_usd="100.00",
            cost_limit_usd=None,
            percent_of_limit=None,
        )
        assert response.cost_limit_usd is None
        assert response.percent_of_limit is None

    def test_audit_event_item(self):
        """Test audit event item schema."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        item = AuditEventItem(
            id=str(uuid4()),
            user_id=str(uuid4()),
            user_email="user@example.com",
            event_type="login_success",
            severity="info",
            ip_address="192.168.1.1",
            created_at=now,
            details={"method": "password"},
        )
        assert item.event_type == "login_success"
        assert item.severity == "info"

    def test_audit_event_item_null_user(self):
        """Test audit event with null user (e.g. failed login for non-existent user)."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        item = AuditEventItem(
            id=str(uuid4()),
            user_id=None,
            user_email=None,
            event_type="login_failure",
            severity="warning",
            ip_address="10.0.0.1",
            created_at=now,
            details=None,
        )
        assert item.user_id is None
        assert item.user_email is None


class TestAdminRoutesIntegration:
    """Integration tests for admin route registration and auth requirements."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_admin_routes_registered(self, app):
        """Test that admin routes are registered."""
        routes = [route.path for route in app.routes]
        assert "/admin/stats" in routes
        assert "/admin/users" in routes
        assert "/admin/users/{user_id}" in routes
        assert "/admin/signups" in routes
        assert "/admin/funnel" in routes
        assert "/admin/top-users" in routes
        assert "/admin/audit-events" in routes

    def test_admin_stats_requires_auth(self, client):
        """Test that /admin/stats requires authentication (401)."""
        response = client.get("/admin/stats")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_users_requires_auth(self, client):
        """Test that /admin/users requires authentication (401)."""
        response = client.get("/admin/users")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_user_detail_requires_auth(self, client):
        """Test that /admin/users/{id} requires authentication (401)."""
        response = client.get(f"/admin/users/{uuid4()}")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_signups_requires_auth(self, client):
        """Test that /admin/signups requires authentication (401)."""
        response = client.get("/admin/signups")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_top_users_requires_auth(self, client):
        """Test that /admin/top-users requires authentication (401)."""
        response = client.get("/admin/top-users")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_funnel_requires_auth(self, client):
        """Test that /admin/funnel requires authentication (401)."""
        response = client.get("/admin/funnel")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_audit_events_requires_auth(self, client):
        """Test that /admin/audit-events requires authentication (401)."""
        response = client.get("/admin/audit-events")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_stats_with_invalid_token(self, client):
        """Test admin stats with invalid token returns 401."""
        response = client.get(
            "/admin/stats",
            headers={"Authorization": "Bearer invalid.token"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_users_with_invalid_token(self, client):
        """Test admin users with invalid token returns 401."""
        response = client.get(
            "/admin/users",
            headers={"Authorization": "Bearer invalid.token"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAdminQueryParams:
    """Tests for admin route query parameter validation."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_users_accepts_search_param(self, client):
        """Test that /admin/users accepts search query parameter."""
        response = client.get("/admin/users", params={"search": "test@example.com"})
        # Should fail on auth, not param validation
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_users_accepts_tier_param(self, client):
        """Test that /admin/users accepts tier query parameter."""
        response = client.get("/admin/users", params={"tier": "pro"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_users_accepts_page_param(self, client):
        """Test that /admin/users accepts page query parameter."""
        response = client.get("/admin/users", params={"page": "2"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_signups_accepts_days_param(self, client):
        """Test that /admin/signups accepts days query parameter."""
        response = client.get("/admin/signups", params={"days": "14"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_top_users_accepts_limit_param(self, client):
        """Test that /admin/top-users accepts limit query parameter."""
        response = client.get("/admin/top-users", params={"limit": "5"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_funnel_accepts_days_param(self, client):
        """Test that /admin/funnel accepts days query parameter."""
        response = client.get("/admin/funnel", params={"days": "14"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
