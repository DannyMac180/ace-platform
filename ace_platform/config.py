"""Configuration management using Pydantic Settings.

Environment variables are loaded from .env file and can be overridden
by actual environment variables.
"""

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ALLOWED_SESSION_COOKIE_SAMESITE = {"lax", "strict", "none"}


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/ace_platform",
        description="PostgreSQL connection string (sync)",
    )
    database_url_async: str | None = Field(
        default=None,
        description="PostgreSQL async connection string. If not set, derived from database_url",
    )

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection string for Celery",
    )

    # OpenAI
    openai_api_key: str = Field(
        default="",
        description="OpenAI API key for LLM calls",
    )
    playbook_embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Embedding model used for semantic playbook matching",
    )
    playbook_embedding_max_chars: int = Field(
        default=12000,
        ge=500,
        description="Maximum playbook characters included when generating match embeddings",
    )

    # JWT Authentication
    jwt_secret_key: str = Field(
        default="change-me-in-production",
        description="Secret key for JWT token signing",
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm",
    )
    jwt_access_token_expire_minutes: int = Field(
        default=30,
        description="Access token expiration time in minutes",
    )
    jwt_refresh_token_expire_days: int = Field(
        default=7,
        description="Refresh token expiration time in days",
    )

    # Billing (optional)
    billing_enabled: bool = Field(
        default=False,
        description="Enable Stripe billing integration",
    )
    stripe_secret_key: str = Field(
        default="",
        description="Stripe secret key (required if billing_enabled)",
    )
    stripe_webhook_secret: str = Field(
        default="",
        description="Stripe webhook secret (required if billing_enabled)",
    )

    # MCP Server
    mcp_server_host: str = Field(
        default="0.0.0.0",
        description="MCP server bind host",
    )
    mcp_server_port: int = Field(
        default=8001,
        description="MCP server port",
    )

    # Evolution thresholds
    evolution_outcome_threshold: int = Field(
        default=5,
        ge=5,
        description="Minimum unprocessed outcomes required to trigger evolution",
    )

    # Evolution LLM settings
    evolution_api_provider: str = Field(
        default="openai",
        description="LLM provider for evolution (openai, anthropic, together)",
    )
    evolution_generator_model: str = Field(
        default="gpt-5.2",
        description="Model for Generator agent",
    )
    evolution_reflector_model: str = Field(
        default="gpt-5.2",
        description="Model for Reflector agent",
    )
    evolution_curator_model: str = Field(
        default="gpt-5.2",
        description="Model for Curator agent",
    )
    evolution_reasoning_effort: str = Field(
        default="medium",
        description="Reasoning effort for GPT-5.x models (none, low, medium, high)",
    )
    evolution_max_tokens: int = Field(
        default=4096,
        description="Max tokens per LLM call in evolution",
    )
    evolution_playbook_token_budget: int = Field(
        default=80000,
        description="Max tokens allowed for playbook content",
    )

    # API Server
    api_host: str = Field(
        default="0.0.0.0",
        description="API server bind host",
    )
    api_port: int = Field(
        default=8000,
        description="API server port",
    )
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Allowed CORS origins",
    )
    trusted_proxy_cidrs: list[str] = Field(
        default=["127.0.0.1/32", "::1/128"],
        description=(
            "Trusted proxy CIDRs for forwarded IP parsing. "
            "Only requests from these proxies can influence X-Forwarded-For/X-Real-IP."
        ),
    )

    # OAuth Authentication
    google_oauth_client_id: str = Field(
        default="",
        description="Google OAuth client ID",
    )
    google_oauth_client_secret: str = Field(
        default="",
        description="Google OAuth client secret",
    )
    github_oauth_client_id: str = Field(
        default="",
        description="GitHub OAuth client ID",
    )
    github_oauth_client_secret: str = Field(
        default="",
        description="GitHub OAuth client secret",
    )
    oauth_redirect_base_url: str = Field(
        default="http://localhost:8000",
        description="Base URL for OAuth redirect callbacks (your API server URL)",
    )
    frontend_url: str = Field(
        default="http://localhost:3000",
        description="Frontend application URL for post-OAuth redirects",
    )
    docs_url: str = Field(
        default="https://docs.aceagent.io",
        description="Documentation site URL for landing page links",
    )
    acquisition_tracking_enabled: bool = Field(
        default=True,
        description="Enable first-party acquisition attribution and event tracking",
    )
    x_landing_enabled: bool = Field(
        default=True,
        description="Enable the conversion-focused /x landing page",
    )
    session_secret_key: str = Field(
        default="",
        description="Secret key for OAuth session cookies (separate from JWT for security isolation)",
    )
    session_cookie_secure: bool = Field(
        default=False,
        description="Set Secure flag on session cookies (required for SameSite=None, use True in production)",
    )
    session_cookie_samesite: str = Field(
        default="lax",
        description="SameSite policy for session cookies: 'lax', 'strict', or 'none' (use 'none' for cross-origin)",
    )
    session_cookie_domain: str = Field(
        default="",
        description="Cookie domain for session cookies (e.g., '.aceagent.io' for cross-subdomain). Empty for default.",
    )

    # Environment
    environment: str = Field(
        default="development",
        description="Environment name (development, staging, production)",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode",
    )

    # Logging
    log_level: str = Field(
        default="",
        description="Override log level (DEBUG, INFO, WARNING, ERROR). If empty, auto-determined.",
    )
    log_format: str = Field(
        default="auto",
        description="Log format: 'json' for structured, 'text' for readable, 'auto' for environment-based",
    )

    # Error tracking (Sentry)
    sentry_dsn: str = Field(
        default="",
        description="Sentry DSN for error tracking. Leave empty to disable Sentry.",
    )
    sentry_release: str = Field(
        default="",
        description=(
            "Release identifier for Sentry events (overrides derived defaults when set). "
            "Use a stable artifact identifier such as the Git commit SHA."
        ),
    )
    sentry_transport_queue_size: int = Field(
        default=100,
        ge=1,
        description="Sentry transport queue size before events are dropped.",
    )
    sentry_traces_sample_rate: float = Field(
        default=0.1,
        description="Sentry performance monitoring sample rate (0.0 to 1.0)",
    )
    sentry_profiles_sample_rate: float = Field(
        default=0.1,
        description="Sentry profiling sample rate (0.0 to 1.0)",
    )

    # Email (Resend)
    resend_api_key: str = Field(
        default="",
        description="Resend API key for sending emails. Leave empty to disable email features.",
    )
    email_from_address: str = Field(
        default="noreply@aceagent.io",
        description="From address for outgoing emails",
    )
    email_from_name: str = Field(
        default="ACE Platform",
        description="From name for outgoing emails",
    )
    email_verification_token_expire_hours: int = Field(
        default=24,
        description="Email verification token expiration time in hours",
    )

    # Support
    support_email: str = Field(
        default="",
        description="Email address where support contact form messages are sent. Falls back to ADMIN_ALERT_EMAIL if empty.",
    )

    # Admin Alerts
    admin_alert_email: str = Field(
        default="",
        description="Email address to receive admin alerts (daily spend summaries, high-spend warnings)",
    )
    admin_alert_slack_webhook: str = Field(
        default="",
        description="Slack webhook URL for admin alerts (optional)",
    )
    admin_alert_spend_threshold_pct: int = Field(
        default=50,
        description="Percentage of tier limit to trigger spend alert (e.g., 50 = alert at 50% of limit)",
    )

    # Monitoring
    metrics_auth_token: str = Field(
        default="",
        description="Bearer token required to access /metrics endpoint. Leave empty to allow unauthenticated access.",
    )

    # Security Headers
    security_headers_enabled: bool = Field(
        default=True,
        description="Enable security headers middleware",
    )
    security_hsts_enabled: bool = Field(
        default=True,
        description="Enable HSTS header (disable for local HTTP development)",
    )
    security_hsts_max_age: int = Field(
        default=31536000,
        description="HSTS max-age in seconds (default: 1 year)",
    )
    security_csp: str = Field(
        default="default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; frame-ancestors 'none'",
        description="Content-Security-Policy header value",
    )

    @field_validator("database_url", mode="after")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        """Normalize postgres:// to postgresql:// for SQLAlchemy compatibility."""
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql://", 1)
        return v

    @field_validator("database_url_async", mode="before")
    @classmethod
    def derive_async_url(cls, v: str | None, info) -> str:
        """Derive async database URL from sync URL if not provided."""
        if v:
            return v
        # Get the sync URL from the data being validated
        sync_url = info.data.get("database_url", "")
        if sync_url.startswith("postgresql://"):
            async_url = sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif sync_url.startswith("postgres://"):
            async_url = sync_url.replace("postgres://", "postgresql+asyncpg://", 1)
        else:
            return sync_url
        # asyncpg doesn't accept sslmode parameter - convert it to ssl parameter
        # Fly.io sets sslmode=disable for internal connections
        ssl_disabled = "sslmode=disable" in async_url
        if "?sslmode=" in async_url:
            async_url = async_url.split("?sslmode=")[0]
        elif "&sslmode=" in async_url:
            # Handle case where sslmode is not the first parameter
            parts = async_url.split("&sslmode=")
            if len(parts) == 2:
                remaining = parts[1].split("&", 1)
                if len(remaining) > 1:
                    async_url = parts[0] + "&" + remaining[1]
                else:
                    async_url = parts[0]
        # If SSL was disabled, explicitly disable it for asyncpg
        if ssl_disabled:
            if "?" in async_url:
                async_url += "&ssl=disable"
            else:
                async_url += "?ssl=disable"
        return async_url

    @field_validator("stripe_secret_key", "stripe_webhook_secret", mode="after")
    @classmethod
    def validate_billing_config(cls, v: str, info) -> str:
        """Validate Stripe config is provided when billing is enabled."""
        billing_enabled = info.data.get("billing_enabled", False)
        if billing_enabled and not v:
            field_name = info.field_name
            raise ValueError(f"{field_name} is required when billing_enabled=True")
        return v

    @field_validator("session_cookie_samesite", mode="after")
    @classmethod
    def validate_session_cookie_samesite(cls, v: str) -> str:
        """Normalize and validate SameSite policy."""
        normalized = v.strip().lower()
        if normalized not in _ALLOWED_SESSION_COOKIE_SAMESITE:
            raise ValueError("SESSION_COOKIE_SAMESITE must be one of: lax, strict, none")
        return normalized

    @field_validator("session_cookie_domain", mode="after")
    @classmethod
    def validate_session_cookie_domain(cls, v: str) -> str:
        """Require cookie domain to be a hostname-only value."""
        if not v:
            return v

        domain = v.strip()
        if domain != v:
            raise ValueError("SESSION_COOKIE_DOMAIN must not include surrounding whitespace")

        if any(token in domain for token in ("://", "/", ":")):
            raise ValueError(
                "SESSION_COOKIE_DOMAIN must be a bare domain (no scheme, path, or port)"
            )

        return domain

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Reject insecure auth defaults in production and staging."""
        if self.environment not in ("production", "staging"):
            return self

        insecure_defaults = {"change-me-in-production", ""}
        if self.jwt_secret_key in insecure_defaults:
            raise ValueError(
                "JWT_SECRET_KEY must be explicitly set to a secure value "
                f"in {self.environment} (current value is a default/empty)"
            )

        if not self.session_secret_key:
            raise ValueError(
                "SESSION_SECRET_KEY must be explicitly set in "
                f"{self.environment} (do not fall back to JWT_SECRET_KEY)"
            )

        if not self.session_cookie_secure:
            if self.session_cookie_samesite == "none":
                raise ValueError(
                    "SESSION_COOKIE_SAMESITE='none' requires SESSION_COOKIE_SECURE=true "
                    f"in {self.environment} for cross-origin OAuth flows"
                )
            raise ValueError(
                f"SESSION_COOKIE_SECURE must be true in {self.environment} "
                "for OAuth session cookie protection"
            )

        oauth_configured = bool(
            self.google_oauth_client_id and self.google_oauth_client_secret
        ) or bool(self.github_oauth_client_id and self.github_oauth_client_secret)
        if oauth_configured and self.session_cookie_samesite == "strict":
            raise ValueError(
                "SESSION_COOKIE_SAMESITE='strict' can break OAuth callbacks; "
                "use 'lax' or 'none' for cross-origin flows"
            )

        if self.session_cookie_domain:
            bare_domain = self.session_cookie_domain.lstrip(".")
            if "." not in bare_domain:
                raise ValueError(
                    "SESSION_COOKIE_DOMAIN should be a parent domain "
                    "(example: aceagent.io or .aceagent.io) in production/staging"
                )

        return self

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
