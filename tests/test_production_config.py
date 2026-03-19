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
            session_cookie_secure=True,
        )
        assert settings.jwt_secret_key == "a-real-production-secret-key"
        assert settings.session_secret_key == "a-real-session-secret-key"
        assert settings.session_cookie_secure is True

    def test_development_allows_empty_session_secret(self):
        """Empty session secret is allowed in development (falls back to JWT key)."""
        settings = Settings(
            environment="development",
            session_secret_key="",
        )
        assert settings.session_secret_key == ""

    def test_production_requires_secure_session_cookie(self):
        """Production rejects insecure OAuth session cookies."""
        with pytest.raises(ValidationError, match="SESSION_COOKIE_SECURE must be true"):
            Settings(
                environment="production",
                jwt_secret_key="a-real-production-secret-key",
                session_secret_key="a-real-session-secret-key",
                session_cookie_secure=False,
            )

    def test_staging_requires_secure_session_cookie(self):
        """Staging rejects insecure OAuth session cookies."""
        with pytest.raises(ValidationError, match="SESSION_COOKIE_SECURE must be true"):
            Settings(
                environment="staging",
                jwt_secret_key="a-real-staging-secret-key",
                session_secret_key="a-real-staging-session-secret-key",
                session_cookie_secure=False,
            )

    def test_rejects_invalid_session_cookie_samesite(self):
        """SameSite value must be one of lax/strict/none."""
        with pytest.raises(
            ValidationError, match="SESSION_COOKIE_SAMESITE must be one of: lax, strict, none"
        ):
            Settings(
                environment="production",
                jwt_secret_key="a-real-production-secret-key",
                session_secret_key="a-real-session-secret-key",
                session_cookie_secure=True,
                session_cookie_samesite="invalid",
            )

    def test_production_rejects_strict_samesite_with_oauth(self):
        """Strict SameSite can break OAuth callback state cookies."""
        with pytest.raises(
            ValidationError, match="SESSION_COOKIE_SAMESITE='strict' can break OAuth callbacks"
        ):
            Settings(
                environment="production",
                jwt_secret_key="a-real-production-secret-key",
                session_secret_key="a-real-session-secret-key",
                session_cookie_secure=True,
                session_cookie_samesite="strict",
                google_oauth_client_id="google-client-id",
                google_oauth_client_secret="google-client-secret",
            )

    def test_production_accepts_lax_samesite_with_oauth(self):
        """Lax SameSite works for OAuth callback redirects."""
        settings = Settings(
            environment="production",
            jwt_secret_key="a-real-production-secret-key",
            session_secret_key="a-real-session-secret-key",
            session_cookie_secure=True,
            session_cookie_samesite="lax",
            google_oauth_client_id="google-client-id",
            google_oauth_client_secret="google-client-secret",
        )
        assert settings.session_cookie_samesite == "lax"

    def test_rejects_session_cookie_domain_with_scheme(self):
        """Cookie domain must be a bare domain hostname."""
        with pytest.raises(ValidationError, match="SESSION_COOKIE_DOMAIN must be a bare domain"):
            Settings(
                environment="production",
                jwt_secret_key="a-real-production-secret-key",
                session_secret_key="a-real-session-secret-key",
                session_cookie_secure=True,
                session_cookie_domain="https://aceagent.io",
            )

    def test_production_rejects_non_parent_session_cookie_domain(self):
        """Production/staging should use a parent domain for shared OAuth cookies."""
        with pytest.raises(
            ValidationError, match="SESSION_COOKIE_DOMAIN should be a parent domain"
        ):
            Settings(
                environment="production",
                jwt_secret_key="a-real-production-secret-key",
                session_secret_key="a-real-session-secret-key",
                session_cookie_secure=True,
                session_cookie_domain="localhost",
            )

    def test_production_accepts_parent_session_cookie_domain(self):
        """Parent-domain cookie setting is accepted in production."""
        settings = Settings(
            environment="production",
            jwt_secret_key="a-real-production-secret-key",
            session_secret_key="a-real-session-secret-key",
            session_cookie_secure=True,
            session_cookie_domain=".aceagent.io",
        )
        assert settings.session_cookie_domain == ".aceagent.io"


class TestEvolutionDefaults:
    """Tests for evolution model defaults."""

    def test_defaults_use_gpt_5_4_with_medium_reasoning(self, monkeypatch):
        """Evolution should default to GPT-5.4 Thinking with medium effort."""
        for env_var in (
            "EVOLUTION_GENERATOR_MODEL",
            "EVOLUTION_REFLECTOR_MODEL",
            "EVOLUTION_CURATOR_MODEL",
            "EVOLUTION_REASONING_EFFORT",
        ):
            monkeypatch.delenv(env_var, raising=False)

        settings = Settings(_env_file=None, environment="development")

        assert settings.evolution_generator_model == "gpt-5.4"
        assert settings.evolution_reflector_model == "gpt-5.4"
        assert settings.evolution_curator_model == "gpt-5.4"
        assert settings.evolution_reasoning_effort == "medium"
