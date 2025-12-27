"""Rate limiting infrastructure for ACE Platform.

This module provides Redis-backed rate limiting with:
- Sliding window algorithm for accurate rate limiting
- Configurable limits per endpoint/action
- IP-based and user-based rate limiting
- FastAPI dependencies for easy integration

Rate limits defined:
- Login attempts: 5/minute per IP
- Outcome reporting: 100/hour per user
- Evolution triggering: 10/hour per playbook

Usage:
    from ace_platform.core.rate_limit import RateLimiter, rate_limit_login

    # As a dependency
    @router.post("/login")
    async def login(
        _: None = Depends(rate_limit_login),
    ):
        ...

    # Direct usage
    limiter = RateLimiter()
    allowed = await limiter.is_allowed("login", client_ip, limit=5, window_seconds=60)
"""

import logging
import time
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis

from ace_platform.config import get_settings

logger = logging.getLogger(__name__)

# Rate limit configurations
RATE_LIMITS = {
    "login": {"limit": 5, "window_seconds": 60},  # 5 per minute per IP
    "outcome": {"limit": 100, "window_seconds": 3600},  # 100 per hour per user
    "evolution": {"limit": 10, "window_seconds": 3600},  # 10 per hour per playbook
}


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""

    allowed: bool
    remaining: int
    reset_at: float
    limit: int


class RateLimitExceeded(HTTPException):
    """Exception raised when rate limit is exceeded."""

    def __init__(
        self,
        detail: str = "Rate limit exceeded",
        retry_after: int | None = None,
    ):
        headers = {}
        if retry_after is not None:
            headers["Retry-After"] = str(retry_after)

        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            headers=headers if headers else None,
        )


class RateLimiter:
    """Redis-backed rate limiter using sliding window algorithm.

    Uses a sorted set to track request timestamps within the window.
    This provides accurate rate limiting that smoothly slides over time.
    """

    def __init__(self, redis_url: str | None = None):
        """Initialize the rate limiter.

        Args:
            redis_url: Redis connection URL. If None, uses settings.
        """
        settings = get_settings()
        self._redis_url = redis_url or settings.redis_url
        self._redis: Redis | None = None

    async def _get_redis(self) -> Redis:
        """Get or create Redis connection.

        Returns:
            Redis client instance.
        """
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

    def _make_key(self, action: str, identifier: str) -> str:
        """Create a Redis key for rate limiting.

        Args:
            action: The action being rate limited (e.g., "login").
            identifier: The identifier for the rate limit (e.g., IP or user ID).

        Returns:
            The Redis key for this rate limit bucket.
        """
        return f"ratelimit:{action}:{identifier}"

    async def check(
        self,
        action: str,
        identifier: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        """Check rate limit without consuming a request.

        Args:
            action: The action being rate limited.
            identifier: The identifier for the rate limit.
            limit: Maximum requests allowed in the window.
            window_seconds: Time window in seconds.

        Returns:
            RateLimitResult with current status.
        """
        redis = await self._get_redis()
        key = self._make_key(action, identifier)
        now = time.time()
        window_start = now - window_seconds

        # Count requests in the current window
        count = await redis.zcount(key, window_start, now)

        remaining = max(0, limit - count)
        allowed = count < limit

        # Calculate reset time (when oldest request expires)
        if count > 0:
            oldest = await redis.zrange(key, 0, 0, withscores=True)
            if oldest:
                reset_at = oldest[0][1] + window_seconds
            else:
                reset_at = now + window_seconds
        else:
            reset_at = now + window_seconds

        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_at=reset_at,
            limit=limit,
        )

    async def is_allowed(
        self,
        action: str,
        identifier: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitResult:
        """Check and consume a rate limit request.

        This is the main method for rate limiting. It checks if the request
        is allowed and records the request in the sliding window.

        Args:
            action: The action being rate limited.
            identifier: The identifier for the rate limit.
            limit: Maximum requests allowed in the window.
            window_seconds: Time window in seconds.

        Returns:
            RateLimitResult with updated status.

        Example:
            result = await limiter.is_allowed("login", "192.168.1.1", limit=5, window_seconds=60)
            if not result.allowed:
                raise RateLimitExceeded(retry_after=int(result.reset_at - time.time()))
        """
        redis = await self._get_redis()
        key = self._make_key(action, identifier)
        now = time.time()
        window_start = now - window_seconds

        # Use pipeline for atomic operations
        pipe = redis.pipeline()

        # Remove expired entries
        pipe.zremrangebyscore(key, 0, window_start)

        # Count current entries
        pipe.zcard(key)

        # Execute the pipeline
        results = await pipe.execute()
        current_count = results[1]

        if current_count >= limit:
            # Rate limit exceeded
            oldest = await redis.zrange(key, 0, 0, withscores=True)
            reset_at = oldest[0][1] + window_seconds if oldest else now + window_seconds

            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=reset_at,
                limit=limit,
            )

        # Add the new request
        pipe = redis.pipeline()
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, window_seconds + 1)  # TTL slightly longer than window
        await pipe.execute()

        return RateLimitResult(
            allowed=True,
            remaining=limit - current_count - 1,
            reset_at=now + window_seconds,
            limit=limit,
        )


# Singleton rate limiter instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get the singleton rate limiter instance.

    Returns:
        The global RateLimiter instance.
    """
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request.

    Handles X-Forwarded-For header for requests behind proxies.

    Args:
        request: The incoming request.

    Returns:
        The client's IP address.
    """
    # Check for forwarded IP (when behind proxy/load balancer)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take the first IP in the chain (original client)
        return forwarded.split(",")[0].strip()

    # Fall back to direct client IP
    if request.client:
        return request.client.host

    return "unknown"


async def _check_rate_limit(
    request: Request,
    action: str,
    identifier: str,
    limit: int,
    window_seconds: int,
) -> None:
    """Check rate limit and raise exception if exceeded.

    Args:
        request: The incoming request.
        action: The action being rate limited.
        identifier: The identifier for the rate limit.
        limit: Maximum requests allowed.
        window_seconds: Time window in seconds.

    Raises:
        RateLimitExceeded: If rate limit is exceeded.
    """
    limiter = get_rate_limiter()

    try:
        result = await limiter.is_allowed(action, identifier, limit, window_seconds)
    except Exception as e:
        # If Redis is unavailable, log and allow the request
        logger.warning(f"Rate limiting unavailable: {e}")
        return

    if not result.allowed:
        retry_after = int(result.reset_at - time.time())
        logger.warning(
            f"Rate limit exceeded for {action}:{identifier}",
            extra={
                "action": action,
                "identifier": identifier,
                "limit": limit,
                "window_seconds": window_seconds,
            },
        )
        raise RateLimitExceeded(
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            retry_after=retry_after,
        )

    # Add rate limit headers to response (via request state)
    request.state.rate_limit_remaining = result.remaining
    request.state.rate_limit_limit = result.limit
    request.state.rate_limit_reset = int(result.reset_at)


async def rate_limit_login(request: Request) -> None:
    """Rate limit dependency for login attempts.

    Limits to 5 requests per minute per IP address.

    Args:
        request: The incoming request.

    Raises:
        RateLimitExceeded: If rate limit is exceeded.
    """
    client_ip = get_client_ip(request)
    config = RATE_LIMITS["login"]
    await _check_rate_limit(
        request,
        action="login",
        identifier=client_ip,
        limit=config["limit"],
        window_seconds=config["window_seconds"],
    )


async def rate_limit_outcome(request: Request, user_id: str) -> None:
    """Rate limit dependency for outcome reporting.

    Limits to 100 requests per hour per user.

    Args:
        request: The incoming request.
        user_id: The authenticated user's ID.

    Raises:
        RateLimitExceeded: If rate limit is exceeded.
    """
    config = RATE_LIMITS["outcome"]
    await _check_rate_limit(
        request,
        action="outcome",
        identifier=user_id,
        limit=config["limit"],
        window_seconds=config["window_seconds"],
    )


async def rate_limit_evolution(request: Request, playbook_id: str) -> None:
    """Rate limit dependency for evolution triggering.

    Limits to 10 requests per hour per playbook.

    Args:
        request: The incoming request.
        playbook_id: The playbook's ID.

    Raises:
        RateLimitExceeded: If rate limit is exceeded.
    """
    config = RATE_LIMITS["evolution"]
    await _check_rate_limit(
        request,
        action="evolution",
        identifier=playbook_id,
        limit=config["limit"],
        window_seconds=config["window_seconds"],
    )


# Type aliases for dependency injection
RateLimitLogin = Annotated[None, Depends(rate_limit_login)]
