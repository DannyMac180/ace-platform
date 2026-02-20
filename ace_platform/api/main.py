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

import sentry_sdk
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
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

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def landing_page():
        """Serve the landing page."""
        frontend_url = settings.frontend_url.rstrip("/")
        docs_url = settings.docs_url.rstrip("/")
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ACE - Playbooks as a Service</title>
    <meta name="description" content="Self-improving AI instructions. Record outcomes, and ACE automatically evolves your playbooks based on real-world results.">
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500;600;700;800&family=Cormorant+Garamond:wght@300;400;500;600;700&family=Fira+Code:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #fdfcfa;
            --bg-surface: #ffffff;
            --bg-muted: #f8f6f1;
            --bg-hero: linear-gradient(180deg, #fdfcfa 0%, #f5f3ee 100%);
            --ink-primary: #1a1a1a;
            --text-secondary: #4a4a4a;
            --text-tertiary: #7a7a7a;
            --accent-primary: #c41e3a;
            --accent-dark: #a31830;
            --gold-primary: #b8860b;
            --border-subtle: rgba(0, 0, 0, 0.08);
            --border-default: rgba(0, 0, 0, 0.1);
            --shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.08);
            --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.12);
            --font-display: 'Playfair Display', Georgia, serif;
            --font-body: 'Cormorant Garamond', Garamond, serif;
            --font-mono: 'Fira Code', SFMono-Regular, Menlo, Monaco, Consolas, monospace;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html { font-size: 16px; -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }
        body {
            font-family: var(--font-body);
            font-size: 1.0625rem;
            line-height: 1.65;
            color: var(--ink-primary);
            background: var(--bg-primary);
            min-height: 100vh;
        }
        body::before {
            content: '';
            position: fixed;
            inset: 0;
            background-image: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M30 0L30 60M0 30L60 30M0 0L60 60M60 0L0 60' stroke='%23000000' stroke-width='0.2' fill='none' opacity='0.02'/%3E%3C/svg%3E");
            opacity: 0.5;
            pointer-events: none;
            z-index: 0;
        }

        /* Navbar */
        .navbar {
            background: var(--bg-surface);
            border-bottom: 1px solid var(--border-subtle);
            box-shadow: var(--shadow-sm);
            height: 4rem;
            position: sticky;
            top: 0;
            z-index: 100;
        }
        .navbar-inner {
            max-width: 1200px;
            margin: 0 auto;
            padding: 0 2rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            height: 100%;
        }
        .navbar-brand {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            text-decoration: none;
        }
        .navbar-logo {
            width: 28px;
            height: 28px;
        }
        .navbar-title {
            font-family: var(--font-display);
            font-weight: 700;
            font-size: 1.25rem;
            color: var(--ink-primary);
            letter-spacing: -0.01em;
        }
        .navbar-links {
            display: flex;
            align-items: center;
            gap: 1.5rem;
        }
        .navbar-links a {
            font-family: var(--font-display);
            font-weight: 500;
            font-size: 0.9375rem;
            color: #2d2d2d;
            text-decoration: none;
            transition: color 0.2s;
        }
        .navbar-links a:hover { color: var(--accent-primary); }

        /* Hero */
        .hero {
            background: var(--bg-hero);
            border-bottom: 1px solid var(--border-subtle);
            padding: 6rem 2rem;
            text-align: center;
            position: relative;
        }
        .hero-title {
            font-family: var(--font-display);
            font-size: 3.5rem;
            font-weight: 700;
            color: var(--ink-primary);
            margin-bottom: 1rem;
            letter-spacing: -0.02em;
            line-height: 1.15;
        }
        .hero-subtitle {
            font-family: var(--font-body);
            font-size: 1.5rem;
            color: var(--text-secondary);
            margin-bottom: 2rem;
            max-width: 600px;
            margin-left: auto;
            margin-right: auto;
            line-height: 1.6;
        }
        .hero-buttons {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 1rem;
            flex-wrap: wrap;
        }
        .btn {
            font-family: var(--font-display);
            font-weight: 500;
            letter-spacing: 0.02em;
            padding: 0.75rem 2rem;
            border-radius: 8px;
            font-size: 1rem;
            text-decoration: none;
            display: inline-block;
            transition: all 250ms cubic-bezier(0.4, 0, 0.2, 1);
            border: 2px solid transparent;
            cursor: pointer;
        }
        .btn-primary {
            background: var(--accent-primary);
            color: #fff;
            border-color: var(--accent-primary);
        }
        .btn-primary:hover {
            background: var(--accent-dark);
            border-color: var(--accent-dark);
            box-shadow: 0 4px 12px rgba(196, 30, 58, 0.3);
        }
        .btn-secondary {
            background: transparent;
            color: var(--accent-primary);
            border-color: var(--accent-primary);
        }
        .btn-secondary:hover {
            background: rgba(196, 30, 58, 0.05);
            color: var(--accent-dark);
        }
        .hero-video-wrap {
            max-width: 920px;
            margin: 2.5rem auto 0;
            padding: 0 0.5rem;
        }
        .hero-video {
            width: 100%;
            aspect-ratio: 16 / 9;
            border-radius: 14px;
            border: 1px solid var(--border-default);
            box-shadow: var(--shadow-md);
            background: #000;
        }

        /* Features */
        .features {
            padding: 4rem 2rem;
            background: var(--bg-surface);
        }
        .features-inner {
            max-width: 1100px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 2rem;
        }
        .feature {
            text-align: center;
            padding: 1.5rem;
        }
        .feature-icon {
            font-size: 3rem;
            margin-bottom: 1rem;
            line-height: 1;
        }
        .feature:nth-child(1) .feature-icon { color: var(--ink-primary); }
        .feature:nth-child(2) .feature-icon,
        .feature:nth-child(3) .feature-icon { color: var(--accent-primary); }
        .feature-title {
            font-family: var(--font-display);
            font-size: 1.25rem;
            font-weight: 600;
            color: var(--ink-primary);
            margin-bottom: 0.75rem;
        }
        .feature-desc {
            font-family: var(--font-body);
            font-size: 1rem;
            color: var(--text-secondary);
            line-height: 1.6;
        }

        /* Quick Links */
        .quick-links {
            padding: 4rem 2rem;
            background: var(--bg-muted);
            border-top: 1px solid rgba(0, 0, 0, 0.06);
        }
        .quick-links-inner {
            max-width: 1100px;
            margin: 0 auto;
        }
        .section-title {
            font-family: var(--font-display);
            font-size: 2rem;
            font-weight: 600;
            color: var(--ink-primary);
            text-align: center;
            margin-bottom: 2rem;
        }
        .link-cards {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1.5rem;
        }
        .link-card {
            display: block;
            background: var(--bg-surface);
            border: 1px solid var(--border-default);
            border-radius: 10px;
            padding: 1.5rem;
            text-decoration: none;
            transition: all 250ms ease;
        }
        .link-card:hover {
            border-color: var(--accent-primary);
            box-shadow: 0 4px 12px rgba(196, 30, 58, 0.1);
            transform: translateY(-2px);
        }
        .link-card h3 {
            font-family: var(--font-display);
            font-size: 1.125rem;
            font-weight: 600;
            color: var(--ink-primary);
            margin-bottom: 0.5rem;
        }
        .link-card p {
            font-family: var(--font-body);
            font-size: 0.9375rem;
            color: var(--text-secondary);
            margin: 0;
        }

        /* Footer */
        .footer {
            background: var(--bg-muted);
            border-top: 1px solid var(--border-subtle);
            padding: 3rem 2rem 2rem;
        }
        .footer-inner {
            max-width: 1100px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 2rem;
            margin-bottom: 2rem;
        }
        .footer-col h4 {
            font-family: var(--font-display);
            font-weight: 600;
            font-size: 0.875rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-secondary);
            margin-bottom: 1rem;
        }
        .footer-col ul {
            list-style: none;
        }
        .footer-col li {
            margin-bottom: 0.5rem;
        }
        .footer-col a {
            font-family: var(--font-body);
            font-size: 0.9375rem;
            color: #2d2d2d;
            text-decoration: none;
            transition: color 0.2s;
        }
        .footer-col a:hover { color: var(--accent-primary); }
        .footer-copyright {
            text-align: center;
            padding-top: 2rem;
            border-top: 1px solid var(--border-subtle);
            font-family: var(--font-body);
            font-size: 0.875rem;
            color: var(--text-secondary);
        }

        /* Responsive */
        @media (max-width: 996px) {
            .hero { padding: 4rem 2rem; }
            .hero-title { font-size: 2.5rem; }
            .hero-subtitle { font-size: 1.25rem; }
            .hero-video-wrap { margin-top: 2rem; }
            .features-inner { grid-template-columns: 1fr; }
            .feature { margin-bottom: 1rem; }
            .link-cards { grid-template-columns: 1fr; }
            .footer-inner { grid-template-columns: 1fr; }
        }
        @media (max-width: 576px) {
            .hero-buttons { flex-direction: column; }
            .btn { width: 100%; text-align: center; }
            .navbar-links { gap: 1rem; }
            .navbar-links a { font-size: 0.8125rem; }
        }

        /* Selection */
        ::selection {
            background: rgba(196, 30, 58, 0.2);
            color: var(--ink-primary);
        }
    </style>
</head>
<body>
    <nav class="navbar">
        <div class="navbar-inner">
            <a href="/" class="navbar-brand">
                <svg class="navbar-logo" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <rect x="1" y="1" width="26" height="26" rx="4" fill="#ffffff" stroke="rgba(184,134,11,0.4)" stroke-width="1"/>
                    <text x="7" y="12" fill="#1a1a1a" font-size="7" font-family="Playfair Display, serif" font-weight="700">A</text>
                    <g transform="translate(14, 18)">
                        <path d="M0 -6.5C0 -6.5 -4.5 -1.5 -4.5 1.8C-4.5 3.4 -3.4 4.8 -1.7 4.8C-0.8 4.8 -0.3 4.4 0 3.9C0.3 4.4 0.8 4.8 1.7 4.8C3.4 4.8 4.5 3.4 4.5 1.8C4.5 -1.5 0 -6.5 0 -6.5Z" fill="#1a1a1a"/>
                    </g>
                </svg>
                <span class="navbar-title">ACE</span>
            </a>
            <div class="navbar-links">
                <a href="{{DOCS_URL}}/docs">Documentation</a>
                <a href="{{FRONTEND_URL}}">Dashboard</a>
            </div>
        </div>
    </nav>

    <section class="hero">
        <h1 class="hero-title">ACE</h1>
        <p class="hero-subtitle">Playbooks as a Service &mdash; Self-improving AI instructions</p>
        <div class="hero-buttons">
            <a href="{{FRONTEND_URL}}/login" class="btn btn-primary">Get Started</a>
            <a href="{{DOCS_URL}}/docs/developer-guides/mcp-integration/overview" class="btn btn-secondary">MCP Integration</a>
        </div>
        <div class="hero-video-wrap">
            <video
                class="hero-video"
                autoplay
                loop
                muted
                playsinline
                controls
                aria-label="ACE platform demo video"
            >
                <source src="{{FRONTEND_URL}}/landing-hero-video.mp4" type="video/mp4" />
                Your browser does not support the video tag.
            </video>
        </div>
    </section>

    <section class="features">
        <div class="features-inner">
            <div class="feature">
                <div class="feature-icon">&spades;</div>
                <h3 class="feature-title">Self-Improving Playbooks</h3>
                <p class="feature-desc">Record outcomes after each task, and ACE automatically evolves your playbooks based on real-world results. The more you use them, the better they get.</p>
            </div>
            <div class="feature">
                <div class="feature-icon">&hearts;</div>
                <h3 class="feature-title">MCP Integration</h3>
                <p class="feature-desc">Connect directly to Claude Desktop, Claude Code, or any MCP-compatible agent. Access playbooks without writing integration code.</p>
            </div>
            <div class="feature">
                <div class="feature-icon">&diams;</div>
                <h3 class="feature-title">Version Control Built-In</h3>
                <p class="feature-desc">Every change creates a new version. Compare diffs, understand improvements, and roll back if needed. Full history at your fingertips.</p>
            </div>
        </div>
    </section>

    <section class="quick-links">
        <div class="quick-links-inner">
            <h2 class="section-title">Quick Links</h2>
            <div class="link-cards">
                <a href="{{DOCS_URL}}/docs/getting-started/quick-start" class="link-card">
                    <h3>Quick Start</h3>
                    <p>Get up and running in 5 minutes</p>
                </a>
                <a href="{{DOCS_URL}}/docs/developer-guides/mcp-integration/claude-code" class="link-card">
                    <h3>Claude Code Setup</h3>
                    <p>Integrate with Claude Code CLI</p>
                </a>
                <a href="{{DOCS_URL}}/docs/developer-guides/recording-outcomes" class="link-card">
                    <h3>Recording Outcomes</h3>
                    <p>Feed ACE the feedback it needs to evolve</p>
                </a>
            </div>
        </div>
    </section>

    <footer class="footer">
        <div class="footer-inner">
            <div class="footer-col">
                <h4>Documentation</h4>
                <ul>
                    <li><a href="{{DOCS_URL}}/docs/getting-started/quick-start">Getting Started</a></li>
                    <li><a href="{{DOCS_URL}}/docs/user-guides/creating-playbooks">User Guides</a></li>
                    <li><a href="{{DOCS_URL}}/docs/developer-guides/mcp-integration/overview">MCP Integration</a></li>
                </ul>
            </div>
            <div class="footer-col">
                <h4>Product</h4>
                <ul>
                    <li><a href="{{FRONTEND_URL}}">Dashboard</a></li>
                    <li><a href="{{FRONTEND_URL}}/pricing">Pricing</a></li>
                </ul>
            </div>
        </div>
        <div class="footer-copyright">
            &copy; 2026 ACE
        </div>
    </footer>
</body>
</html>"""
        return html.replace("{{FRONTEND_URL}}", frontend_url).replace("{{DOCS_URL}}", docs_url)


# Create the application instance
app = create_app()
