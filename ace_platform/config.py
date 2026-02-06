"""Configuration management using Pydantic Settings.

Environment variables are loaded from .env file and can be overridden
by actual environment variables.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        default="default-src 'self'; frame-ancestors 'none'",
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

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
