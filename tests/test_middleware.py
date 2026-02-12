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
    SecurityHeadersMiddleware,
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

    @pytest.mark.asyncio
    async def test_handles_non_utf8_header_bytes(self):
        """Test raw non-UTF-8 bytes do not crash correlation ID parsing."""

        async def app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        middleware = CorrelationIdMiddleware(app)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [(b"x-correlation-id", b"\xff\xfe")],
        }
        response_parts: list[dict] = []

        async def send(message):
            response_parts.append(message)

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        await middleware(scope, receive, send)

        start = next(part for part in response_parts if part["type"] == "http.response.start")
        response_headers = dict(start["headers"])
        assert b"x-correlation-id" in response_headers


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


class TestSecurityHeadersMiddleware:
    """Tests for SecurityHeadersMiddleware."""

    @pytest.fixture
    def app(self):
        """Create a test FastAPI app with security headers middleware."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        async def test_route():
            return {"message": "ok"}

        return app

    @pytest.fixture
    def client(self, app):
        """Create a test client."""
        return TestClient(app)

    def test_adds_x_content_type_options(self, client):
        """Test that middleware adds X-Content-Type-Options header."""
        response = client.get("/test")
        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"

    def test_adds_x_frame_options(self, client):
        """Test that middleware adds X-Frame-Options header."""
        response = client.get("/test")
        assert response.status_code == 200
        assert response.headers["X-Frame-Options"] == "DENY"

    def test_adds_x_xss_protection(self, client):
        """Test that middleware adds X-XSS-Protection header."""
        response = client.get("/test")
        assert response.status_code == 200
        assert response.headers["X-XSS-Protection"] == "1; mode=block"

    def test_adds_referrer_policy(self, client):
        """Test that middleware adds Referrer-Policy header."""
        response = client.get("/test")
        assert response.status_code == 200
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_adds_content_security_policy(self, client):
        """Test that middleware adds Content-Security-Policy header."""
        response = client.get("/test")
        assert response.status_code == 200
        assert "Content-Security-Policy" in response.headers
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]

    def test_adds_permissions_policy(self, client):
        """Test that middleware adds Permissions-Policy header."""
        response = client.get("/test")
        assert response.status_code == 200
        assert "Permissions-Policy" in response.headers
        assert "camera=()" in response.headers["Permissions-Policy"]

    def test_adds_hsts_when_enabled(self, client):
        """Test that middleware adds HSTS header when enabled."""
        response = client.get("/test")
        assert response.status_code == 200
        assert "Strict-Transport-Security" in response.headers
        hsts = response.headers["Strict-Transport-Security"]
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts


class TestSecurityHeadersMiddlewareConfig:
    """Tests for SecurityHeadersMiddleware configuration options."""

    def test_hsts_disabled(self):
        """Test that HSTS header is not added when disabled."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware, enable_hsts=False)

        @app.get("/test")
        async def test_route():
            return {"message": "ok"}

        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 200
        assert "Strict-Transport-Security" not in response.headers

    def test_custom_hsts_max_age(self):
        """Test that custom HSTS max-age is used."""
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware, hsts_max_age=86400)

        @app.get("/test")
        async def test_route():
            return {"message": "ok"}

        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 200
        assert "max-age=86400" in response.headers["Strict-Transport-Security"]

    def test_hsts_without_subdomains(self):
        """Test HSTS without includeSubDomains."""
        app = FastAPI()
        app.add_middleware(
            SecurityHeadersMiddleware,
            hsts_include_subdomains=False,
        )

        @app.get("/test")
        async def test_route():
            return {"message": "ok"}

        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 200
        hsts = response.headers["Strict-Transport-Security"]
        assert "includeSubDomains" not in hsts

    def test_custom_csp(self):
        """Test that custom CSP is used."""
        custom_csp = "default-src 'none'; script-src 'self'"
        app = FastAPI()
        app.add_middleware(
            SecurityHeadersMiddleware,
            content_security_policy=custom_csp,
        )

        @app.get("/test")
        async def test_route():
            return {"message": "ok"}

        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 200
        assert response.headers["Content-Security-Policy"] == custom_csp
