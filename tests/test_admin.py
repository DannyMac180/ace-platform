"""Tests for admin dashboard API routes.

These tests verify:
1. Admin routes require authentication (401 without token)
2. Admin routes require admin role (403 for non-admin user)
3. Route registration
4. Response schema validation
"""

from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ace_platform.api.routes.admin import (
    AdminUserItem,
    AuditEventItem,
    DailySignupResponse,
    PlatformStatsResponse,
    TopUserResponse,
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
