"""FastAPI application for ACE Platform.

This module sets up the FastAPI application with:
- CORS middleware for cross-origin requests
- Correlation ID middleware for request tracing
- Request timing middleware for performance monitoring
- Global error handling
- Health check endpoints
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ace_platform.config import get_settings
from ace_platform.db.session import close_async_db

from .middleware import (
    CorrelationIdMiddleware,
    RequestTimingMiddleware,
    get_correlation_id,
    setup_logging_with_correlation_id,
)

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler.

    Sets up resources on startup and cleans up on shutdown.
    """
    # Startup
    log_level = logging.DEBUG if settings.debug else logging.INFO
    setup_logging_with_correlation_id(level=log_level)
    logger.info("ACE Platform API starting up")

    yield

    # Shutdown
    logger.info("ACE Platform API shutting down")
    await close_async_db()


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
    from ace_platform.api.routes import auth_router, playbooks_router

    # Include API routers
    app.include_router(auth_router)
    app.include_router(playbooks_router)

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


# Create the application instance
app = create_app()
