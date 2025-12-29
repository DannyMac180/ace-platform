"""Login attempt lockout with exponential backoff.

This module provides Redis-backed login attempt tracking with:
- Per-IP and per-email failed attempt tracking
- Exponential backoff after threshold failures
- Automatic reset on successful login
- Graceful degradation if Redis is unavailable

Security benefits:
- Prevents brute-force attacks on user accounts
- Rate limits credential stuffing attacks
- Tracks both IP (for distributed attacks) and email (for targeted attacks)

Usage:
    from ace_platform.core.login_lockout import LoginLockoutManager, check_login_lockout

    # As a dependency check before authentication
    lockout_manager = get_lockout_manager()

    # Check if locked out
    lockout = await lockout_manager.check_lockout(ip="1.2.3.4", email="user@example.com")
    if lockout.is_locked:
        raise HTTPException(429, f"Too many failed attempts. Try again in {lockout.retry_after}s")

    # Record failed attempt
    await lockout_manager.record_failure(ip="1.2.3.4", email="user@example.com")

    # Reset on successful login
    await lockout_manager.reset(ip="1.2.3.4", email="user@example.com")
"""

import logging
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request, status
from redis.asyncio import Redis

from ace_platform.config import get_settings

logger = logging.getLogger(__name__)

# Lockout configuration
LOCKOUT_CONFIG = {
    "threshold": 5,  # Start lockout after N failed attempts
    "base_delay_seconds": 30,  # First lockout duration
    "max_delay_seconds": 3600,  # Maximum lockout (1 hour)
    "window_seconds": 3600,  # Track attempts within this window
}


@dataclass
class LockoutStatus:
    """Result of a lockout check."""

    is_locked: bool
    retry_after: int  # Seconds until lockout expires (0 if not locked)
    failed_attempts: int  # Number of failed attempts in window
    threshold: int  # Threshold before lockout kicks in


class LoginLockoutManager:
    """Redis-backed login lockout manager with exponential backoff.

    Tracks failed login attempts by both IP address and email address.
    After the threshold is reached, applies exponential backoff delays.

    Delay formula: min(base_delay * 2^(attempts - threshold), max_delay)
    - After 5 failures: 30s
    - After 6 failures: 60s
    - After 7 failures: 120s
    - After 8 failures: 240s
    - ... up to max_delay (1 hour)
    """

    def __init__(self, redis_url: str | None = None):
        """Initialize the lockout manager.

        Args:
            redis_url: Redis connection URL. If None, uses settings.
        """
        settings = get_settings()
        self._redis_url = redis_url or settings.redis_url
        self._redis: Redis | None = None

    async def _get_redis(self) -> Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = Redis.from_url(
                self._redis_url,
                decode_responses=True,
            )
        return self._redis

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._redis is not None:
            await self._redis.close()
            self._redis = None

    def _make_key(self, key_type: str, identifier: str) -> str:
        """Create a Redis key for lockout tracking.

        Args:
            key_type: "ip" or "email"
            identifier: The IP address or email

        Returns:
            Redis key string
        """
        return f"login_lockout:{key_type}:{identifier.lower()}"

    def _calculate_lockout_seconds(self, failed_attempts: int) -> int:
        """Calculate lockout duration based on failed attempt count.

        Uses exponential backoff after threshold is reached.

        Args:
            failed_attempts: Total failed attempts in window

        Returns:
            Lockout duration in seconds (0 if under threshold)
        """
        threshold = LOCKOUT_CONFIG["threshold"]
        if failed_attempts < threshold:
            return 0

        excess_attempts = failed_attempts - threshold
        base_delay = LOCKOUT_CONFIG["base_delay_seconds"]
        max_delay = LOCKOUT_CONFIG["max_delay_seconds"]

        # Exponential backoff: base * 2^excess
        delay = base_delay * (2**excess_attempts)
        return min(delay, max_delay)

    async def _get_attempt_count(self, redis: Redis, key: str) -> int:
        """Get the current failed attempt count for a key.

        Args:
            redis: Redis client
            key: Redis key to check

        Returns:
            Number of failed attempts in the current window
        """
        now = time.time()
        window_start = now - LOCKOUT_CONFIG["window_seconds"]

        # Count attempts in the current window
        count = await redis.zcount(key, window_start, now)
        return count

    async def _get_last_attempt_time(self, redis: Redis, key: str) -> float | None:
        """Get the timestamp of the most recent failed attempt.

        Args:
            redis: Redis client
            key: Redis key to check

        Returns:
            Timestamp of last attempt, or None if no attempts
        """
        # Get the most recent entry
        entries = await redis.zrange(key, -1, -1, withscores=True)
        if entries:
            return entries[0][1]
        return None

    async def check_lockout(
        self,
        ip: str | None = None,
        email: str | None = None,
    ) -> LockoutStatus:
        """Check if login is currently locked out.

        Checks both IP and email lockouts, returning the stricter one.

        Args:
            ip: Client IP address
            email: User email address

        Returns:
            LockoutStatus with lockout details
        """
        try:
            redis = await self._get_redis()
        except Exception as e:
            logger.warning(f"Login lockout check unavailable: {e}")
            # Graceful degradation: allow login if Redis unavailable
            return LockoutStatus(
                is_locked=False,
                retry_after=0,
                failed_attempts=0,
                threshold=LOCKOUT_CONFIG["threshold"],
            )

        now = time.time()
        max_attempts = 0
        max_retry_after = 0

        # Check IP lockout
        if ip:
            ip_key = self._make_key("ip", ip)
            ip_attempts = await self._get_attempt_count(redis, ip_key)
            max_attempts = max(max_attempts, ip_attempts)

            if ip_attempts >= LOCKOUT_CONFIG["threshold"]:
                last_attempt = await self._get_last_attempt_time(redis, ip_key)
                if last_attempt:
                    lockout_duration = self._calculate_lockout_seconds(ip_attempts)
                    lockout_ends = last_attempt + lockout_duration
                    if lockout_ends > now:
                        max_retry_after = max(max_retry_after, int(lockout_ends - now))

        # Check email lockout
        if email:
            email_key = self._make_key("email", email)
            email_attempts = await self._get_attempt_count(redis, email_key)
            max_attempts = max(max_attempts, email_attempts)

            if email_attempts >= LOCKOUT_CONFIG["threshold"]:
                last_attempt = await self._get_last_attempt_time(redis, email_key)
                if last_attempt:
                    lockout_duration = self._calculate_lockout_seconds(email_attempts)
                    lockout_ends = last_attempt + lockout_duration
                    if lockout_ends > now:
                        max_retry_after = max(max_retry_after, int(lockout_ends - now))

        return LockoutStatus(
            is_locked=max_retry_after > 0,
            retry_after=max_retry_after,
            failed_attempts=max_attempts,
            threshold=LOCKOUT_CONFIG["threshold"],
        )

    async def record_failure(
        self,
        ip: str | None = None,
        email: str | None = None,
    ) -> None:
        """Record a failed login attempt.

        Should be called after a failed authentication attempt.

        Args:
            ip: Client IP address
            email: User email address
        """
        try:
            redis = await self._get_redis()
        except Exception as e:
            logger.warning(f"Failed to record login failure: {e}")
            return

        now = time.time()
        window_seconds = LOCKOUT_CONFIG["window_seconds"]

        pipe = redis.pipeline()

        # Record IP failure
        if ip:
            ip_key = self._make_key("ip", ip)
            pipe.zremrangebyscore(ip_key, 0, now - window_seconds)  # Cleanup old
            pipe.zadd(ip_key, {str(now): now})
            pipe.expire(ip_key, window_seconds + 1)

        # Record email failure
        if email:
            email_key = self._make_key("email", email)
            pipe.zremrangebyscore(email_key, 0, now - window_seconds)  # Cleanup old
            pipe.zadd(email_key, {str(now): now})
            pipe.expire(email_key, window_seconds + 1)

        try:
            await pipe.execute()
            logger.info(
                "Recorded failed login attempt",
                extra={"ip": ip, "email": email[:3] + "***" if email else None},
            )
        except Exception as e:
            logger.warning(f"Failed to record login failure: {e}")

    async def reset(
        self,
        ip: str | None = None,
        email: str | None = None,
    ) -> None:
        """Reset failed attempt counters after successful login.

        Should be called after a successful authentication.

        Args:
            ip: Client IP address
            email: User email address
        """
        try:
            redis = await self._get_redis()
        except Exception as e:
            logger.warning(f"Failed to reset login lockout: {e}")
            return

        pipe = redis.pipeline()

        if ip:
            pipe.delete(self._make_key("ip", ip))

        if email:
            pipe.delete(self._make_key("email", email))

        try:
            await pipe.execute()
        except Exception as e:
            logger.warning(f"Failed to reset login lockout: {e}")


# Singleton lockout manager instance
_lockout_manager: LoginLockoutManager | None = None


def get_lockout_manager() -> LoginLockoutManager:
    """Get the singleton lockout manager instance."""
    global _lockout_manager
    if _lockout_manager is None:
        _lockout_manager = LoginLockoutManager()
    return _lockout_manager


class LoginLockoutExceeded(HTTPException):
    """Exception raised when login is locked out due to too many failed attempts."""

    def __init__(self, retry_after: int, failed_attempts: int):
        headers = {"Retry-After": str(retry_after)}
        detail = (
            f"Too many failed login attempts ({failed_attempts}). "
            f"Please try again in {retry_after} seconds."
        )
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers=headers,
        )


async def check_login_lockout(
    request: Request,
    email: str,
) -> None:
    """Check if login is locked out and raise exception if so.

    This should be called at the start of the login flow, before
    attempting authentication.

    Args:
        request: FastAPI request (for IP extraction)
        email: Email being used to login

    Raises:
        LoginLockoutExceeded: If login is currently locked out
    """
    from ace_platform.core.rate_limit import get_client_ip

    manager = get_lockout_manager()
    client_ip = get_client_ip(request)

    status = await manager.check_lockout(ip=client_ip, email=email)

    if status.is_locked:
        logger.warning(
            "Login locked out due to failed attempts",
            extra={
                "ip": client_ip,
                "email": email[:3] + "***" if email else None,
                "failed_attempts": status.failed_attempts,
                "retry_after": status.retry_after,
            },
        )
        raise LoginLockoutExceeded(
            retry_after=status.retry_after,
            failed_attempts=status.failed_attempts,
        )


async def record_login_failure(request: Request, email: str) -> None:
    """Record a failed login attempt.

    Should be called after authentication fails.

    Args:
        request: FastAPI request (for IP extraction)
        email: Email that failed to authenticate
    """
    from ace_platform.core.rate_limit import get_client_ip

    manager = get_lockout_manager()
    client_ip = get_client_ip(request)
    await manager.record_failure(ip=client_ip, email=email)


async def reset_login_lockout(request: Request, email: str) -> None:
    """Reset lockout counters after successful login.

    Should be called after successful authentication.

    Args:
        request: FastAPI request (for IP extraction)
        email: Email that successfully authenticated
    """
    from ace_platform.core.rate_limit import get_client_ip

    manager = get_lockout_manager()
    client_ip = get_client_ip(request)
    await manager.reset(ip=client_ip, email=email)
