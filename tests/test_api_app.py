"""Tests for the FastAPI application setup."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from ace_platform.api.main import _traces_sampler, app, create_app
from ace_platform.api.middleware import CORRELATION_ID_HEADER


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return TestClient(app)

    def test_health_check_returns_healthy(self, client):
        """Test that /health returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "ace-platform"

    def test_health_check_includes_correlation_id(self, client):
        """Test that /health response includes correlation ID."""
        response = client.get("/health")
        assert response.status_code == 200
        assert CORRELATION_ID_HEADER in response.headers

    def test_readiness_check_with_db_connected(self, client):
        """Test /ready endpoint when database is connected."""
        # Note: Patches at definition site; works because import is inside the route handler
        with patch("ace_platform.db.session.async_session_context") as mock_session:
            mock_db = AsyncMock()
            mock_db.execute = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db

            response = client.get("/ready")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"
            assert data["database"] == "connected"

    def test_readiness_check_with_db_disconnected(self, client):
        """Test /ready endpoint returns 503 when database is not available."""
        # Note: Patches at definition site; works because import is inside the route handler
        with patch("ace_platform.db.session.async_session_context") as mock_session:
            mock_session.return_value.__aenter__.side_effect = Exception("Connection failed")

            response = client.get("/ready")
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "not_ready"
            assert data["database"] == "disconnected"


class TestExceptionHandlers:
    """Tests for global exception handlers."""

    @pytest.fixture
    def test_app(self):
        """Create a test app with routes that raise exceptions."""
        test_app = create_app()

        @test_app.get("/raise-http-404")
        async def raise_http_404():
            raise HTTPException(status_code=404, detail="Resource not found")

        @test_app.get("/raise-http-403")
        async def raise_http_403():
            raise HTTPException(status_code=403, detail="Access denied")

        class ValidationModel(BaseModel):
            name: str
            age: int

        @test_app.post("/validate")
        async def validate_input(data: ValidationModel):
            return {"received": data.model_dump()}

        @test_app.get("/raise-generic")
        async def raise_generic():
            raise ValueError("Something went wrong")

        return test_app

    @pytest.fixture
    def client(self, test_app):
        """Create a test client for the test app."""
        return TestClient(test_app, raise_server_exceptions=False)

    def test_http_exception_404_response_format(self, client):
        """Test that HTTP 404 exceptions return consistent error format."""
        response = client.get("/raise-http-404")
        assert response.status_code == 404

        data = response.json()
        assert "error" in data
        assert data["error"]["type"] == "http_error"
        assert data["error"]["message"] == "Resource not found"
        assert data["error"]["status_code"] == 404
        assert "correlation_id" in data

    def test_http_exception_403_response_format(self, client):
        """Test that HTTP 403 exceptions return consistent error format."""
        response = client.get("/raise-http-403")
        assert response.status_code == 403

        data = response.json()
        assert data["error"]["type"] == "http_error"
        assert data["error"]["message"] == "Access denied"
        assert data["error"]["status_code"] == 403

    def test_validation_error_response_format(self, client):
        """Test that validation errors return detailed error format."""
        response = client.post(
            "/validate",
            json={"name": 123, "age": "not-a-number"},  # Invalid types
        )
        assert response.status_code == 422

        data = response.json()
        assert "error" in data
        assert data["error"]["type"] == "validation_error"
        assert data["error"]["message"] == "Request validation failed"
        assert "details" in data["error"]
        assert len(data["error"]["details"]) > 0
        assert "correlation_id" in data

        # Check error details structure
        error_detail = data["error"]["details"][0]
        assert "field" in error_detail
        assert "message" in error_detail
        assert "type" in error_detail

    def test_validation_error_missing_required_field(self, client):
        """Test validation error for missing required fields."""
        response = client.post(
            "/validate",
            json={"name": "test"},  # Missing 'age' field
        )
        assert response.status_code == 422

        data = response.json()
        assert data["error"]["type"] == "validation_error"
        # Should have at least one error about missing field
        fields_with_errors = [e["field"] for e in data["error"]["details"]]
        assert any("age" in field for field in fields_with_errors)

    def test_generic_exception_returns_500(self, client):
        """Test that unhandled exceptions return 500 with safe message."""
        response = client.get("/raise-generic")
        assert response.status_code == 500

        data = response.json()
        assert "error" in data
        assert data["error"]["type"] == "internal_error"
        assert "correlation_id" in data
        # Should not leak exception details in non-debug mode
        assert data["error"]["message"] == "An unexpected error occurred"

    def test_generic_exception_redacts_sensitive_headers_in_sentry_context(self):
        """Test that sensitive request headers are redacted before Sentry capture."""
        test_app = create_app()

        @test_app.get("/raise-generic-redaction")
        async def raise_generic_redaction():
            raise ValueError("redaction test")

        captured_context: dict[str, dict] = {}

        class DummyScope:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                return False

            def set_tag(self, key, value):
                return None

            def set_context(self, key, value):
                captured_context[key] = value

        with (
            patch("ace_platform.api.main.sentry_sdk.new_scope", return_value=DummyScope()),
            patch("ace_platform.api.main.sentry_sdk.capture_exception"),
        ):
            client = TestClient(test_app, raise_server_exceptions=False)
            response = client.get(
                "/raise-generic-redaction",
                headers={
                    "Authorization": "Bearer top-secret-token",
                    "Cookie": "sessionid=abc123",
                    "X-Api-Key": "super-secret-key",
                    "X-Correlation-ID": "test-correlation-id",
                    "User-Agent": "pytest-agent",
                },
            )

        assert response.status_code == 500
        assert "request" in captured_context

        request_headers = {
            key.lower(): value for key, value in captured_context["request"]["headers"].items()
        }
        assert request_headers["authorization"] == "[REDACTED]"
        assert request_headers["cookie"] == "[REDACTED]"
        assert request_headers["x-api-key"] == "[REDACTED]"
        assert request_headers["x-correlation-id"] == "test-correlation-id"
        assert request_headers["user-agent"] == "pytest-agent"

    def test_traces_sampler_uses_effective_api_sample_rate(self):
        context = {"transaction_context": {"name": "/playbooks"}}
        with patch("ace_platform.api.main.get_effective_traces_sample_rate", return_value=0.25):
            assert _traces_sampler(context) == 0.25

    def test_generic_exception_shows_details_in_debug_mode(self):
        """Test that debug mode shows exception details in error response."""
        with patch("ace_platform.api.main.settings") as mock_settings:
            mock_settings.debug = True
            mock_settings.cors_origins = ["http://localhost:3000"]

            test_app = create_app()

            @test_app.get("/raise-debug-error")
            async def raise_debug_error():
                raise ValueError("Detailed error info")

            client = TestClient(test_app, raise_server_exceptions=False)
            response = client.get("/raise-debug-error")

            assert response.status_code == 500
            data = response.json()
            # In debug mode, should include exception type and message
            assert "ValueError" in data["error"]["message"]
            assert "Detailed error info" in data["error"]["message"]

    def test_http_exception_preserves_headers(self):
        """Test that HTTP exception headers are preserved in response."""
        test_app = create_app()

        @test_app.get("/raise-401-with-header")
        async def raise_401_with_header():
            raise HTTPException(
                status_code=401,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer realm='api'"},
            )

        client = TestClient(test_app, raise_server_exceptions=False)
        response = client.get("/raise-401-with-header")

        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers
        assert response.headers["WWW-Authenticate"] == "Bearer realm='api'"

    def test_error_response_includes_correlation_id_header(self, client):
        """Test that error responses include correlation ID in headers."""
        response = client.get("/raise-http-404")
        assert CORRELATION_ID_HEADER in response.headers


class TestCORSMiddleware:
    """Tests for CORS middleware configuration."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return TestClient(app)

    def test_cors_headers_on_options_request(self, client):
        """Test that CORS headers are present on OPTIONS requests."""
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # OPTIONS should succeed (preflight)
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers

    def test_cors_exposes_custom_headers(self, client):
        """Test that CORS exposes custom headers."""
        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )
        assert response.status_code == 200
        # Check that our custom headers are exposed
        exposed_headers = response.headers.get("access-control-expose-headers", "")
        assert (
            "X-Correlation-ID" in exposed_headers or "x-correlation-id" in exposed_headers.lower()
        )


class TestAppConfiguration:
    """Tests for application configuration."""

    _MCP_INITIALIZE_HEADERS = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    _MCP_INITIALIZE_PAYLOAD = {
        "jsonrpc": "2.0",
        "id": "init-1",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    }

    def test_create_app_returns_fastapi_instance(self):
        """Test that create_app returns a FastAPI instance."""
        from fastapi import FastAPI

        app = create_app()
        assert isinstance(app, FastAPI)

    def test_app_has_correct_title(self):
        """Test that the app has the correct title."""
        test_app = create_app()
        assert test_app.title == "ACE Platform"

    def test_app_has_correct_version(self):
        """Test that the app has the correct version."""
        test_app = create_app()
        assert test_app.version == "0.1.0"

    def test_app_registers_health_routes(self):
        """Test that health routes are registered."""
        test_app = create_app()
        routes = [route.path for route in test_app.routes]
        assert "/health" in routes
        assert "/ready" in routes

    def test_mcp_streamable_and_legacy_endpoints_are_mounted(self):
        """Mounted MCP endpoints should exist for both HTTP and legacy SSE."""
        with TestClient(app) as client:
            response = client.get("/mcp")
            assert response.status_code != 404

            # Probe legacy SSE mount without opening a streaming SSE connection.
            response = client.options("/mcp/sse")
            assert response.status_code != 404

    def test_mcp_root_post_does_not_redirect(self):
        """POST /mcp should initialize directly without slash redirect."""
        with TestClient(app) as client:
            response = client.post(
                "/mcp",
                headers=self._MCP_INITIALIZE_HEADERS,
                json=self._MCP_INITIALIZE_PAYLOAD,
                follow_redirects=False,
            )
            assert response.status_code != 307
            assert response.headers.get("mcp-session-id")

    def test_app_lifespan_can_restart_after_streamable_http_session_shutdown(self):
        """Repeated app startups should not fail on one-shot session manager reuse."""
        with TestClient(app) as first_client:
            first_response = first_client.get("/health")
            assert first_response.status_code == 200

        with TestClient(app) as second_client:
            second_response = second_client.get("/health")
            assert second_response.status_code == 200


class TestRequestProcessing:
    """Tests for request processing features."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return TestClient(app)

    def test_response_includes_process_time_header(self, client):
        """Test that responses include X-Process-Time header."""
        response = client.get("/health")
        assert "X-Process-Time" in response.headers
        # Should be a valid float
        process_time = float(response.headers["X-Process-Time"])
        assert process_time >= 0

    def test_custom_correlation_id_is_preserved(self, client):
        """Test that a custom correlation ID is preserved in response."""
        custom_id = "my-custom-correlation-id-123"
        response = client.get(
            "/health",
            headers={CORRELATION_ID_HEADER: custom_id},
        )
        assert response.status_code == 200
        assert response.headers[CORRELATION_ID_HEADER] == custom_id

    def test_generated_correlation_id_is_valid_uuid(self, client):
        """Test that generated correlation IDs are valid UUIDs."""
        import uuid

        response = client.get("/health")
        correlation_id = response.headers[CORRELATION_ID_HEADER]
        # Should be a valid UUID
        uuid.UUID(correlation_id)
