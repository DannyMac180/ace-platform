"""Tests for login lockout with exponential backoff.

These tests verify:
1. LockoutStatus data structure
2. LoginLockoutManager functionality
3. Exponential backoff calculation
4. Lockout configuration
5. Integration with login endpoint
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from ace_platform.core.login_lockout import (
    LOCKOUT_CONFIG,
    LockoutStatus,
    LoginLockoutExceeded,
    LoginLockoutManager,
    check_login_lockout,
    get_lockout_manager,
    record_login_failure,
    reset_login_lockout,
)


class TestLockoutStatus:
    """Tests for LockoutStatus dataclass."""

    def test_not_locked(self):
        """Test status when not locked out."""
        status = LockoutStatus(
            is_locked=False,
            retry_after=0,
            failed_attempts=2,
            threshold=5,
        )

        assert status.is_locked is False
        assert status.retry_after == 0
        assert status.failed_attempts == 2
        assert status.threshold == 5

    def test_locked_out(self):
        """Test status when locked out."""
        status = LockoutStatus(
            is_locked=True,
            retry_after=30,
            failed_attempts=5,
            threshold=5,
        )

        assert status.is_locked is True
        assert status.retry_after == 30


class TestLoginLockoutExceeded:
    """Tests for LoginLockoutExceeded exception."""

    def test_exception_message(self):
        """Test exception message includes attempt count."""
        exc = LoginLockoutExceeded(retry_after=60, failed_attempts=7)
        assert exc.status_code == 429
        assert "7" in exc.detail
        assert "60 seconds" in exc.detail

    def test_retry_after_header(self):
        """Test exception includes Retry-After header."""
        exc = LoginLockoutExceeded(retry_after=120, failed_attempts=6)
        assert exc.headers is not None
        assert exc.headers["Retry-After"] == "120"


class TestLockoutConfig:
    """Tests for lockout configuration."""

    def test_threshold(self):
        """Test lockout threshold configuration."""
        assert LOCKOUT_CONFIG["threshold"] == 5

    def test_base_delay(self):
        """Test base delay configuration."""
        assert LOCKOUT_CONFIG["base_delay_seconds"] == 30

    def test_max_delay(self):
        """Test max delay configuration."""
        assert LOCKOUT_CONFIG["max_delay_seconds"] == 3600  # 1 hour

    def test_window(self):
        """Test tracking window configuration."""
        assert LOCKOUT_CONFIG["window_seconds"] == 3600  # 1 hour


class TestExponentialBackoff:
    """Tests for exponential backoff calculation."""

    def test_under_threshold(self):
        """Test no lockout under threshold."""
        manager = LoginLockoutManager()
        delay = manager._calculate_lockout_seconds(4)
        assert delay == 0

    def test_at_threshold(self):
        """Test first lockout at threshold."""
        manager = LoginLockoutManager()
        delay = manager._calculate_lockout_seconds(5)
        assert delay == 30  # base_delay * 2^0 = 30

    def test_exponential_growth(self):
        """Test exponential growth of lockout duration."""
        manager = LoginLockoutManager()

        # 5 failures: 30s (base * 2^0)
        assert manager._calculate_lockout_seconds(5) == 30

        # 6 failures: 60s (base * 2^1)
        assert manager._calculate_lockout_seconds(6) == 60

        # 7 failures: 120s (base * 2^2)
        assert manager._calculate_lockout_seconds(7) == 120

        # 8 failures: 240s (base * 2^3)
        assert manager._calculate_lockout_seconds(8) == 240

        # 9 failures: 480s (base * 2^4)
        assert manager._calculate_lockout_seconds(9) == 480

    def test_max_delay_cap(self):
        """Test that lockout duration is capped at max."""
        manager = LoginLockoutManager()

        # Many failures should cap at max_delay
        delay = manager._calculate_lockout_seconds(20)
        assert delay == 3600  # max_delay


class TestLoginLockoutManager:
    """Tests for LoginLockoutManager class."""

    def test_make_key_ip(self):
        """Test Redis key generation for IP."""
        manager = LoginLockoutManager()
        key = manager._make_key("ip", "192.168.1.1")
        assert key == "login_lockout:ip:192.168.1.1"

    def test_make_key_email(self):
        """Test Redis key generation for email."""
        manager = LoginLockoutManager()
        key = manager._make_key("email", "User@Example.com")
        assert key == "login_lockout:email:user@example.com"  # lowercase


class TestGetLockoutManager:
    """Tests for lockout manager singleton."""

    def test_returns_lockout_manager(self):
        """Test that get_lockout_manager returns a LoginLockoutManager."""
        manager = get_lockout_manager()
        assert isinstance(manager, LoginLockoutManager)

    def test_returns_same_instance(self):
        """Test that get_lockout_manager returns the same instance."""
        manager1 = get_lockout_manager()
        manager2 = get_lockout_manager()
        assert manager1 is manager2


class TestCheckLoginLockout:
    """Tests for check_login_lockout function."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock request."""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.100"
        return request

    @pytest.mark.asyncio
    async def test_not_locked_allows_login(self, mock_request):
        """Test that login is allowed when not locked out."""
        mock_status = LockoutStatus(
            is_locked=False,
            retry_after=0,
            failed_attempts=2,
            threshold=5,
        )

        with patch("ace_platform.core.login_lockout.get_lockout_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.check_lockout = AsyncMock(return_value=mock_status)
            mock_get_manager.return_value = mock_manager

            # Should not raise
            await check_login_lockout(mock_request, "user@example.com")

            mock_manager.check_lockout.assert_called_once()

    @pytest.mark.asyncio
    async def test_locked_raises_exception(self, mock_request):
        """Test that login raises exception when locked out."""
        mock_status = LockoutStatus(
            is_locked=True,
            retry_after=60,
            failed_attempts=7,
            threshold=5,
        )

        with patch("ace_platform.core.login_lockout.get_lockout_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.check_lockout = AsyncMock(return_value=mock_status)
            mock_get_manager.return_value = mock_manager

            with pytest.raises(LoginLockoutExceeded) as exc_info:
                await check_login_lockout(mock_request, "user@example.com")

            assert exc_info.value.status_code == 429


class TestRecordLoginFailure:
    """Tests for record_login_failure function."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock request."""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.100"
        return request

    @pytest.mark.asyncio
    async def test_records_failure(self, mock_request):
        """Test that failure is recorded."""
        with patch("ace_platform.core.login_lockout.get_lockout_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.record_failure = AsyncMock()
            mock_get_manager.return_value = mock_manager

            await record_login_failure(mock_request, "user@example.com")

            mock_manager.record_failure.assert_called_once_with(
                ip="192.168.1.100", email="user@example.com"
            )


class TestResetLoginLockout:
    """Tests for reset_login_lockout function."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock request."""
        request = MagicMock(spec=Request)
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "192.168.1.100"
        return request

    @pytest.mark.asyncio
    async def test_resets_counters(self, mock_request):
        """Test that counters are reset on success."""
        with patch("ace_platform.core.login_lockout.get_lockout_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.reset = AsyncMock()
            mock_get_manager.return_value = mock_manager

            await reset_login_lockout(mock_request, "user@example.com")

            mock_manager.reset.assert_called_once_with(ip="192.168.1.100", email="user@example.com")


class TestLockoutManagerWithMockRedis:
    """Tests for LoginLockoutManager with mocked Redis."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = AsyncMock()
        return redis

    @pytest.mark.asyncio
    async def test_check_lockout_no_attempts(self, mock_redis):
        """Test check_lockout with no previous attempts."""
        mock_redis.zcount = AsyncMock(return_value=0)

        manager = LoginLockoutManager()
        manager._redis = mock_redis

        status = await manager.check_lockout(ip="192.168.1.1", email="user@test.com")

        assert status.is_locked is False
        assert status.failed_attempts == 0

    @pytest.mark.asyncio
    async def test_check_lockout_under_threshold(self, mock_redis):
        """Test check_lockout with attempts under threshold."""
        mock_redis.zcount = AsyncMock(return_value=3)

        manager = LoginLockoutManager()
        manager._redis = mock_redis

        status = await manager.check_lockout(ip="192.168.1.1")

        assert status.is_locked is False
        assert status.failed_attempts == 3

    @pytest.mark.asyncio
    async def test_check_lockout_at_threshold_expired(self, mock_redis):
        """Test check_lockout at threshold but lockout expired."""
        # 5 attempts, but last attempt was long ago (lockout expired)
        mock_redis.zcount = AsyncMock(return_value=5)
        mock_redis.zrange = AsyncMock(return_value=[("timestamp", time.time() - 100)])

        manager = LoginLockoutManager()
        manager._redis = mock_redis

        status = await manager.check_lockout(ip="192.168.1.1")

        # 5 attempts + 30s lockout = lockout ended after 30s
        # Last attempt was 100s ago, so lockout expired
        assert status.is_locked is False

    @pytest.mark.asyncio
    async def test_check_lockout_active(self, mock_redis):
        """Test check_lockout with active lockout."""
        now = time.time()
        # 5 attempts, last attempt was 10 seconds ago
        mock_redis.zcount = AsyncMock(return_value=5)
        mock_redis.zrange = AsyncMock(return_value=[("timestamp", now - 10)])

        manager = LoginLockoutManager()
        manager._redis = mock_redis

        status = await manager.check_lockout(ip="192.168.1.1")

        # 5 attempts = 30s lockout, last attempt 10s ago = ~20s remaining
        # Allow 1 second tolerance for test execution time
        assert status.is_locked is True
        assert 18 <= status.retry_after <= 21

    @pytest.mark.asyncio
    async def test_record_failure(self, mock_redis):
        """Test record_failure stores attempt in Redis."""
        mock_pipeline = AsyncMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipeline)
        mock_pipeline.execute = AsyncMock(return_value=[])

        manager = LoginLockoutManager()
        manager._redis = mock_redis

        await manager.record_failure(ip="192.168.1.1", email="user@test.com")

        # Should have called pipeline operations for both IP and email
        mock_redis.pipeline.assert_called()
        mock_pipeline.execute.assert_called()

    @pytest.mark.asyncio
    async def test_reset(self, mock_redis):
        """Test reset deletes keys from Redis."""
        mock_pipeline = AsyncMock()
        mock_redis.pipeline = MagicMock(return_value=mock_pipeline)
        mock_pipeline.execute = AsyncMock(return_value=[])

        manager = LoginLockoutManager()
        manager._redis = mock_redis

        await manager.reset(ip="192.168.1.1", email="user@test.com")

        # Should have called delete for both keys
        mock_redis.pipeline.assert_called()
        mock_pipeline.delete.assert_called()
        mock_pipeline.execute.assert_called()

    @pytest.mark.asyncio
    async def test_graceful_degradation_on_redis_error(self):
        """Test that lockout check allows login if Redis is unavailable."""
        manager = LoginLockoutManager()

        # Mock _get_redis to raise an exception
        with patch.object(manager, "_get_redis", side_effect=Exception("Redis unavailable")):
            status = await manager.check_lockout(ip="192.168.1.1")

        # Should allow login when Redis is down
        assert status.is_locked is False
        assert status.failed_attempts == 0


class TestLoginEndpointIntegration:
    """Integration tests for login endpoint with lockout."""

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

    def test_login_endpoint_has_429_response(self, client):
        """Test that login endpoint documents 429 response."""
        openapi = client.app.openapi()
        login_path = openapi.get("paths", {}).get("/auth/login", {})
        post_responses = login_path.get("post", {}).get("responses", {})
        assert "429" in post_responses

    def test_login_endpoint_docstring_mentions_lockout(self, client):
        """Test that login endpoint documentation mentions lockout."""
        routes = [r for r in client.app.routes if getattr(r, "path", "") == "/auth/login"]
        assert len(routes) > 0

        # Check the endpoint function has lockout documentation
        route = routes[0]
        if hasattr(route, "endpoint"):
            docstring = route.endpoint.__doc__ or ""
            assert "exponential backoff" in docstring.lower() or "failed" in docstring.lower()
