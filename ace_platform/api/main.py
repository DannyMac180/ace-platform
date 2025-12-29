"""FastAPI application for ACE Platform.

This module sets up the FastAPI application with:
- CORS middleware for cross-origin requests
- Correlation ID middleware for request tracing
- Request timing middleware for performance monitoring
- Global error handling
- Health check endpoints
- Sentry error tracking (when configured)
"""

import logging
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ace_platform.config import get_settings
from ace_platform.core.logging import get_logger, setup_logging
from ace_platform.db.session import close_async_db

from .middleware import (
    CorrelationIdMiddleware,
    RequestTimingMiddleware,
    get_correlation_id,
)

settings = get_settings()
logger = get_logger(__name__)


def _init_sentry() -> None:
    """Initialize Sentry error tracking if configured.

    Sentry is only initialized if SENTRY_DSN is set. This allows
    running without Sentry in development while enabling it in
    staging/production environments.
    """
    if not settings.sentry_dsn:
        logger.debug("Sentry DSN not configured, error tracking disabled")
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release="ace-platform@0.1.0",
        # Performance monitoring
        traces_sample_rate=settings.sentry_traces_sample_rate,
        profiles_sample_rate=settings.sentry_profiles_sample_rate,
        # Automatically capture breadcrumbs for logging, HTTP requests, etc.
        enable_tracing=True,
        # Don't send PII by default
        send_default_pii=False,
        # Filter out health check transactions
        traces_sampler=_traces_sampler,
    )
    logger.info(
        "Sentry error tracking initialized",
        extra={"environment": settings.environment},
    )


def _traces_sampler(sampling_context: dict) -> float:
    """Custom sampler to filter out noisy transactions.

    Args:
        sampling_context: Context about the transaction being sampled.

    Returns:
        Sample rate for this transaction (0.0 to 1.0).
    """
    # Don't trace health check endpoints
    transaction_context = sampling_context.get("transaction_context", {})
    name = transaction_context.get("name", "")

    if name in ("/health", "/ready", "/metrics"):
        return 0.0

    # Use default sample rate for everything else
    return settings.sentry_traces_sample_rate


# Initialize Sentry at module load time
_init_sentry()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler.

    Sets up resources on startup and cleans up on shutdown.
    """
    # Startup - configure structured logging
    log_level = None
    if settings.log_level:
        log_level = getattr(logging, settings.log_level.upper(), None)

    json_format = None
    if settings.log_format != "auto":
        json_format = settings.log_format == "json"

    setup_logging(level=log_level, json_format=json_format)
    logger.info("ACE Platform API starting up", extra={"environment": settings.environment})

    # Seed starter playbooks
    await _seed_starter_playbooks()

    yield

    # Shutdown
    logger.info("ACE Platform API shutting down")
    await close_async_db()


async def _seed_starter_playbooks() -> None:
    """Seed starter playbooks on startup.

    This runs during application startup to ensure starter playbooks
    are available in the database. It's idempotent - existing playbooks
    are skipped.
    """
    from ace_platform.db.seed import seed_starter_playbooks
    from ace_platform.db.session import async_session_context

    try:
        async with async_session_context() as db:
            results = await seed_starter_playbooks(db)
            if results["created"]:
                logger.info(f"Seeded {len(results['created'])} starter playbook(s)")
            if results["errors"]:
                logger.warning(f"Failed to seed {len(results['errors'])} playbook(s)")
    except Exception as e:
        # Don't fail startup if seeding fails
        logger.error(f"Error seeding starter playbooks: {e}")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(
        title="ACE Platform",
        description="Hosted Playbooks as a Service - "
        "A platform for self-improving AI agent playbooks",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
    )

    # Middleware execution order: last added = outermost (first for requests, last for responses)
    # Request flow:  CorrelationId → Timing → CORS → Route
    # Response flow: Route → CORS → Timing → CorrelationId
    #
    # This ensures the correlation ID context is available throughout the entire
    # request lifecycle, including when Timing middleware logs slow requests.

    # CORS middleware (innermost - handles preflight requests)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID", "X-Process-Time"],
    )

    # Request timing middleware (middle layer - can access correlation ID)
    app.add_middleware(RequestTimingMiddleware)

    # Correlation ID middleware (outermost - added last so context wraps everything)
    # The correlation ID remains available until after all inner middleware complete
    app.add_middleware(CorrelationIdMiddleware)

    # Register exception handlers
    _register_exception_handlers(app)

    # Register routes
    _register_routes(app)

    return app


def _register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers.

    Args:
        app: The FastAPI application to register handlers on.
    """

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        """Handle HTTP exceptions with consistent error format.

        Args:
            request: The incoming request.
            exc: The HTTP exception raised.

        Returns:
            JSONResponse with error details.
        """
        correlation_id = get_correlation_id() or "unknown"
        logger.warning(
            f"[{correlation_id}] HTTP {exc.status_code}: {exc.detail}",
            extra={"correlation_id": correlation_id, "status_code": exc.status_code},
        )
        response = JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "type": "http_error",
                    "message": exc.detail,
                    "status_code": exc.status_code,
                },
                "correlation_id": correlation_id,
            },
        )
        # Preserve any headers from the exception (e.g., WWW-Authenticate for 401)
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle request validation errors with detailed feedback.

        Args:
            request: The incoming request.
            exc: The validation exception raised.

        Returns:
            JSONResponse with validation error details.
        """
        correlation_id = get_correlation_id() or "unknown"
        errors = []
        for error in exc.errors():
            field = ".".join(str(loc) for loc in error["loc"])
            errors.append(
                {
                    "field": field,
                    "message": error["msg"],
                    "type": error["type"],
                }
            )

        logger.warning(
            f"[{correlation_id}] Validation error: {len(errors)} field(s) invalid",
            extra={"correlation_id": correlation_id, "validation_errors": errors},
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "type": "validation_error",
                    "message": "Request validation failed",
                    "details": errors,
                },
                "correlation_id": correlation_id,
            },
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle unhandled exceptions with safe error response.

        This handler catches all exceptions not handled by more specific handlers.
        It logs the full exception but returns a generic error message to avoid
        leaking sensitive information.

        Args:
            request: The incoming request.
            exc: The unhandled exception.

        Returns:
            JSONResponse with generic error message.
        """
        correlation_id = get_correlation_id() or "unknown"
        logger.exception(
            f"[{correlation_id}] Unhandled exception: {type(exc).__name__}",
            extra={"correlation_id": correlation_id},
        )

        # Capture to Sentry with context
        with sentry_sdk.push_scope() as scope:
            scope.set_tag("correlation_id", correlation_id)
            scope.set_context(
                "request",
                {
                    "url": str(request.url),
                    "method": request.method,
                    "headers": dict(request.headers),
                },
            )
            sentry_sdk.capture_exception(exc)

        # Don't leak exception details in production
        message = "An unexpected error occurred"
        if settings.debug:
            message = f"{type(exc).__name__}: {str(exc)}"

        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "type": "internal_error",
                    "message": message,
                },
                "correlation_id": correlation_id,
            },
        )


def _register_routes(app: FastAPI) -> None:
    """Register all API routes.

    Args:
        app: The FastAPI application to register routes on.
    """
    from ace_platform.api.routes import (
        auth_router,
        billing_router,
        playbooks_router,
        usage_router,
    )

    # Include API routers
    app.include_router(auth_router)
    app.include_router(billing_router)
    app.include_router(playbooks_router)
    app.include_router(usage_router)

    @app.get("/health", tags=["Health"])
    async def health_check():
        """Check if the API is running.

        Returns:
            Simple status message indicating the API is healthy.
        """
        return {"status": "healthy", "service": "ace-platform"}

    @app.get("/ready", tags=["Health"])
    async def readiness_check():
        """Check if the API is ready to serve requests.

        This endpoint verifies database connectivity.

        Returns:
            Status message with database connection status.
        """
        from ace_platform.db.session import async_session_context

        try:
            async with async_session_context() as db:
                await db.execute("SELECT 1")
            db_status = "connected"
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            db_status = "disconnected"

        return {
            "status": "ready" if db_status == "connected" else "not_ready",
            "database": db_status,
        }

    @app.get("/metrics", tags=["Monitoring"], include_in_schema=False)
    async def metrics():
        """Expose Prometheus metrics for scraping.

        Returns metrics in Prometheus text format for monitoring systems.
        This endpoint is excluded from OpenAPI docs for security.

        Returns:
            Prometheus-formatted metrics text.
        """
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
        from starlette.responses import Response

        # Import metrics module to ensure all metrics are registered
        from ace_platform.core import metrics as _  # noqa: F401

        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )


# Create the application instance
app = create_app()
