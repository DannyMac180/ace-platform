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
from fastmcp_mount import MountFastMCP
from starlette.middleware.sessions import SessionMiddleware

from ace_platform.config import get_settings
from ace_platform.core.logging import get_logger, setup_logging
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
        allow_methods=["*"],
        allow_headers=["*"],
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
        evolutions_router,
        oauth_router,
        playbooks_router,
        usage_router,
    )

    # Include API routers
    app.include_router(auth_router)
    app.include_router(oauth_router)
    app.include_router(billing_router)
    app.include_router(playbooks_router)
    app.include_router(usage_router)
    app.include_router(evolutions_router)

    # Mount MCP server at /mcp for SSE transport
    # This allows clients to connect to the MCP server via the same domain as the API
    # using: https://aceagent.io/mcp/sse
    from ace_platform.mcp.server import mcp as mcp_server

    mcp_sse_app = mcp_server.sse_app()
    app.mount("/mcp", app=MountFastMCP(app=mcp_sse_app), name="mcp")

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
            from sqlalchemy import text

            async with async_session_context() as db:
                await db.execute(text("SELECT 1"))
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

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def landing_page():
        """Serve the landing page."""
        frontend_url = settings.frontend_url.rstrip("/")
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ACE Platform - Self-Improving AI Playbooks</title>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500;600;700;800&family=Cormorant+Garamond:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #fdfcfa;
            --bg-secondary: #f5f3ee;
            --bg-card: #ffffff;
            --ink-primary: #1a1a1a;
            --text-secondary: #4a4a4a;
            --text-tertiary: #7a7a7a;
            --accent-primary: #c41e3a;
            --accent-secondary: #a31830;
            --gold-primary: #b8860b;
            --border-default: rgba(0, 0, 0, 0.12);
            --border-gold: rgba(184, 134, 11, 0.4);
            --shadow-card: 0 2px 8px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.04);
            --shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.1), 0 4px 8px rgba(0, 0, 0, 0.06);
            --font-display: 'Playfair Display', Georgia, serif;
            --font-body: 'Cormorant Garamond', Garamond, serif;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        html { font-size: 16px; -webkit-font-smoothing: antialiased; }
        body {
            font-family: var(--font-body);
            font-size: 1.0625rem;
            line-height: 1.65;
            color: var(--ink-primary);
            background: var(--bg-primary);
            min-height: 100vh;
        }
        /* Subtle pattern overlay */
        body::before {
            content: '';
            position: fixed;
            inset: 0;
            background-image: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M30 0L30 60M0 30L60 30M0 0L60 60M60 0L0 60' stroke='%23000000' stroke-width='0.2' fill='none' opacity='0.02'/%3E%3C/svg%3E");
            opacity: 0.5;
            pointer-events: none;
            z-index: -1;
        }
        .container {
            max-width: 1100px;
            margin: 0 auto;
            padding: 2rem;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 1.5rem 0;
            border-bottom: 1px solid var(--border-default);
            margin-bottom: 2rem;
        }
        .logo {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }
        .logo-text {
            font-family: var(--font-display);
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--ink-primary);
            letter-spacing: -0.02em;
        }
        nav a {
            font-family: var(--font-display);
            color: var(--text-secondary);
            text-decoration: none;
            margin-left: 2rem;
            font-size: 0.9375rem;
            font-weight: 500;
            transition: color 0.2s;
        }
        nav a:hover { color: var(--accent-primary); }
        .hero {
            text-align: center;
            padding: 5rem 0;
        }
        h1 {
            font-family: var(--font-display);
            font-size: 3.25rem;
            font-weight: 700;
            color: var(--ink-primary);
            margin-bottom: 1.5rem;
            letter-spacing: -0.02em;
            line-height: 1.15;
        }
        .subtitle {
            font-family: var(--font-body);
            font-size: 1.375rem;
            color: var(--text-secondary);
            margin-bottom: 2.5rem;
            max-width: 600px;
            margin-left: auto;
            margin-right: auto;
            line-height: 1.6;
        }
        .cta-buttons {
            display: flex;
            gap: 1rem;
            justify-content: center;
            flex-wrap: wrap;
        }
        .btn {
            font-family: var(--font-display);
            padding: 0.875rem 2rem;
            border-radius: 8px;
            font-size: 0.9375rem;
            font-weight: 600;
            text-decoration: none;
            letter-spacing: 0.02em;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            border: 1px solid transparent;
        }
        .btn-primary {
            background: var(--accent-primary);
            color: #fff;
            box-shadow: 0 2px 8px rgba(196, 30, 58, 0.2);
        }
        .btn-primary:hover {
            background: var(--accent-secondary);
            transform: translateY(-2px);
            box-shadow: 0 4px 16px rgba(196, 30, 58, 0.3);
        }
        .btn-secondary {
            background: transparent;
            color: var(--ink-primary);
            border-color: var(--border-default);
        }
        .btn-secondary:hover {
            border-color: var(--gold-primary);
            color: var(--gold-primary);
        }
        .divider {
            display: flex;
            align-items: center;
            gap: 1rem;
            color: var(--text-tertiary);
            margin: 4rem 0;
        }
        .divider::before, .divider::after {
            content: '';
            flex: 1;
            height: 1px;
            background: linear-gradient(90deg, transparent, var(--border-default), transparent);
        }
        .divider span { font-size: 1.25rem; }
        .features {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 2rem;
            padding: 2rem 0 4rem;
        }
        .feature {
            background: var(--bg-card);
            padding: 2rem;
            border-radius: 10px;
            border: 1px solid var(--border-default);
            box-shadow: var(--shadow-card);
            position: relative;
            transition: all 0.3s ease;
        }
        .feature:hover {
            box-shadow: var(--shadow-lg);
            border-color: var(--border-gold);
        }
        /* Card corner decorations */
        .feature::before, .feature::after {
            content: '';
            position: absolute;
            width: 16px;
            height: 16px;
            border: 2px solid var(--ink-primary);
            opacity: 0.1;
            transition: opacity 0.3s;
        }
        .feature::before {
            top: 8px;
            left: 8px;
            border-right: none;
            border-bottom: none;
        }
        .feature::after {
            bottom: 8px;
            right: 8px;
            border-left: none;
            border-top: none;
        }
        .feature:hover::before, .feature:hover::after { opacity: 0.25; }
        .feature h3 {
            font-family: var(--font-display);
            color: var(--accent-primary);
            margin-bottom: 0.75rem;
            font-size: 1.25rem;
            font-weight: 600;
        }
        .feature p {
            color: var(--text-secondary);
            line-height: 1.7;
        }
        footer {
            text-align: center;
            padding: 3rem 0;
            border-top: 1px solid var(--border-default);
            color: var(--text-tertiary);
            font-size: 0.9375rem;
        }
        /* Ace card logo SVG */
        .ace-card {
            width: 36px;
            height: 50px;
        }
        @media (max-width: 768px) {
            h1 { font-size: 2.25rem; }
            .subtitle { font-size: 1.125rem; }
            .hero { padding: 3rem 0; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo">
                <svg class="ace-card" viewBox="0 0 40 56" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <rect x="1" y="1" width="38" height="54" rx="4" fill="#ffffff" stroke="rgba(184,134,11,0.4)" stroke-width="1.5"/>
                    <rect x="4" y="4" width="32" height="48" rx="2" fill="none" stroke="#b8860b" stroke-width="0.5" opacity="0.3"/>
                    <text x="7" y="14" fill="#1a1a1a" font-size="9" font-family="Playfair Display, serif" font-weight="700">A</text>
                    <g transform="translate(20, 28)">
                        <path d="M0 -12C0 -12 -8 -3 -8 3C-8 6 -6 8.5 -3 8.5C-1.5 8.5 -0.5 7.8 0 7C0.5 7.8 1.5 8.5 3 8.5C6 8.5 8 6 8 3C8 -3 0 -12 0 -12Z" fill="#1a1a1a"/>
                        <path d="M-2.5 7L-3.5 12H3.5L2.5 7" fill="#1a1a1a"/>
                    </g>
                    <path d="M4 8L4 4L8 4" stroke="#b8860b" stroke-width="1" fill="none" opacity="0.6"/>
                    <path d="M36 8L36 4L32 4" stroke="#b8860b" stroke-width="1" fill="none" opacity="0.6"/>
                    <path d="M4 48L4 52L8 52" stroke="#b8860b" stroke-width="1" fill="none" opacity="0.6"/>
                    <path d="M36 48L36 52L32 52" stroke="#b8860b" stroke-width="1" fill="none" opacity="0.6"/>
                </svg>
                <span class="logo-text">ACE</span>
            </div>
            <nav>
                <a href="/health">Status</a>
            </nav>
        </header>

        <section class="hero">
            <h1>AI Playbooks That<br>Improve Themselves</h1>
            <p class="subtitle">
                Create context for your AI agents that gets smarter the more you use it.
                ACE automatically captures what works and evolves your playbooks.
            </p>
            <div class="cta-buttons">
                <a href="{{FRONTEND_URL}}/login" class="btn btn-primary">Get Started</a>
                <a href="#features" class="btn btn-secondary">Learn More</a>
            </div>
        </section>

        <div class="divider"><span>&#9824;</span></div>

        <section class="features" id="features">
            <div class="feature">
                <h3>Self-Improving Context</h3>
                <p>Your playbooks evolve based on real outcomes. The more you use them, the better they get at guiding your AI agents.</p>
            </div>
            <div class="feature">
                <h3>MCP Integration</h3>
                <p>Connect to any AI assistant that supports the Model Context Protocol. Your playbooks become living context that travels with you.</p>
            </div>
            <div class="feature">
                <h3>Outcome Tracking</h3>
                <p>ACE watches what works and what doesn't, automatically incorporating successful patterns into your playbooks.</p>
            </div>
        </section>

        <footer>
            &copy; 2026 ACE Platform. Built for developers who want their AI to get smarter.
        </footer>
    </div>
</body>
</html>"""
        return html.replace("{{FRONTEND_URL}}", frontend_url)


# Create the application instance
app = create_app()
