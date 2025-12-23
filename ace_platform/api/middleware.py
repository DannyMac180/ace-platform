"""FastAPI middleware for request processing.

This module contains middleware for:
- Correlation ID generation and propagation
- Request timing
- Logging
"""

import logging
import time
import uuid
from collections.abc import Callable
from contextvars import ContextVar

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

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
