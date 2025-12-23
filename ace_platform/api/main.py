"""FastAPI application for ACE Platform.

This module sets up the FastAPI application with:
- CORS middleware for cross-origin requests
- Correlation ID middleware for request tracing
- Request timing middleware for performance monitoring
- Health check endpoints
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ace_platform.config import get_settings
from ace_platform.db.session import close_async_db

from .middleware import (
    CorrelationIdMiddleware,
    RequestTimingMiddleware,
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

    # Add CORS middleware first (outermost layer for responses)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID", "X-Process-Time"],
    )

    # Add request timing middleware
    app.add_middleware(RequestTimingMiddleware)

    # Add correlation ID middleware (innermost, runs first for requests)
    app.add_middleware(CorrelationIdMiddleware)

    # Register routes
    _register_routes(app)

    return app


def _register_routes(app: FastAPI) -> None:
    """Register all API routes.

    Args:
        app: The FastAPI application to register routes on.
    """

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
