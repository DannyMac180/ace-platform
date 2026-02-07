"""Tests for production configuration validation.

These tests verify that insecure secret defaults are rejected
when ENVIRONMENT is set to production or staging.
"""

import pytest
from pydantic import ValidationError

from ace_platform.config import Settings


class TestProductionConfigValidation:
    """Tests for validate_production_secrets model validator."""

    def test_development_allows_default_jwt_secret(self):
        """Default JWT secret is allowed in development."""
        settings = Settings(
            environment="development",
            jwt_secret_key="change-me-in-production",
        )
        assert settings.jwt_secret_key == "change-me-in-production"

    def test_production_rejects_default_jwt_secret(self):
        """Default JWT secret is rejected in production."""
        with pytest.raises(ValidationError, match="JWT_SECRET_KEY must be explicitly set"):
            Settings(
                environment="production",
                jwt_secret_key="change-me-in-production",
                session_secret_key="some-session-secret",
            )

    def test_staging_rejects_default_jwt_secret(self):
        """Default JWT secret is rejected in staging."""
        with pytest.raises(ValidationError, match="JWT_SECRET_KEY must be explicitly set"):
            Settings(
                environment="staging",
                jwt_secret_key="change-me-in-production",
                session_secret_key="some-session-secret",
            )

    def test_production_rejects_empty_jwt_secret(self):
        """Empty JWT secret is rejected in production."""
        with pytest.raises(ValidationError, match="JWT_SECRET_KEY must be explicitly set"):
            Settings(
                environment="production",
                jwt_secret_key="",
                session_secret_key="some-session-secret",
            )

    def test_production_requires_session_secret(self):
        """Empty session secret is rejected in production."""
        with pytest.raises(ValidationError, match="SESSION_SECRET_KEY must be explicitly set"):
            Settings(
                environment="production",
                jwt_secret_key="a-real-production-secret-key",
                session_secret_key="",
            )

    def test_production_accepts_proper_secrets(self):
        """Proper secrets are accepted in production."""
        settings = Settings(
            environment="production",
            jwt_secret_key="a-real-production-secret-key",
            session_secret_key="a-real-session-secret-key",
        )
        assert settings.jwt_secret_key == "a-real-production-secret-key"
        assert settings.session_secret_key == "a-real-session-secret-key"

    def test_development_allows_empty_session_secret(self):
        """Empty session secret is allowed in development (falls back to JWT key)."""
        settings = Settings(
            environment="development",
            session_secret_key="",
        )
        assert settings.session_secret_key == ""
