"""FastAPI middleware for request processing.

This module contains middleware for:
- Correlation ID generation and propagation
- Request timing
- Security headers
- CSRF protection
- Logging
"""

import logging
import secrets
import time
import uuid
from collections.abc import Callable
from contextvars import ContextVar

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# CSRF token configuration
CSRF_TOKEN_LENGTH = 32
CSRF_TOKEN_HEADER = "X-CSRF-Token"
CSRF_TOKEN_SESSION_KEY = "_csrf_token"

# Context variable for correlation ID - accessible anywhere in the request context
correlation_id_ctx: ContextVar[str | None] = ContextVar("correlation_id", default=None)

# Header names for correlation ID
CORRELATION_ID_HEADER = "X-Correlation-ID"
REQUEST_ID_HEADER = "X-Request-ID"

logger = logging.getLogger(__name__)


def get_correlation_id() -> str | None:
    """Get the current correlation ID from context.

    Returns:
        The correlation ID for the current request, or None if not in a request context.

    Usage:
        from ace_platform.api.middleware import get_correlation_id

        correlation_id = get_correlation_id()
        logger.info(f"[{correlation_id}] Processing request")
    """
    return correlation_id_ctx.get()


def generate_correlation_id() -> str:
    """Generate a new correlation ID.

    Returns:
        A new UUID string for use as a correlation ID.
    """
    return str(uuid.uuid4())


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token.

    Returns:
        A URL-safe random token string.
    """
    return secrets.token_urlsafe(CSRF_TOKEN_LENGTH)


def get_csrf_token_from_session(request: Request) -> str | None:
    """Get the CSRF token from the session.

    Args:
        request: The incoming request with session.

    Returns:
        The CSRF token if present, None otherwise.
    """
    if not hasattr(request, "session"):
        return None
    return request.session.get(CSRF_TOKEN_SESSION_KEY)


def ensure_csrf_token(request: Request) -> str:
    """Ensure a CSRF token exists in the session, creating one if needed.

    Args:
        request: The incoming request with session.

    Returns:
        The existing or newly created CSRF token.
    """
    token = get_csrf_token_from_session(request)
    if not token:
        token = generate_csrf_token()
        request.session[CSRF_TOKEN_SESSION_KEY] = token
    return token


def validate_csrf_token_value(
    request: Request,
    provided_token: str | None,
    *,
    consume_token: bool = False,
    error_detail_missing_session: str = "CSRF token missing from session. Please refresh and try again.",
    error_detail_missing_token: str = "CSRF token missing from request.",
    error_detail_mismatch: str = "CSRF token validation failed.",
) -> None:
    """Validate a provided CSRF token against the session token.

    This is the core CSRF validation function. It can be used for different
    token sources (headers, query params, form data) by passing the token value.

    Args:
        request: The incoming request with session.
        provided_token: The CSRF token provided by the client.
        consume_token: If True, delete the token from session after validation (single-use).
        error_detail_missing_session: Custom error message when no token in session.
        error_detail_missing_token: Custom error message when no token provided.
        error_detail_mismatch: Custom error message when tokens don't match.

    Raises:
        HTTPException: If CSRF validation fails.
    """
    session_token = get_csrf_token_from_session(request)
    if not session_token:
        logger.warning(
            "CSRF validation failed: no token in session",
            extra={"correlation_id": get_correlation_id()},
        )
        raise HTTPException(
            status_code=403,
            detail=error_detail_missing_session,
        )

    if not provided_token:
        logger.warning(
            "CSRF validation failed: no token provided",
            extra={"correlation_id": get_correlation_id()},
        )
        raise HTTPException(
            status_code=403,
            detail=error_detail_missing_token,
        )

    # Use constant-time comparison to prevent timing attacks
    if not secrets.compare_digest(session_token, provided_token):
        logger.warning(
            "CSRF validation failed: token mismatch",
            extra={"correlation_id": get_correlation_id()},
        )
        raise HTTPException(
            status_code=403,
            detail=error_detail_mismatch,
        )

    # Optionally consume the token (for single-use scenarios like OAuth)
    if consume_token:
        del request.session[CSRF_TOKEN_SESSION_KEY]


async def validate_csrf_token(request: Request) -> None:
    """Validate the CSRF token from the request header matches the session.

    This should be called on state-changing operations that use session-based auth.
    For OAuth flows that need single-use tokens, use validate_csrf_token_value directly.

    Args:
        request: The incoming request.

    Raises:
        HTTPException: If CSRF validation fails.
    """
    header_token = request.headers.get(CSRF_TOKEN_HEADER)
    validate_csrf_token_value(
        request,
        header_token,
        error_detail_missing_token="CSRF token missing from request header.",
    )


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware that adds correlation IDs to requests.

    This middleware:
    1. Checks for an existing correlation ID in request headers (X-Correlation-ID or X-Request-ID)
    2. Generates a new UUID if no correlation ID is present
    3. Stores the correlation ID in a context variable for logging
    4. Adds the correlation ID to response headers

    The correlation ID can be used to trace requests across services and in logs.
    """

    def __init__(self, app: ASGIApp):
        """Initialize the middleware.

        Args:
            app: The ASGI application to wrap.
        """
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process the request and add correlation ID.

        Args:
            request: The incoming request.
            call_next: The next middleware or route handler.

        Returns:
            The response with correlation ID header added.
        """
        # Try to get correlation ID from headers (check both common header names)
        correlation_id = (
            request.headers.get(CORRELATION_ID_HEADER)
            or request.headers.get(REQUEST_ID_HEADER)
            or generate_correlation_id()
        )

        # Set the correlation ID in the context variable
        token = correlation_id_ctx.set(correlation_id)

        try:
            # Log the request with correlation ID
            logger.debug(
                f"[{correlation_id}] {request.method} {request.url.path}",
                extra={"correlation_id": correlation_id},
            )

            # Process the request
            response = await call_next(request)

            # Add correlation ID to response headers
            response.headers[CORRELATION_ID_HEADER] = correlation_id

            return response
        finally:
            # Reset the context variable
            correlation_id_ctx.reset(token)


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Middleware that adds request timing information.

    Adds X-Process-Time header with the request processing duration in seconds.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process the request and add timing header.

        Args:
            request: The incoming request.
            call_next: The next middleware or route handler.

        Returns:
            The response with X-Process-Time header added.
        """
        start_time = time.perf_counter()
        response = await call_next(request)
        process_time = time.perf_counter() - start_time

        # Add timing header (in seconds, with microsecond precision)
        response.headers["X-Process-Time"] = f"{process_time:.6f}"

        # Log slow requests
        correlation_id = get_correlation_id() or "unknown"
        if process_time > 1.0:
            logger.warning(
                f"[{correlation_id}] Slow request: {request.method} {request.url.path} "
                f"took {process_time:.3f}s",
                extra={"correlation_id": correlation_id, "process_time": process_time},
            )

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware that adds security headers to all responses.

    This middleware adds standard security headers to protect against common
    web vulnerabilities:

    - Strict-Transport-Security (HSTS): Forces HTTPS connections
    - X-Content-Type-Options: Prevents MIME-type sniffing
    - X-Frame-Options: Prevents clickjacking attacks
    - X-XSS-Protection: Legacy XSS protection (for older browsers)
    - Referrer-Policy: Controls referrer information leakage
    - Content-Security-Policy: Restricts resource loading (configurable)
    - Permissions-Policy: Disables unnecessary browser features

    Note: For API-only services, some headers like CSP are less critical
    but still good practice for defense in depth.
    """

    def __init__(
        self,
        app: ASGIApp,
        enable_hsts: bool = True,
        hsts_max_age: int = 31536000,
        hsts_include_subdomains: bool = True,
        content_security_policy: str | None = None,
    ):
        """Initialize the security headers middleware.

        Args:
            app: The ASGI application to wrap.
            enable_hsts: Whether to enable HSTS (disable for local development).
            hsts_max_age: HSTS max-age in seconds (default: 1 year).
            hsts_include_subdomains: Include subdomains in HSTS.
            content_security_policy: Custom CSP header value, or None for default.
        """
        super().__init__(app)
        self.enable_hsts = enable_hsts
        self.hsts_max_age = hsts_max_age
        self.hsts_include_subdomains = hsts_include_subdomains
        self.content_security_policy = content_security_policy or "default-src 'self'"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process the request and add security headers to the response.

        Args:
            request: The incoming request.
            call_next: The next middleware or route handler.

        Returns:
            The response with security headers added.
        """
        response = await call_next(request)

        # Strict-Transport-Security (HSTS)
        # Only enable in production to avoid issues with local development
        if self.enable_hsts:
            hsts_value = f"max-age={self.hsts_max_age}"
            if self.hsts_include_subdomains:
                hsts_value += "; includeSubDomains"
            response.headers["Strict-Transport-Security"] = hsts_value

        # Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Legacy XSS protection for older browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content Security Policy
        response.headers["Content-Security-Policy"] = self.content_security_policy

        # Permissions Policy - disable unnecessary browser features
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
            "magnetometer=(), microphone=(), payment=(), usb=()"
        )

        return response


class CorrelationIdFilter(logging.Filter):
    """Logging filter that adds correlation ID to log records.

    This filter adds the correlation_id attribute to all log records,
    making it available for formatters to include in log output.

    Usage:
        import logging

        handler = logging.StreamHandler()
        handler.addFilter(CorrelationIdFilter())
        handler.setFormatter(
            logging.Formatter('[%(correlation_id)s] %(levelname)s - %(message)s')
        )
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Add correlation ID to the log record.

        Args:
            record: The log record to modify.

        Returns:
            Always returns True to allow the record through.
        """
        record.correlation_id = get_correlation_id() or "-"
        return True


def setup_logging_with_correlation_id(
    level: int = logging.INFO,
    format_string: str | None = None,
) -> None:
    """Configure logging to include correlation IDs.

    Args:
        level: The logging level to use.
        format_string: Custom format string. If None, uses a default format
            that includes the correlation ID.

    Usage:
        from ace_platform.api.middleware import setup_logging_with_correlation_id

        setup_logging_with_correlation_id(level=logging.DEBUG)
    """
    if format_string is None:
        format_string = (
            "%(asctime)s [%(correlation_id)s] %(levelname)s %(name)s:%(lineno)d - %(message)s"
        )

    # Create handler with correlation ID filter
    handler = logging.StreamHandler()
    handler.addFilter(CorrelationIdFilter())
    handler.setFormatter(logging.Formatter(format_string))

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)
