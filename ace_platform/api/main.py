"""FastAPI application for ACE Platform.

This module sets up the FastAPI application with:
- CORS middleware for cross-origin requests
- Correlation ID middleware for request tracing
- Request timing middleware for performance monitoring
- Global error handling
- Health check endpoints
- MCP server integration (SSE transport)
- Sentry error tracking (when configured)
"""

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import sentry_sdk
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from ace_platform.config import get_settings
from ace_platform.core.logging import get_logger, setup_logging
from ace_platform.core.sentry_bootstrap import (
    get_effective_traces_sample_rate,
    init_sentry_for_process,
)
from ace_platform.core.sentry_context import sanitize_request_headers
from ace_platform.db.session import close_async_db

from .middleware import (
    CorrelationIdMiddleware,
    RequestTimingMiddleware,
    SecurityHeadersMiddleware,
    get_correlation_id,
)

settings = get_settings()
logger = get_logger(__name__)
LANDING_VIDEO_PATH = Path(__file__).resolve().parent.parent / "static" / "landing-hero-video.mp4"
LANDING_FAVICON_PATH = Path(__file__).resolve().parent.parent / "static" / "ace-favicon.svg"


def _init_sentry() -> None:
    """Initialize Sentry error tracking for the API process."""
    init_sentry_for_process(
        process_name="api",
        settings=settings,
        traces_sampler=_traces_sampler,
        enable_tracing=True,
        send_default_pii=False,
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

    # Use the resolved API sample rate for everything else
    return get_effective_traces_sample_rate(settings, process_name="api")


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

    # Warn if JWT secret key is still the default value
    if (
        settings.jwt_secret_key == "change-me-in-production"
        and settings.environment != "development"
    ):
        logger.critical(
            "JWT_SECRET_KEY is using the default value in '%s' environment. "
            "Set a secure JWT_SECRET_KEY environment variable before serving traffic.",
            settings.environment,
        )

    # Seed starter playbooks
    await _seed_starter_playbooks()

    # Setup OAuth clients
    from ace_platform.core.oauth import setup_oauth

    setup_oauth()
    logger.info("OAuth clients configured")

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
    # Request flow:  CorrelationId → Timing → Security → CORS → Session → Route
    # Response flow: Route → Session → CORS → Security → Timing → CorrelationId
    #
    # This ensures the correlation ID context is available throughout the entire
    # request lifecycle, including when Timing middleware logs slow requests.

    # Session middleware (innermost - required for OAuth state)
    # Uses dedicated session secret for security isolation from JWT tokens
    # For cross-subdomain deployments (e.g., app.aceagent.io + aceagent.io), requires:
    #   SESSION_COOKIE_DOMAIN=.aceagent.io (note the leading dot)
    #   SESSION_COOKIE_SAMESITE=lax (or 'none' for true cross-origin)
    #   SESSION_COOKIE_SECURE=true (required for production HTTPS)
    session_secret = settings.session_secret_key or settings.jwt_secret_key
    session_kwargs: dict = {
        "secret_key": session_secret,
        "max_age": 600,  # 10 minutes for OAuth flow
        "same_site": settings.session_cookie_samesite,
        "https_only": settings.session_cookie_secure,
    }
    # Only set domain if explicitly configured (empty string = use default)
    if settings.session_cookie_domain:
        session_kwargs["domain"] = settings.session_cookie_domain
    app.add_middleware(SessionMiddleware, **session_kwargs)

    # CORS middleware (handles preflight requests)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-Correlation-ID"],
        expose_headers=["X-Correlation-ID", "X-Process-Time"],
    )

    # Security headers middleware (adds security headers to all responses)
    if settings.security_headers_enabled:
        app.add_middleware(
            SecurityHeadersMiddleware,
            enable_hsts=settings.security_hsts_enabled,
            hsts_max_age=settings.security_hsts_max_age,
            content_security_policy=settings.security_csp,
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
        with sentry_sdk.new_scope() as scope:
            scope.set_tag("correlation_id", correlation_id)
            scope.set_context(
                "request",
                {
                    "url": str(request.url),
                    "method": request.method,
                    "headers": sanitize_request_headers(dict(request.headers)),
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
        account_router,
        admin_router,
        auth_router,
        billing_router,
        evolutions_router,
        oauth_router,
        playbooks_router,
        support_router,
        usage_router,
    )

    # Include API routers
    app.include_router(auth_router)
    app.include_router(account_router)
    app.include_router(admin_router)
    app.include_router(oauth_router)
    app.include_router(billing_router)
    app.include_router(playbooks_router)
    app.include_router(usage_router)
    app.include_router(evolutions_router)
    app.include_router(support_router)

    # Mount MCP server at /mcp for SSE transport
    # This allows clients to connect to the MCP server via the same domain as the API
    # using: https://aceagent.io/mcp/sse
    #
    # The HeaderAuthMiddleware wraps the MCP app to extract API keys from HTTP headers:
    # - X-API-Key: <api_key>
    # - Authorization: Bearer <api_key>
    #
    # This allows Claude Code users to configure authentication in their MCP settings:
    # {
    #   "mcpServers": {
    #     "ace": {
    #       "type": "sse",
    #       "url": "https://aceagent.io/mcp/sse",
    #       "headers": { "X-API-Key": "your-api-key" }
    #     }
    #   }
    # }
    from ace_platform.mcp.server import (
        FlyReplayMiddleware,
        HeaderAuthMiddleware,
        SSEDisconnectMiddleware,
    )
    from ace_platform.mcp.server import mcp as mcp_server

    mcp_sse_app = mcp_server.sse_app()
    mcp_sse_app_with_auth = HeaderAuthMiddleware(mcp_sse_app)
    mcp_sse_app_with_disconnect = SSEDisconnectMiddleware(mcp_sse_app_with_auth)
    mcp_sse_app_with_replay = FlyReplayMiddleware(mcp_sse_app_with_disconnect)
    app.mount("/mcp", app=mcp_sse_app_with_replay, name="mcp")

    # OAuth discovery endpoints - return OAuth-spec-compatible 404 responses.
    # Claude Code's MCP client performs OAuth discovery (RFC 9728) before
    # connecting to SSE endpoints. FastAPI's default 404 body {"detail":"Not Found"}
    # doesn't match the expected OAuth error format {"error":"..."}, causing a
    # ZodError in the client. These endpoints return spec-compliant 404s.
    @app.get("/.well-known/oauth-protected-resource")
    @app.get("/.well-known/oauth-authorization-server")
    async def well_known_oauth_not_found():
        return JSONResponse(
            {
                "error": "invalid_request",
                "error_description": "OAuth is not supported by this server",
            },
            status_code=404,
        )

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
        Returns 200 if ready, 503 Service Unavailable if not.

        Returns:
            Status message with database connection status.
        """
        from ace_platform.db.session import async_session_context

        try:
            from sqlalchemy import text

            async with async_session_context() as db:
                await db.execute(text("SELECT 1"))
            db_status = "connected"
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "database": "disconnected",
                },
            )

        return {
            "status": "ready",
            "database": db_status,
        }

    @app.get("/metrics", tags=["Monitoring"], include_in_schema=False)
    async def metrics(request: Request):
        """Expose Prometheus metrics for scraping.

        Returns metrics in Prometheus text format for monitoring systems.
        This endpoint is excluded from OpenAPI docs for security.
        When METRICS_AUTH_TOKEN is set, requires Bearer token authentication.

        Returns:
            Prometheus-formatted metrics text.
        """
        if settings.metrics_auth_token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header != f"Bearer {settings.metrics_auth_token}":
                return JSONResponse(
                    status_code=401,
                    content={"error": "Unauthorized"},
                )

        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
        from starlette.responses import Response

        # Import metrics module to ensure all metrics are registered
        from ace_platform.core import metrics as _  # noqa: F401

        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )

    @app.get("/landing-hero-video.mp4", include_in_schema=False)
    async def landing_video():
        """Serve landing page hero video from same origin."""
        if not LANDING_VIDEO_PATH.exists():
            raise HTTPException(status_code=404, detail="Landing video not found")
        return FileResponse(
            LANDING_VIDEO_PATH,
            media_type="video/mp4",
            filename="landing-hero-video.mp4",
        )

    @app.get("/ace-favicon.svg", include_in_schema=False)
    async def landing_favicon():
        """Serve landing page favicon from same origin."""
        if not LANDING_FAVICON_PATH.exists():
            raise HTTPException(status_code=404, detail="Landing favicon not found")
        return FileResponse(
            LANDING_FAVICON_PATH,
            media_type="image/svg+xml",
            filename="ace-favicon.svg",
        )

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon_ico():
        """Redirect browser default favicon requests to the SVG favicon."""
        return RedirectResponse(url="/ace-favicon.svg", status_code=307)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def landing_page():
        """Serve the landing page."""
        frontend_url = settings.frontend_url.rstrip("/")
        docs_url = settings.docs_url.rstrip("/")
        current_year = datetime.now(UTC).year
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/svg+xml" href="/ace-favicon.svg">
    <link rel="shortcut icon" href="/favicon.ico">
    <title>ACE</title>
    <meta name="description" content="ACE helps individual developers and knowledge workers improve AI output quality continuously by evolving playbooks from real outcomes.">
    <style>
        :root {
            --bg-primary: #fdfcfa;
            --bg-secondary: #f5f3ee;
            --bg-surface: #ffffff;
            --bg-soft: rgba(255, 255, 255, 0.85);
            --ink-primary: #1a1a1a;
            --text-secondary: #4a4a4a;
            --text-tertiary: #7a7a7a;
            --accent-primary: #c41e3a;
            --accent-secondary: #a31830;
            --gold-primary: #b8860b;
            --success: #1e7a4d;
            --border-default: rgba(0, 0, 0, 0.12);
            --border-soft: rgba(0, 0, 0, 0.08);
            --border-gold: rgba(184, 134, 11, 0.4);
            --shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.08);
            --shadow-md: 0 8px 24px rgba(0, 0, 0, 0.1);
            --font-display: "Palatino Linotype", Palatino, "Book Antiqua", Cambria, Georgia, "Times New Roman", serif;
            --font-body: "Baskerville", "Garamond", "Times New Roman", Times, serif;
        }

        * { margin: 0; padding: 0; box-sizing: border-box; }
        html { font-size: 16px; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
        body {
            font-family: var(--font-body);
            font-size: 1.0625rem;
            line-height: 1.65;
            color: var(--ink-primary);
            background: var(--bg-primary);
        }
        body::before,
        body::after {
            content: '';
            position: fixed;
            inset: 0;
            pointer-events: none;
            z-index: 0;
        }
        body::before {
            background-image: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M30 0L30 60M0 30L60 30M0 0L60 60M60 0L0 60' stroke='%23000000' stroke-width='0.2' fill='none' opacity='0.02'/%3E%3C/svg%3E");
            opacity: 0.45;
        }
        body::after {
            background:
              radial-gradient(circle at 10% 5%, rgba(184, 134, 11, 0.14), transparent 32%),
              radial-gradient(circle at 90% 95%, rgba(196, 30, 58, 0.14), transparent 30%);
        }

        .page {
            position: relative;
            z-index: 1;
            max-width: 1200px;
            margin: 0 auto;
            padding: 1.25rem 1.25rem 1.25rem;
        }

        a {
            color: var(--accent-primary);
            text-decoration: none;
            transition: color 150ms ease;
        }
        a:hover { color: var(--accent-secondary); }

        h1, h2, h3 {
            font-family: var(--font-display);
            color: var(--ink-primary);
            line-height: 1.2;
            letter-spacing: -0.01em;
        }
        p { color: var(--text-secondary); }

        .nav {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            padding: 0.5rem 0;
        }
        .brand {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            text-decoration: none;
            color: var(--ink-primary);
        }
        .brand:hover { color: var(--ink-primary); }
        .brand-logo {
            width: 40px;
            height: 56px;
            flex-shrink: 0;
        }
        .brand-title {
            font-family: var(--font-display);
            font-weight: 700;
            font-size: 1.05rem;
            line-height: 1;
        }

        .nav-links {
            display: flex;
            align-items: center;
            gap: 1rem;
            flex-wrap: wrap;
            justify-content: flex-end;
        }
        .nav-links a {
            font-family: var(--font-display);
            font-weight: 500;
            font-size: 0.95rem;
            color: var(--text-secondary);
        }
        .nav-links a:hover { color: var(--ink-primary); }

        .action {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            border-radius: 10px;
            padding: 0.66rem 1.1rem;
            font-size: 0.82rem;
            font-weight: 600;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            border: 1px solid var(--border-default);
            color: var(--ink-primary);
            background: var(--bg-surface);
        }
        .action:hover { background: var(--bg-secondary); color: var(--ink-primary); }
        .action.primary {
            background: linear-gradient(145deg, var(--accent-primary), var(--accent-secondary));
            color: #fff;
            border-color: transparent;
            box-shadow: var(--shadow-sm);
        }
        .action.primary:hover { color: #fff; box-shadow: 0 4px 12px rgba(196, 30, 58, 0.3); }

        .hero {
            margin-top: 2rem;
            display: grid;
            grid-template-columns: 1.1fr 1fr;
            gap: 2rem;
            align-items: center;
        }
        .eyebrow {
            display: inline-flex;
            max-width: fit-content;
            border-radius: 999px;
            padding: 0.3rem 0.75rem;
            background: rgba(184, 134, 11, 0.1);
            color: var(--text-secondary);
            font-size: 0.92rem;
            margin-bottom: 1rem;
        }
        .hero h1 {
            font-size: 3.75rem;
            line-height: 1.08;
            max-width: 16ch;
        }
        .hero-subhead {
            margin-top: 1rem;
            font-size: 1.55rem;
            max-width: 48ch;
        }
        .hero-actions {
            display: flex;
            flex-wrap: wrap;
            gap: 0.7rem;
            margin-top: 1.35rem;
        }
        .micro-copy {
            margin-top: 0.85rem;
            color: var(--text-tertiary);
            font-size: 1.02rem;
        }

        .hero-visual {
            border: 1px solid var(--border-gold);
            border-radius: 16px;
            background: linear-gradient(160deg, rgba(255, 255, 255, 0.92), rgba(250, 246, 240, 0.97));
            box-shadow: var(--shadow-md);
            padding: 1rem;
            display: grid;
            gap: 0.9rem;
        }
        .hero-video {
            width: 100%;
            aspect-ratio: 16 / 9;
            border-radius: 10px;
            border: 1px solid var(--border-default);
            background: var(--bg-secondary);
            object-fit: cover;
        }
        .metric-panel {
            border-radius: 10px;
            border: 1px solid var(--border-default);
            background: var(--bg-surface);
            padding: 1rem;
        }
        .metric-panel p:first-child {
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-size: 0.82rem;
            color: var(--text-tertiary);
            margin-bottom: 0.3rem;
        }
        .metric-panel strong {
            display: block;
            font-family: var(--font-display);
            font-size: 1.85rem;
            color: var(--ink-primary);
        }
        .metric-panel p:last-child {
            margin-top: 0.2rem;
            font-size: 1.08rem;
            color: var(--text-secondary);
        }

        .trust-strip {
            margin-top: 2rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            flex-wrap: wrap;
            padding: 1rem;
            border-radius: 12px;
            border: 1px solid var(--border-default);
            background: rgba(255, 255, 255, 0.75);
        }
        .badges {
            display: flex;
            gap: 0.5rem;
            flex-wrap: wrap;
        }
        .badges span {
            padding: 0.35rem 0.7rem;
            border-radius: 999px;
            border: 1px solid var(--border-default);
            background: var(--bg-surface);
            color: var(--ink-primary);
            font-size: 0.9rem;
        }

        .grid-2 {
            margin-top: 2rem;
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 1rem;
        }
        .panel {
            border-radius: 12px;
            border: 1px solid var(--border-default);
            background: var(--bg-soft);
            padding: 1.25rem;
        }
        .panel h2 {
            font-size: 2.1rem;
            margin-bottom: 0.75rem;
        }
        .panel ul {
            list-style: none;
            display: grid;
            gap: 0.45rem;
        }
        .panel li {
            position: relative;
            padding-left: 1rem;
        }
        .panel li::before {
            content: "•";
            position: absolute;
            left: 0;
            color: var(--accent-primary);
        }

        section {
            margin-top: 3rem;
        }
        .section-title {
            font-size: 2.75rem;
            margin-bottom: 0.35rem;
        }
        .section-subtitle {
            font-size: 1.15rem;
            margin-bottom: 1rem;
        }

        .cards-3 {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 1rem;
        }
        .cards-2 {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 1rem;
        }
        .card {
            border-radius: 12px;
            border: 1px solid var(--border-default);
            background: var(--bg-surface);
            padding: 1.1rem;
            box-shadow: var(--shadow-sm);
        }
        .card h3 {
            font-size: 1.7rem;
            margin-bottom: 0.45rem;
        }
        .card p {
            font-size: 1.05rem;
        }

        .metric-label {
            color: var(--text-tertiary);
            text-transform: uppercase;
            font-size: 0.78rem;
            letter-spacing: 0.08em;
        }

        .control-list {
            display: grid;
            gap: 0.6rem;
        }
        .control-list p {
            border-left: 3px solid var(--border-default);
            padding-left: 0.9rem;
        }

        .price-card ul {
            margin-top: 0.7rem;
            padding-left: 1rem;
            display: grid;
            gap: 0.2rem;
            color: var(--text-secondary);
        }
        .price {
            font-family: var(--font-display);
            color: var(--ink-primary);
            font-size: 3rem;
            line-height: 1.1;
            margin-bottom: 0.1rem;
        }
        .yearly {
            font-size: 0.95rem;
            color: var(--text-secondary);
            display: inline-flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.3rem;
            margin-bottom: 0.4rem;
        }
        .yearly span {
            display: inline-flex;
            align-items: center;
            border-radius: 4px;
            border: 1px solid rgba(30, 122, 77, 0.35);
            background: rgba(30, 122, 77, 0.1);
            color: var(--success);
            font-size: 0.72rem;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            font-weight: 700;
            padding: 0.1rem 0.4rem;
        }
        .price-card.featured {
            border-color: var(--border-gold);
            background: linear-gradient(180deg, rgba(184, 134, 11, 0.08), rgba(255, 255, 255, 1));
            position: relative;
        }
        .popular {
            position: absolute;
            top: 0.75rem;
            right: 0.75rem;
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #7c5c07;
            background: rgba(184, 134, 11, 0.1);
            border-radius: 999px;
            padding: 0.2rem 0.5rem;
        }

        .faq-list {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 1rem;
        }
        .faq-item {
            border-radius: 12px;
            border: 1px solid var(--border-default);
            background: var(--bg-surface);
            padding: 1rem;
        }
        .faq-item h3 {
            font-size: 1.35rem;
            margin-bottom: 0.35rem;
        }

        .final-cta {
            margin-top: 3rem;
            border-radius: 16px;
            border: 1px solid var(--border-gold);
            background: linear-gradient(120deg, rgba(196, 30, 58, 0.1), rgba(184, 134, 11, 0.1));
            padding: 2rem;
            text-align: center;
        }
        .final-cta h2 {
            font-size: 3.2rem;
            max-width: 18ch;
            margin: 0 auto;
            line-height: 1.1;
        }
        .final-cta p {
            margin-top: 0.5rem;
            font-size: 1.35rem;
        }
        .final-cta .hero-actions {
            justify-content: center;
        }

        .footer {
            margin-top: 1.2rem;
            padding-top: 1rem;
            border-top: 1px solid var(--border-default);
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 1rem;
            flex-wrap: wrap;
        }
        .footer span {
            font-family: var(--font-display);
            color: var(--ink-primary);
            font-size: 1.1rem;
        }
        .footer-links {
            display: flex;
            gap: 1rem;
            flex-wrap: wrap;
        }
        .footer-links a {
            font-family: var(--font-display);
            color: var(--accent-primary);
            font-size: 1.05rem;
        }

        @media (max-width: 1024px) {
            .hero { grid-template-columns: 1fr; }
            .cards-3 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
            .hero h1 { max-width: 20ch; }
            .final-cta h2 { font-size: 2.5rem; }
        }
        @media (max-width: 760px) {
            .page { padding: 1rem 1rem 1rem; }
            .nav { flex-direction: column; align-items: flex-start; }
            .nav-links { justify-content: flex-start; }
            .grid-2,
            .cards-3,
            .cards-2,
            .faq-list { grid-template-columns: 1fr; }
            .hero h1 { font-size: 2.6rem; }
            .section-title { font-size: 2.2rem; }
            .final-cta { padding: 1.3rem; }
            .final-cta h2 { font-size: 2rem; }
        }
        ::selection {
            background: rgba(196, 30, 58, 0.2);
            color: var(--ink-primary);
        }
    </style>
</head>
<body>
    <div class="page">
        <header class="nav">
            <a href="/" class="brand" aria-label="ACE home">
                <svg class="brand-logo" viewBox="0 0 40 56" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
                    <rect x="1" y="1" width="38" height="54" rx="4" fill="#ffffff" stroke="rgba(184,134,11,0.4)" stroke-width="1.5"/>
                    <rect x="4" y="4" width="32" height="48" rx="2" fill="none" stroke="#b8860b" stroke-width="0.5" opacity="0.3"/>
                    <text x="7" y="14" fill="#1a1a1a" font-size="9" font-family="Palatino Linotype, Georgia, serif" font-weight="700">A</text>
                    <text x="33" y="50" fill="#1a1a1a" font-size="9" font-family="Palatino Linotype, Georgia, serif" font-weight="700" transform="rotate(180,33,47)">A</text>
                    <g transform="translate(20, 28)">
                        <path d="M0 -12C0 -12 -8 -3 -8 3C-8 6 -6 8.5 -3 8.5C-1.5 8.5 -0.5 7.8 0 7C0.5 7.8 1.5 8.5 3 8.5C6 8.5 8 6 8 3C8 -3 0 -12 0 -12Z" fill="#1a1a1a"/>
                        <path d="M-2.5 7L-3.5 12H3.5L2.5 7" fill="#1a1a1a"/>
                    </g>
                </svg>
                <span class="brand-title">ACE</span>
            </a>

            <nav class="nav-links" aria-label="Main navigation">
                <a href="#how-it-works">How it works</a>
                <a href="#use-cases">Use cases</a>
                <a href="#pricing">Pricing</a>
                <a href="{{DOCS_URL}}/docs/getting-started/quick-start" target="_blank" rel="noreferrer">Docs</a>
                <a href="{{FRONTEND_URL}}/login" class="action">Sign in</a>
                <a href="{{FRONTEND_URL}}/register" class="action primary">Start free</a>
            </nav>
        </header>

        <section class="hero">
            <div>
                <p class="eyebrow">Agentic Context Engineer</p>
                <h1>Your AI workflow gets better after every task.</h1>
                <p class="hero-subhead">ACE captures what worked, what failed, and what to improve so your assistant becomes more reliable with real use.</p>
                <div class="hero-actions">
                    <a href="{{FRONTEND_URL}}/register" class="action primary">Start free</a>
                    <a href="{{DOCS_URL}}/docs/getting-started/quick-start" target="_blank" rel="noreferrer" class="action">See 2-min setup</a>
                </div>
                <p class="micro-copy">Works with MCP-enabled workflows.</p>
            </div>

            <div class="hero-visual" aria-hidden="true">
                <video class="hero-video" autoplay loop muted playsinline preload="metadata">
                    <source src="/landing-hero-video.mp4" type="video/mp4" />
                </video>
                <div class="metric-panel">
                    <p>Latest improvement</p>
                    <strong>Fewer repeat bugs</strong>
                    <p>ACE turns recurring issues into rules your agent follows.</p>
                </div>
            </div>
        </section>

        <section class="trust-strip" aria-label="Integrations">
            <p>Built for people shipping real work with AI</p>
            <div class="badges">
                <span>Claude Code</span>
                <span>Codex</span>
                <span>MCP</span>
            </div>
        </section>

        <section class="grid-2">
            <article class="panel">
                <h2>Stop restarting from scratch every session.</h2>
                <ul>
                    <li>Great prompts disappear between sessions.</li>
                    <li>Output quality drifts from task to task.</li>
                    <li>You spend too much time fixing repeated misses.</li>
                </ul>
            </article>
            <article class="panel">
                <h2>ACE makes improvement a personal system.</h2>
                <ul>
                    <li>Capture what worked and what failed automatically.</li>
                    <li>Generate focused evolutions from real execution history.</li>
                    <li>Get high-signal playbook improvements generated from your real outcomes.</li>
                </ul>
            </article>
        </section>

        <section id="how-it-works">
            <h2 class="section-title">How it works</h2>
            <p class="section-subtitle">Simple workflow, compounding results.</p>
            <div class="cards-3">
                <article class="card">
                    <h3>Connect your workflow</h3>
                    <p>Plug ACE into your MCP-compatible environment in minutes.</p>
                </article>
                <article class="card">
                    <h3>Run your normal tasks</h3>
                    <p>Code, research, write, and ship exactly how you already work.</p>
                </article>
                <article class="card">
                    <h3>Receive evolved playbooks</h3>
                    <p>ACE creates improved playbook versions as your outcomes accumulate.</p>
                </article>
            </div>
        </section>

        <section id="use-cases">
            <h2 class="section-title">Where individuals see immediate lift</h2>
            <p class="section-subtitle">From coding tasks to general knowledge work, ACE compounds what you learn.</p>
            <div class="cards-3">
                <article class="card">
                    <h3>Ship cleaner code faster</h3>
                    <p>Reduce repeat bugs by turning review feedback into reusable patterns.</p>
                </article>
                <article class="card">
                    <h3>Deliver consistent client work</h3>
                    <p>Keep docs, analysis, and deliverables aligned to your quality bar.</p>
                </article>
                <article class="card">
                    <h3>Build your personal AI system</h3>
                    <p>Convert one-off wins into durable playbooks that compound over time.</p>
                </article>
            </div>
        </section>

        <section>
            <h2 class="section-title">Measure compounding gains</h2>
            <p class="section-subtitle">Track these signals to verify that ACE is improving your workflow over time.</p>
            <div class="cards-3">
                <article class="card">
                    <p class="metric-label">Repeat errors</p>
                    <h3>Down</h3>
                    <p>Track recurring misses and shrink them with each evolution run.</p>
                </article>
                <article class="card">
                    <p class="metric-label">Task cycle time</p>
                    <h3>Faster</h3>
                    <p>Measure how quickly you move from prompt to production-ready output.</p>
                </article>
                <article class="card">
                    <p class="metric-label">First-pass quality</p>
                    <h3>Higher</h3>
                    <p>Increase how often outputs are usable without extensive rewrites.</p>
                </article>
            </div>
        </section>

        <section>
            <h2 class="section-title">Built for production-minded individuals</h2>
            <div class="control-list">
                <p>Versioned playbooks let you inspect every evolution run over time.</p>
                <p>Scoped API access with a clear audit trail of evolution activity.</p>
                <p>Works with your existing stack instead of forcing a platform rewrite.</p>
            </div>
        </section>

        <section id="pricing">
            <h2 class="section-title">Start free, upgrade when you need more power</h2>
            <div class="cards-3">
                <article class="card price-card">
                    <h3>Starter</h3>
                    <p class="price">$9/mo</p>
                    <p class="yearly">$90/yr <span>17% off</span></p>
                    <p>For individuals building momentum with AI.</p>
                    <ul>
                        <li>100 evolution runs / month</li>
                        <li>5 playbooks</li>
                        <li>Premium AI models</li>
                    </ul>
                </article>
                <article class="card price-card featured">
                    <p class="popular">Most popular</p>
                    <h3>Pro</h3>
                    <p class="price">$29/mo</p>
                    <p class="yearly">$290/yr <span>17% off</span></p>
                    <p>For power users shipping every day.</p>
                    <ul>
                        <li>500 evolution runs / month</li>
                        <li>20 playbooks</li>
                        <li>Data export</li>
                    </ul>
                </article>
                <article class="card price-card">
                    <h3>Ultra</h3>
                    <p class="price">$79/mo</p>
                    <p class="yearly">$790/yr <span>17% off</span></p>
                    <p>For heavy individual workflows.</p>
                    <ul>
                        <li>2,000 evolution runs / month</li>
                        <li>100 playbooks</li>
                        <li>Data export</li>
                    </ul>
                </article>
            </div>
            <div class="hero-actions">
                <a href="{{FRONTEND_URL}}/register" class="action primary">Start free</a>
                <a href="{{FRONTEND_URL}}/login" class="action">Sign in</a>
            </div>
        </section>

        <section>
            <h2 class="section-title">FAQ</h2>
            <div class="faq-list">
                <article class="faq-item">
                    <h3>How long does setup take?</h3>
                    <p>Most users can connect ACE to an MCP workflow in about 5 minutes.</p>
                </article>
                <article class="faq-item">
                    <h3>How are changes applied?</h3>
                    <p>Evolutions generate new playbook versions automatically, and you can inspect version history in the app.</p>
                </article>
                <article class="faq-item">
                    <h3>Will this work with my current AI toolchain?</h3>
                    <p>ACE is built to layer onto MCP-compatible tools instead of replacing them.</p>
                </article>
                <article class="faq-item">
                    <h3>Is this only for coding?</h3>
                    <p>No. ACE works for coding and broader knowledge workflows like research, writing, and analysis.</p>
                </article>
            </div>
        </section>

        <section class="final-cta">
            <h2>Make your AI improve continuously</h2>
            <p>Turn today's tasks into tomorrow's better results.</p>
            <div class="hero-actions">
                <a href="{{FRONTEND_URL}}/register" class="action primary">Start free</a>
                <a href="{{DOCS_URL}}/docs/getting-started/quick-start" target="_blank" rel="noreferrer" class="action">Open quick start</a>
            </div>
        </section>

        <footer class="footer">
            <span>&copy; {{CURRENT_YEAR}} ACE</span>
            <div class="footer-links">
                <a href="{{FRONTEND_URL}}/terms">Terms</a>
                <a href="{{FRONTEND_URL}}/privacy">Privacy</a>
                <a href="{{DOCS_URL}}" target="_blank" rel="noreferrer">Docs</a>
            </div>
        </footer>
    </div>
</body>
</html>"""
        return (
            html.replace("{{FRONTEND_URL}}", frontend_url)
            .replace("{{DOCS_URL}}", docs_url)
            .replace("{{CURRENT_YEAR}}", str(current_year))
        )


# Create the application instance
app = create_app()
