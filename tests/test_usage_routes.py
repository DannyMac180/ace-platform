"""Tests for usage reporting API routes.

These tests verify:
1. Route registration
2. Authentication requirements
3. Response schema validation
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ace_platform.api.routes.usage import (
    DailyUsageResponse,
    ModelUsageResponse,
    OperationUsageResponse,
    PlaybookUsageResponse,
    UsageSummaryResponse,
)


class TestUsageSchemas:
    """Tests for Pydantic schemas."""

    def test_usage_summary_response(self):
        """Test usage summary response schema."""
        now = datetime.now(timezone.utc)
        response = UsageSummaryResponse(
            start_date=now,
            end_date=now,
            total_requests=100,
            total_prompt_tokens=50000,
            total_completion_tokens=25000,
            total_tokens=75000,
            total_cost_usd=Decimal("1.50"),
        )
        assert response.total_requests == 100
        assert response.total_tokens == 75000
        assert response.total_cost_usd == Decimal("1.50")

    def test_daily_usage_response(self):
        """Test daily usage response schema."""
        now = datetime.now(timezone.utc)
        response = DailyUsageResponse(
            date=now,
            request_count=10,
            prompt_tokens=5000,
            completion_tokens=2500,
            total_tokens=7500,
            cost_usd=Decimal("0.15"),
        )
        assert response.request_count == 10
        assert response.total_tokens == 7500

    def test_playbook_usage_response(self):
        """Test playbook usage response schema."""
        playbook_id = uuid4()
        response = PlaybookUsageResponse(
            playbook_id=playbook_id,
            playbook_name="My Playbook",
            request_count=50,
            total_tokens=50000,
            cost_usd=Decimal("1.00"),
        )
        assert response.playbook_id == playbook_id
        assert response.playbook_name == "My Playbook"

    def test_playbook_usage_response_null_playbook(self):
        """Test playbook usage response with null playbook."""
        response = PlaybookUsageResponse(
            playbook_id=None,
            playbook_name=None,
            request_count=10,
            total_tokens=5000,
            cost_usd=Decimal("0.10"),
        )
        assert response.playbook_id is None
        assert response.playbook_name is None

    def test_operation_usage_response(self):
        """Test operation usage response schema."""
        response = OperationUsageResponse(
            operation="evolution_generator",
            request_count=30,
            total_tokens=30000,
            cost_usd=Decimal("0.60"),
        )
        assert response.operation == "evolution_generator"
        assert response.request_count == 30

    def test_model_usage_response(self):
        """Test model usage response schema."""
        response = ModelUsageResponse(
            model="gpt-4o",
            request_count=50,
            total_tokens=50000,
            cost_usd=Decimal("0.75"),
        )
        assert response.model == "gpt-4o"
        assert response.request_count == 50


class TestUsageRoutesIntegration:
    """Integration tests for usage routes."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_usage_routes_registered(self, app):
        """Test that usage routes are registered."""
        routes = [route.path for route in app.routes]
        assert "/usage/summary" in routes
        assert "/usage/daily" in routes
        assert "/usage/by-playbook" in routes
        assert "/usage/by-operation" in routes
        assert "/usage/by-model" in routes

    def test_summary_requires_auth(self, client):
        """Test that summary endpoint requires authentication."""
        response = client.get("/usage/summary")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_daily_requires_auth(self, client):
        """Test that daily endpoint requires authentication."""
        response = client.get("/usage/daily")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_by_playbook_requires_auth(self, client):
        """Test that by-playbook endpoint requires authentication."""
        response = client.get("/usage/by-playbook")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_by_operation_requires_auth(self, client):
        """Test that by-operation endpoint requires authentication."""
        response = client.get("/usage/by-operation")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_by_model_requires_auth(self, client):
        """Test that by-model endpoint requires authentication."""
        response = client.get("/usage/by-model")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_summary_with_invalid_token(self, client):
        """Test summary with invalid token."""
        response = client.get(
            "/usage/summary",
            headers={"Authorization": "Bearer invalid.token"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_daily_with_invalid_token(self, client):
        """Test daily with invalid token."""
        response = client.get(
            "/usage/daily",
            headers={"Authorization": "Bearer invalid.token"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestUsageRouteQueryParams:
    """Tests for query parameter validation."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_summary_accepts_date_params(self, client):
        """Test that summary accepts date query params."""
        # Will fail auth but validates params are accepted
        response = client.get(
            "/usage/summary",
            params={
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-01-31T23:59:59Z",
            },
        )
        # Should fail on auth, not on param validation
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_daily_accepts_date_params(self, client):
        """Test that daily accepts date query params."""
        response = client.get(
            "/usage/daily",
            params={
                "start_date": "2024-01-01T00:00:00Z",
                "end_date": "2024-01-31T23:59:59Z",
            },
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
