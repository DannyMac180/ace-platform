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
        description="Number of unprocessed outcomes to trigger evolution",
    )
    evolution_time_threshold_hours: int = Field(
        default=24,
        description="Hours since last evolution to trigger (with at least 1 outcome)",
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

    # Environment
    environment: str = Field(
        default="development",
        description="Environment name (development, staging, production)",
    )
    debug: bool = Field(
        default=False,
        description="Enable debug mode",
    )

    @field_validator("database_url_async", mode="before")
    @classmethod
    def derive_async_url(cls, v: str | None, info) -> str:
        """Derive async database URL from sync URL if not provided."""
        if v:
            return v
        # Get the sync URL from the data being validated
        sync_url = info.data.get("database_url", "")
        if sync_url.startswith("postgresql://"):
            return sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif sync_url.startswith("postgres://"):
            return sync_url.replace("postgres://", "postgresql+asyncpg://", 1)
        return sync_url

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
