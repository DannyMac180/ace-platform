"""Tests for API middleware."""

import logging
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ace_platform.api.middleware import (
    CORRELATION_ID_HEADER,
    REQUEST_ID_HEADER,
    CorrelationIdFilter,
    CorrelationIdMiddleware,
    RequestTimingMiddleware,
    correlation_id_ctx,
    generate_correlation_id,
    get_correlation_id,
)


class TestCorrelationIdFunctions:
    """Tests for correlation ID utility functions."""

    def test_generate_correlation_id_returns_uuid(self):
        """Test that generate_correlation_id returns a valid UUID string."""
        correlation_id = generate_correlation_id()
        # Should be a valid UUID
        uuid.UUID(correlation_id)
        assert len(correlation_id) == 36  # UUID format with hyphens

    def test_generate_correlation_id_unique(self):
        """Test that each generated ID is unique."""
        ids = [generate_correlation_id() for _ in range(100)]
        assert len(set(ids)) == 100  # All unique

    def test_get_correlation_id_default_none(self):
        """Test that get_correlation_id returns None when not set."""
        # Reset context to ensure clean state
        correlation_id_ctx.set(None)
        assert get_correlation_id() is None

    def test_get_correlation_id_returns_set_value(self):
        """Test that get_correlation_id returns the set value."""
        test_id = "test-correlation-id-123"
        token = correlation_id_ctx.set(test_id)
        try:
            assert get_correlation_id() == test_id
        finally:
            correlation_id_ctx.reset(token)


class TestCorrelationIdMiddleware:
    """Tests for CorrelationIdMiddleware."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app with correlation ID middleware."""
        app = FastAPI()
        app.add_middleware(CorrelationIdMiddleware)

        @app.get("/test")
        async def test_route():
            return {"correlation_id": get_correlation_id()}

        return app

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_generates_correlation_id_when_not_provided(self, client):
        """Test that middleware generates a correlation ID when not in headers."""
        response = client.get("/test")
        assert response.status_code == 200

        # Should have correlation ID in response headers
        assert CORRELATION_ID_HEADER in response.headers
        correlation_id = response.headers[CORRELATION_ID_HEADER]

        # Should be a valid UUID
        uuid.UUID(correlation_id)

    def test_uses_provided_correlation_id_header(self, client):
        """Test that middleware uses X-Correlation-ID from request headers."""
        test_id = "my-custom-correlation-id"
        response = client.get(
            "/test",
            headers={CORRELATION_ID_HEADER: test_id},
        )

        assert response.status_code == 200
        assert response.headers[CORRELATION_ID_HEADER] == test_id
        assert response.json()["correlation_id"] == test_id

    def test_uses_provided_request_id_header(self, client):
        """Test that middleware uses X-Request-ID from request headers."""
        test_id = "my-request-id"
        response = client.get(
            "/test",
            headers={REQUEST_ID_HEADER: test_id},
        )

        assert response.status_code == 200
        assert response.headers[CORRELATION_ID_HEADER] == test_id
        assert response.json()["correlation_id"] == test_id

    def test_prefers_correlation_id_over_request_id(self, client):
        """Test that X-Correlation-ID takes precedence over X-Request-ID."""
        correlation_id = "correlation-id-value"
        request_id = "request-id-value"

        response = client.get(
            "/test",
            headers={
                CORRELATION_ID_HEADER: correlation_id,
                REQUEST_ID_HEADER: request_id,
            },
        )

        assert response.status_code == 200
        assert response.headers[CORRELATION_ID_HEADER] == correlation_id
        assert response.json()["correlation_id"] == correlation_id


class TestRequestTimingMiddleware:
    """Tests for RequestTimingMiddleware."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app with timing middleware."""
        app = FastAPI()
        app.add_middleware(RequestTimingMiddleware)

        @app.get("/test")
        async def test_route():
            return {"message": "ok"}

        return app

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_adds_process_time_header(self, client):
        """Test that middleware adds X-Process-Time header."""
        response = client.get("/test")
        assert response.status_code == 200
        assert "X-Process-Time" in response.headers

        # Should be a valid float
        process_time = float(response.headers["X-Process-Time"])
        assert process_time >= 0


class TestCorrelationIdFilter:
    """Tests for CorrelationIdFilter logging filter."""

    def test_adds_correlation_id_to_record(self):
        """Test that filter adds correlation_id to log records."""
        filter_ = CorrelationIdFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )

        # Set a correlation ID in context
        test_id = "test-log-correlation-id"
        token = correlation_id_ctx.set(test_id)
        try:
            result = filter_.filter(record)
            assert result is True
            assert record.correlation_id == test_id
        finally:
            correlation_id_ctx.reset(token)

    def test_uses_dash_when_no_correlation_id(self):
        """Test that filter uses '-' when no correlation ID is set."""
        filter_ = CorrelationIdFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )

        # Ensure no correlation ID is set
        correlation_id_ctx.set(None)

        result = filter_.filter(record)
        assert result is True
        assert record.correlation_id == "-"


class TestMiddlewareIntegration:
    """Integration tests for middleware working together."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app with all middleware."""
        app = FastAPI()
        # Add in reverse order (last added = first executed for requests)
        app.add_middleware(RequestTimingMiddleware)
        app.add_middleware(CorrelationIdMiddleware)

        @app.get("/test")
        async def test_route():
            return {"correlation_id": get_correlation_id()}

        return app

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_all_headers_present(self, client):
        """Test that all middleware headers are present."""
        response = client.get("/test")
        assert response.status_code == 200

        # Both headers should be present
        assert CORRELATION_ID_HEADER in response.headers
        assert "X-Process-Time" in response.headers

        # Correlation ID should be valid UUID
        uuid.UUID(response.headers[CORRELATION_ID_HEADER])

        # Process time should be valid float
        float(response.headers["X-Process-Time"])
