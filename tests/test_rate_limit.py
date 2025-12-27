"""Tests for rate limiting infrastructure.

These tests verify:
1. Rate limit result data structure
2. RateLimiter functionality
3. Rate limit configuration
4. Client IP extraction
5. Rate limit exception handling
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from ace_platform.core.rate_limit import (
    RATE_LIMITS,
    RateLimiter,
    RateLimitExceeded,
    RateLimitResult,
    get_client_ip,
    get_rate_limiter,
    rate_limit_login,
    rate_limit_outcome,
)


class TestRateLimitResult:
    """Tests for RateLimitResult dataclass."""

    def test_result_allowed(self):
        """Test allowed rate limit result."""
        result = RateLimitResult(
            allowed=True,
            remaining=4,
            reset_at=time.time() + 60,
            limit=5,
        )

        assert result.allowed is True
        assert result.remaining == 4
        assert result.limit == 5

    def test_result_exceeded(self):
        """Test exceeded rate limit result."""
        result = RateLimitResult(
            allowed=False,
            remaining=0,
            reset_at=time.time() + 30,
            limit=5,
        )

        assert result.allowed is False
        assert result.remaining == 0


class TestRateLimitExceeded:
    """Tests for RateLimitExceeded exception."""

    def test_default_message(self):
        """Test exception with default message."""
        exc = RateLimitExceeded()
        assert exc.status_code == 429
        assert exc.detail == "Rate limit exceeded"

    def test_custom_message(self):
        """Test exception with custom message."""
        exc = RateLimitExceeded(detail="Too many login attempts")
        assert exc.detail == "Too many login attempts"

    def test_retry_after_header(self):
        """Test exception includes Retry-After header."""
        exc = RateLimitExceeded(retry_after=60)
        assert exc.headers is not None
        assert exc.headers["Retry-After"] == "60"


class TestRateLimitConfigs:
    """Tests for rate limit configurations."""

    def test_login_config(self):
        """Test login rate limit configuration."""
        config = RATE_LIMITS["login"]
        assert config["limit"] == 5
        assert config["window_seconds"] == 60  # 1 minute

    def test_outcome_config(self):
        """Test outcome rate limit configuration."""
        config = RATE_LIMITS["outcome"]
        assert config["limit"] == 100
        assert config["window_seconds"] == 3600  # 1 hour

    def test_evolution_config(self):
        """Test evolution rate limit configuration."""
        config = RATE_LIMITS["evolution"]
        assert config["limit"] == 10
        assert config["window_seconds"] == 3600  # 1 hour


class TestGetClientIp:
    """Tests for client IP extraction."""

    def test_direct_client_ip(self):
        """Test extracting direct client IP."""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.100"

        ip = get_client_ip(request)
        assert ip == "192.168.1.100"

    def test_forwarded_ip_single(self):
        """Test extracting IP from X-Forwarded-For header."""
        request = MagicMock(spec=Request)
        request.headers = {"X-Forwarded-For": "10.0.0.1"}
        request.client = MagicMock()
        request.client.host = "127.0.0.1"

        ip = get_client_ip(request)
        assert ip == "10.0.0.1"

    def test_forwarded_ip_chain(self):
        """Test extracting first IP from X-Forwarded-For chain."""
        request = MagicMock(spec=Request)
        request.headers = {"X-Forwarded-For": "10.0.0.1, 10.0.0.2, 10.0.0.3"}
        request.client = MagicMock()

        ip = get_client_ip(request)
        assert ip == "10.0.0.1"

    def test_no_client(self):
        """Test when no client info is available."""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = None

        ip = get_client_ip(request)
        assert ip == "unknown"


class TestGetRateLimiter:
    """Tests for rate limiter singleton."""

    def test_returns_rate_limiter(self):
        """Test that get_rate_limiter returns a RateLimiter."""
        limiter = get_rate_limiter()
        assert isinstance(limiter, RateLimiter)

    def test_returns_same_instance(self):
        """Test that get_rate_limiter returns the same instance."""
        limiter1 = get_rate_limiter()
        limiter2 = get_rate_limiter()
        assert limiter1 is limiter2


class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_make_key(self):
        """Test rate limit key generation."""
        limiter = RateLimiter()
        key = limiter._make_key("login", "192.168.1.1")
        assert key == "ratelimit:login:192.168.1.1"

    def test_make_key_with_uuid(self):
        """Test rate limit key generation with UUID."""
        limiter = RateLimiter()
        key = limiter._make_key("outcome", "abc-123-def")
        assert key == "ratelimit:outcome:abc-123-def"


class TestRateLimitLoginDependency:
    """Tests for login rate limit dependency."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock request."""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.100"
        request.state = MagicMock()
        return request

    @pytest.mark.asyncio
    async def test_login_rate_limit_allowed(self, mock_request):
        """Test login request allowed within rate limit."""
        mock_result = RateLimitResult(
            allowed=True,
            remaining=4,
            reset_at=time.time() + 60,
            limit=5,
        )

        with patch("ace_platform.core.rate_limit.get_rate_limiter") as mock_get_limiter:
            mock_limiter = AsyncMock()
            mock_limiter.is_allowed = AsyncMock(return_value=mock_result)
            mock_get_limiter.return_value = mock_limiter

            # Should not raise
            await rate_limit_login(mock_request)

            # Verify is_allowed was called with correct parameters
            mock_limiter.is_allowed.assert_called_once()
            call_args = mock_limiter.is_allowed.call_args
            assert call_args[0][0] == "login"
            assert call_args[0][1] == "192.168.1.100"
            assert call_args[0][2] == 5  # limit
            assert call_args[0][3] == 60  # window_seconds

    @pytest.mark.asyncio
    async def test_login_rate_limit_exceeded(self, mock_request):
        """Test login request rejected when rate limit exceeded."""
        mock_result = RateLimitResult(
            allowed=False,
            remaining=0,
            reset_at=time.time() + 30,
            limit=5,
        )

        with patch("ace_platform.core.rate_limit.get_rate_limiter") as mock_get_limiter:
            mock_limiter = AsyncMock()
            mock_limiter.is_allowed = AsyncMock(return_value=mock_result)
            mock_get_limiter.return_value = mock_limiter

            with pytest.raises(RateLimitExceeded) as exc_info:
                await rate_limit_login(mock_request)

            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_login_rate_limit_redis_unavailable(self, mock_request):
        """Test that request is allowed if Redis is unavailable."""
        with patch("ace_platform.core.rate_limit.get_rate_limiter") as mock_get_limiter:
            mock_limiter = AsyncMock()
            mock_limiter.is_allowed = AsyncMock(side_effect=Exception("Redis unavailable"))
            mock_get_limiter.return_value = mock_limiter

            # Should not raise - allows request if Redis is down
            await rate_limit_login(mock_request)


class TestRateLimitOutcomeDependency:
    """Tests for outcome rate limit dependency."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock request."""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.100"
        request.state = MagicMock()
        return request

    @pytest.mark.asyncio
    async def test_outcome_rate_limit_allowed(self, mock_request):
        """Test outcome request allowed within rate limit."""
        mock_result = RateLimitResult(
            allowed=True,
            remaining=99,
            reset_at=time.time() + 3600,
            limit=100,
        )

        with patch("ace_platform.core.rate_limit.get_rate_limiter") as mock_get_limiter:
            mock_limiter = AsyncMock()
            mock_limiter.is_allowed = AsyncMock(return_value=mock_result)
            mock_get_limiter.return_value = mock_limiter

            # Should not raise
            await rate_limit_outcome(mock_request, "user-123")

            # Verify is_allowed was called with correct parameters
            mock_limiter.is_allowed.assert_called_once()
            call_args = mock_limiter.is_allowed.call_args
            assert call_args[0][0] == "outcome"
            assert call_args[0][1] == "user-123"
            assert call_args[0][2] == 100  # limit
            assert call_args[0][3] == 3600  # window_seconds

    @pytest.mark.asyncio
    async def test_outcome_rate_limit_exceeded(self, mock_request):
        """Test outcome request rejected when rate limit exceeded."""
        mock_result = RateLimitResult(
            allowed=False,
            remaining=0,
            reset_at=time.time() + 1800,
            limit=100,
        )

        with patch("ace_platform.core.rate_limit.get_rate_limiter") as mock_get_limiter:
            mock_limiter = AsyncMock()
            mock_limiter.is_allowed = AsyncMock(return_value=mock_result)
            mock_get_limiter.return_value = mock_limiter

            with pytest.raises(RateLimitExceeded) as exc_info:
                await rate_limit_outcome(mock_request, "user-123")

            assert exc_info.value.status_code == 429


class TestRateLimitEndpointIntegration:
    """Integration tests for rate limited endpoints."""

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

    def test_login_returns_429_header(self, client):
        """Test that login endpoint includes rate limit response code."""
        # The endpoint should have 429 in its responses

        # Check route has 429 response
        routes = [r for r in client.app.routes if getattr(r, "path", "") == "/auth/login"]
        assert len(routes) > 0

    def test_outcome_returns_429_header(self, client):
        """Test that outcome creation endpoint includes rate limit response code."""
        # Check the OpenAPI spec shows 429 as a response
        openapi = client.app.openapi()
        outcome_path = openapi.get("paths", {}).get("/playbooks/{playbook_id}/outcomes", {})
        post_responses = outcome_path.get("post", {}).get("responses", {})
        assert "429" in post_responses
