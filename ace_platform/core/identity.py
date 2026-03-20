"""Provider-neutral identity abstractions for hosted OAuth providers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import Request

from ace_platform.config import get_settings
from ace_platform.db.models import OAuthProvider


class OAuthIdentityError(Exception):
    """Raised when an OAuth provider cannot produce a usable identity."""

    def __init__(self, *, reason: str, user_message: str):
        super().__init__(reason)
        self.reason = reason
        self.user_message = user_message


@dataclass(frozen=True)
class OAuthIdentity:
    """Normalized identity payload returned from an OAuth provider."""

    provider_user_id: str
    email: str
    user_info: dict[str, Any]
    access_token: str | None = None
    refresh_token: str | None = None
    token_expires_at: datetime | None = None


@dataclass(frozen=True)
class HostedIdentityProvider:
    """Provider-neutral contract for hosted OAuth providers."""

    provider: OAuthProvider
    display_name: str
    client_id_setting: str
    client_secret_setting: str
    session_state_key: str

    @property
    def key(self) -> str:
        return self.provider.value

    def is_enabled(self) -> bool:
        settings = get_settings()
        return bool(
            getattr(settings, self.client_id_setting, "")
            and getattr(settings, self.client_secret_setting, "")
        )

    def callback_url(self) -> str:
        settings = get_settings()
        return f"{settings.oauth_redirect_base_url}/auth/oauth/{self.key}/callback"

    async def authorize_redirect(self, oauth_registry: Any, request: Request):
        client = getattr(oauth_registry, self.key)
        return await client.authorize_redirect(request, self.callback_url())

    async def exchange_token(self, oauth_registry: Any, request: Request) -> dict[str, Any]:
        client = getattr(oauth_registry, self.key)
        token = await client.authorize_access_token(request)
        return dict(token)

    async def resolve_identity(
        self,
        oauth_registry: Any,
        request: Request,
        token: dict[str, Any],
    ) -> OAuthIdentity:
        if self.provider == OAuthProvider.GOOGLE:
            return await _resolve_google_identity(token)
        if self.provider == OAuthProvider.GITHUB:
            return await _resolve_github_identity(oauth_registry, token)
        raise OAuthIdentityError(
            reason=f"Unsupported OAuth provider: {self.key}",
            user_message=f"{self.display_name} OAuth is not supported.",
        )


async def _resolve_google_identity(token: dict[str, Any]) -> OAuthIdentity:
    user_info = token.get("userinfo")
    if not user_info:
        raise OAuthIdentityError(
            reason="No user info",
            user_message="Failed to get user info from Google",
        )

    email = user_info.get("email")
    if not email:
        raise OAuthIdentityError(
            reason="No email provided",
            user_message="No email provided by Google",
        )

    provider_user_id = user_info.get("sub")
    if not provider_user_id:
        raise OAuthIdentityError(
            reason="No provider user id",
            user_message="Failed to identify your Google account",
        )

    return OAuthIdentity(
        provider_user_id=str(provider_user_id),
        email=email,
        user_info=dict(user_info),
        access_token=token.get("access_token"),
        refresh_token=token.get("refresh_token"),
    )


async def _resolve_github_identity(
    oauth_registry: Any,
    token: dict[str, Any],
) -> OAuthIdentity:
    client = getattr(oauth_registry, OAuthProvider.GITHUB.value)

    try:
        response = await client.get("user", token=token)
        user_info = response.json()
    except Exception as exc:
        raise OAuthIdentityError(
            reason="User info fetch failed",
            user_message="Failed to get user info from GitHub. Please try again.",
        ) from exc

    email = user_info.get("email")
    if not email:
        try:
            emails_response = await client.get("user/emails", token=token)
            emails = emails_response.json()
            primary_email = next(
                (
                    email_payload
                    for email_payload in emails
                    if email_payload.get("primary") and email_payload.get("verified")
                ),
                None,
            )
            if primary_email:
                email = primary_email["email"]
        except Exception:
            email = None

    if not email:
        raise OAuthIdentityError(
            reason="No verified email",
            user_message="No verified email found on GitHub account",
        )

    provider_user_id = user_info.get("id")
    if provider_user_id is None:
        raise OAuthIdentityError(
            reason="No provider user id",
            user_message="Failed to identify your GitHub account",
        )

    return OAuthIdentity(
        provider_user_id=str(provider_user_id),
        email=email,
        user_info=dict(user_info),
        access_token=token.get("access_token"),
        refresh_token=token.get("refresh_token"),
    )


_HOSTED_IDENTITY_PROVIDERS: dict[OAuthProvider, HostedIdentityProvider] = {
    OAuthProvider.GOOGLE: HostedIdentityProvider(
        provider=OAuthProvider.GOOGLE,
        display_name="Google",
        client_id_setting="google_oauth_client_id",
        client_secret_setting="google_oauth_client_secret",
        session_state_key="_state_google_",
    ),
    OAuthProvider.GITHUB: HostedIdentityProvider(
        provider=OAuthProvider.GITHUB,
        display_name="GitHub",
        client_id_setting="github_oauth_client_id",
        client_secret_setting="github_oauth_client_secret",
        session_state_key="_state_github_",
    ),
}


def get_identity_provider(provider: OAuthProvider) -> HostedIdentityProvider:
    """Return the hosted identity provider definition for an OAuth provider."""

    return _HOSTED_IDENTITY_PROVIDERS[provider]


def list_identity_providers() -> tuple[HostedIdentityProvider, ...]:
    """Return the supported hosted identity providers in stable order."""

    return tuple(_HOSTED_IDENTITY_PROVIDERS.values())


def oauth_signup_context_key(provider: OAuthProvider) -> str:
    """Return the session key used to persist OAuth signup context."""

    return f"oauth_signup_context_{provider.value}"
