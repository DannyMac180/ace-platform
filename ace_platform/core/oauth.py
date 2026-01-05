"""OAuth client configuration using Authlib.

This module sets up OAuth clients for Google and GitHub authentication.
Clients are only registered if their credentials are configured in environment variables.
"""

from authlib.integrations.starlette_client import OAuth

from ace_platform.config import get_settings

# Initialize OAuth registry
oauth = OAuth()

# Settings are accessed lazily to avoid issues during import
_settings = None


def _get_settings():
    """Get settings lazily to avoid import-time issues."""
    global _settings
    if _settings is None:
        _settings = get_settings()
    return _settings


def setup_oauth():
    """Configure OAuth clients based on environment settings.

    This should be called during app startup to register OAuth providers.
    """
    settings = _get_settings()

    # Register Google OAuth client
    if settings.google_oauth_client_id and settings.google_oauth_client_secret:
        oauth.register(
            name="google",
            client_id=settings.google_oauth_client_id,
            client_secret=settings.google_oauth_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={
                "scope": "openid email profile",
            },
        )

    # Register GitHub OAuth client
    if settings.github_oauth_client_id and settings.github_oauth_client_secret:
        oauth.register(
            name="github",
            client_id=settings.github_oauth_client_id,
            client_secret=settings.github_oauth_client_secret,
            access_token_url="https://github.com/login/oauth/access_token",
            authorize_url="https://github.com/login/oauth/authorize",
            api_base_url="https://api.github.com/",
            client_kwargs={
                "scope": "read:user user:email",
            },
        )


def is_google_oauth_enabled() -> bool:
    """Check if Google OAuth is configured."""
    settings = _get_settings()
    return bool(settings.google_oauth_client_id and settings.google_oauth_client_secret)


def is_github_oauth_enabled() -> bool:
    """Check if GitHub OAuth is configured."""
    settings = _get_settings()
    return bool(settings.github_oauth_client_id and settings.github_oauth_client_secret)
