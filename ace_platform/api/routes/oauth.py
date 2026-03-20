"""OAuth authentication routes for Google and GitHub login.

This module provides REST API endpoints for:
- Provider discovery (GET /auth/oauth/providers)
- CSRF token generation (GET /auth/oauth/csrf-token)
- Google OAuth flow (GET /auth/oauth/google/login, /auth/oauth/google/callback)
- GitHub OAuth flow (GET /auth/oauth/github/login, /auth/oauth/github/callback)
- Account linking (GET /auth/oauth/accounts, DELETE /auth/oauth/accounts/{provider})

CSRF Protection:
OAuth login endpoints require a valid CSRF token to prevent login CSRF attacks.
The frontend should:
1. Call GET /auth/oauth/csrf-token to get a token
2. Include the token as ?csrf_token=xxx when redirecting to login
"""

import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.api.auth import RequiredUser
from ace_platform.api.deps import get_db
from ace_platform.api.middleware import (
    ensure_csrf_token,
    validate_csrf_token_value,
)
from ace_platform.config import get_settings
from ace_platform.core.acquisition import (
    attribution_from_query_params,
    parse_signup_attribution,
)
from ace_platform.core.audit import (
    audit_oauth_account_unlinked,
    audit_oauth_login_failure,
    audit_oauth_login_success,
    get_client_ip,
    get_user_agent,
    is_new_ip_for_user,
)
from ace_platform.core.email import send_new_login_alert
from ace_platform.core.identity import (
    HostedIdentityProvider,
    OAuthIdentityError,
    get_identity_provider,
    list_identity_providers,
    oauth_signup_context_key,
)
from ace_platform.core.oauth import (
    oauth,
)
from ace_platform.core.oauth_service import OAuthService
from ace_platform.core.rate_limit import RateLimitOAuth
from ace_platform.core.security import create_access_token, create_refresh_token
from ace_platform.core.workspaces import bootstrap_workspace_for_user
from ace_platform.db.models import AcquisitionEvent, AcquisitionEventType, OAuthProvider

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/oauth", tags=["OAuth"])
settings = get_settings()


# =============================================================================
# Response Schemas
# =============================================================================


class OAuthProvidersResponse(BaseModel):
    """Response listing available OAuth providers."""

    providers: list["OAuthProviderStatus"]
    google: bool = False
    github: bool = False


class OAuthProviderStatus(BaseModel):
    """Provider metadata exposed through the provider-neutral auth interface."""

    provider: str
    display_name: str
    enabled: bool


class LinkedAccountsResponse(BaseModel):
    """Response listing user's linked OAuth accounts."""

    providers: list["LinkedAccountStatus"]
    google: bool = False
    github: bool = False
    has_password: bool


class LinkedAccountStatus(BaseModel):
    """Linked-account status for a hosted identity provider."""

    provider: str
    display_name: str
    linked: bool


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str


class CSRFTokenResponse(BaseModel):
    """Response containing CSRF token for OAuth flows."""

    csrf_token: str


# =============================================================================
# CSRF Token
# =============================================================================


def _validate_oauth_csrf_token(request: Request, csrf_token: str | None) -> None:
    """Validate CSRF token for OAuth login endpoints.

    Uses the shared CSRF validation with OAuth-specific error messages and
    single-use token behavior (token is consumed after validation).

    Args:
        request: The incoming request with session.
        csrf_token: The CSRF token from query parameter.

    Raises:
        HTTPException: If CSRF validation fails.
    """
    validate_csrf_token_value(
        request,
        csrf_token,
        consume_token=True,  # OAuth tokens are single-use
        error_detail_missing_session="CSRF token missing from session. Please get a token first via /auth/oauth/csrf-token",
        error_detail_missing_token="CSRF token required. Include ?csrf_token=xxx in the OAuth login URL.",
        error_detail_mismatch="CSRF token validation failed. Please get a fresh token and try again.",
    )


def _store_oauth_signup_context(
    request: Request,
    *,
    provider: OAuthProvider,
    anonymous_id: str | None,
    experiment_variant: str | None,
    attribution: dict[str, str] | None,
) -> None:
    """Persist signup attribution context through OAuth redirect flow."""
    request.session[oauth_signup_context_key(provider)] = {
        "anonymous_id": anonymous_id,
        "experiment_variant": experiment_variant,
        "attribution": attribution,
    }


def _pop_oauth_signup_context(request: Request, provider: OAuthProvider) -> dict[str, Any]:
    """Pop and return OAuth signup attribution context for a provider."""
    value = request.session.pop(oauth_signup_context_key(provider), None)
    return value if isinstance(value, dict) else {}


def _legacy_provider_flags(
    statuses: list[OAuthProviderStatus] | list[LinkedAccountStatus],
    attr_name: str,
) -> dict[str, bool]:
    flags = {"google": False, "github": False}
    for provider_status in statuses:
        provider = getattr(provider_status, "provider", None)
        if provider in flags:
            flags[provider] = bool(getattr(provider_status, attr_name))
    return flags


def _build_oauth_provider_statuses() -> list[OAuthProviderStatus]:
    return [
        OAuthProviderStatus(
            provider=provider.key,
            display_name=provider.display_name,
            enabled=provider.is_enabled(),
        )
        for provider in list_identity_providers()
    ]


def _apply_oauth_signup_context(
    *,
    db: AsyncSession,
    user,
    signup_context: dict[str, Any],
    provider: HostedIdentityProvider,
) -> None:
    anonymous_id = signup_context.get("anonymous_id")
    experiment_variant = signup_context.get("experiment_variant")
    attribution = signup_context.get("attribution")
    parsed_attribution = parse_signup_attribution(attribution)

    user.signup_source = parsed_attribution.source
    user.signup_channel = parsed_attribution.channel
    user.signup_campaign = parsed_attribution.campaign
    user.signup_anonymous_id = anonymous_id
    user.signup_variant = experiment_variant
    user.signup_attribution = parsed_attribution.snapshot

    event_data: dict[str, Any] = {"method": "oauth", "provider": provider.key}
    if parsed_attribution.snapshot:
        event_data["attribution"] = parsed_attribution.snapshot

    db.add(
        AcquisitionEvent(
            user_id=user.id,
            event_type=AcquisitionEventType.REGISTER_SUCCESS,
            anonymous_id=anonymous_id,
            source=parsed_attribution.source,
            channel=parsed_attribution.channel,
            campaign=parsed_attribution.campaign,
            experiment_variant=experiment_variant,
            event_data=event_data,
        )
    )


async def _oauth_login(
    provider: HostedIdentityProvider,
    request: Request,
    csrf_token: str | None,
    anonymous_id: str | None,
    experiment_variant: str | None,
) -> RedirectResponse:
    if not provider.is_enabled():
        raise HTTPException(status_code=400, detail=f"{provider.display_name} OAuth not configured")

    _validate_oauth_csrf_token(request, csrf_token)

    _store_oauth_signup_context(
        request,
        provider=provider.provider,
        anonymous_id=anonymous_id,
        experiment_variant=experiment_variant,
        attribution=attribution_from_query_params(request.query_params),
    )
    return await provider.authorize_redirect(oauth, request)


async def _oauth_callback(
    provider: HostedIdentityProvider,
    request: Request,
    db: AsyncSession,
) -> RedirectResponse:
    if not provider.is_enabled():
        raise HTTPException(status_code=400, detail=f"{provider.display_name} OAuth not configured")

    try:
        token = await provider.exchange_token(oauth, request)
    except Exception as exc:
        session_has_state = bool(request.session.get(provider.session_state_key))
        logger.error(
            "%s OAuth token exchange failed: %s: %s (session_has_state=%s)",
            provider.display_name,
            type(exc).__name__,
            str(exc),
            session_has_state,
            exc_info=True,
            extra={
                "error": str(exc),
                "error_type": type(exc).__name__,
                "provider": provider.key,
                "session_has_state": session_has_state,
                "query_params": dict(request.query_params),
            },
        )
        await audit_oauth_login_failure(
            db,
            request,
            provider=provider.key,
            reason=f"Token exchange failed: {type(exc).__name__}: {exc}",
        )
        await db.commit()
        return _oauth_error_redirect(
            f"Failed to authenticate with {provider.display_name}. Please try again."
        )

    try:
        identity = await provider.resolve_identity(oauth, request, token)
    except OAuthIdentityError as exc:
        logger.warning(
            "%s OAuth identity resolution failed: %s",
            provider.display_name,
            exc.reason,
            extra={"provider": provider.key},
        )
        await audit_oauth_login_failure(
            db,
            request,
            provider=provider.key,
            reason=exc.reason,
        )
        await db.commit()
        return _oauth_error_redirect(exc.user_message)

    oauth_service = OAuthService(db)
    user, is_new = await oauth_service.get_or_create_user_from_oauth(
        provider=provider.provider,
        provider_user_id=identity.provider_user_id,
        email=identity.email,
        user_info=identity.user_info,
        access_token=identity.access_token,
        refresh_token=identity.refresh_token,
        token_expires_at=identity.token_expires_at,
    )
    signup_context = _pop_oauth_signup_context(request, provider.provider)

    if settings.acquisition_tracking_enabled and is_new:
        _apply_oauth_signup_context(
            db=db,
            user=user,
            signup_context=signup_context,
            provider=provider,
        )

    if not user.is_active:
        await audit_oauth_login_failure(
            db,
            request,
            provider=provider.key,
            reason="Account disabled",
            email=identity.email,
        )
        await db.commit()
        return _oauth_error_redirect("Account is disabled")

    await bootstrap_workspace_for_user(db, user)

    should_send_alert = False
    client_ip = None
    if not is_new:
        client_ip = get_client_ip(request)
        if client_ip:
            should_send_alert = await is_new_ip_for_user(db, user.id, client_ip)

    await audit_oauth_login_success(
        db,
        user.id,
        request,
        provider=provider.key,
        is_new_user=is_new,
    )
    await db.commit()

    if should_send_alert:
        await send_new_login_alert(
            to_email=user.email,
            ip_address=client_ip,
            login_time=datetime.now(UTC),
            user_agent=get_user_agent(request),
        )

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    return _oauth_success_redirect(access_token, refresh_token, is_new)


@router.get("/csrf-token", response_model=CSRFTokenResponse)
async def get_csrf_token(request: Request) -> CSRFTokenResponse:
    """Get a CSRF token for OAuth login.

    This endpoint generates a CSRF token and stores it in the session.
    The frontend should call this before initiating OAuth login, then
    include the token in the login URL as a query parameter.

    The token is single-use - after OAuth login validation, it is invalidated.

    Returns:
        CSRFTokenResponse with the CSRF token.
    """
    token = ensure_csrf_token(request)
    return CSRFTokenResponse(csrf_token=token)


# =============================================================================
# Provider Discovery
# =============================================================================


@router.get("/providers", response_model=OAuthProvidersResponse)
async def get_oauth_providers() -> OAuthProvidersResponse:
    """Get list of enabled OAuth providers.

    Returns which OAuth providers are configured and available for login.
    """
    providers = _build_oauth_provider_statuses()
    legacy_flags = _legacy_provider_flags(providers, "enabled")
    return OAuthProvidersResponse(
        providers=providers,
        google=legacy_flags["google"],
        github=legacy_flags["github"],
    )


# =============================================================================
# Google OAuth
# =============================================================================


@router.get("/google/login")
async def google_login(
    request: Request,
    _: RateLimitOAuth,
    csrf_token: Annotated[str | None, Query(description="CSRF token from /csrf-token")] = None,
    anonymous_id: Annotated[str | None, Query(max_length=128)] = None,
    experiment_variant: Annotated[str | None, Query(max_length=100)] = None,
    exp_trial_disclosure: Annotated[str | None, Query(max_length=100)] = None,
    src: Annotated[str | None, Query(max_length=64)] = None,
    source: Annotated[str | None, Query(max_length=64)] = None,
    channel: Annotated[str | None, Query(max_length=64)] = None,
    campaign: Annotated[str | None, Query(max_length=255)] = None,
    aid: Annotated[str | None, Query(max_length=128)] = None,
    referrer_host: Annotated[str | None, Query(max_length=255)] = None,
    landing_path: Annotated[str | None, Query(max_length=512)] = None,
    device_type: Annotated[str | None, Query(max_length=64)] = None,
    utm_source: Annotated[str | None, Query(max_length=255)] = None,
    utm_medium: Annotated[str | None, Query(max_length=255)] = None,
    utm_campaign: Annotated[str | None, Query(max_length=255)] = None,
    utm_term: Annotated[str | None, Query(max_length=255)] = None,
    utm_content: Annotated[str | None, Query(max_length=255)] = None,
):
    """Initiate Google OAuth login flow.

    Requires a valid CSRF token to prevent login CSRF attacks.
    Get a token from GET /auth/oauth/csrf-token first.

    Redirects the user to Google's OAuth consent screen.
    """
    return await _oauth_login(
        get_identity_provider(OAuthProvider.GOOGLE),
        request,
        csrf_token,
        anonymous_id,
        experiment_variant or exp_trial_disclosure,
    )


@router.get("/google/callback")
async def google_callback(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: RateLimitOAuth,
):
    """Handle Google OAuth callback.

    Creates or links user account and returns JWT tokens via frontend redirect.
    """
    return await _oauth_callback(get_identity_provider(OAuthProvider.GOOGLE), request, db)


# =============================================================================
# GitHub OAuth
# =============================================================================


@router.get("/github/login")
async def github_login(
    request: Request,
    _: RateLimitOAuth,
    csrf_token: Annotated[str | None, Query(description="CSRF token from /csrf-token")] = None,
    anonymous_id: Annotated[str | None, Query(max_length=128)] = None,
    experiment_variant: Annotated[str | None, Query(max_length=100)] = None,
    exp_trial_disclosure: Annotated[str | None, Query(max_length=100)] = None,
    src: Annotated[str | None, Query(max_length=64)] = None,
    source: Annotated[str | None, Query(max_length=64)] = None,
    channel: Annotated[str | None, Query(max_length=64)] = None,
    campaign: Annotated[str | None, Query(max_length=255)] = None,
    aid: Annotated[str | None, Query(max_length=128)] = None,
    referrer_host: Annotated[str | None, Query(max_length=255)] = None,
    landing_path: Annotated[str | None, Query(max_length=512)] = None,
    device_type: Annotated[str | None, Query(max_length=64)] = None,
    utm_source: Annotated[str | None, Query(max_length=255)] = None,
    utm_medium: Annotated[str | None, Query(max_length=255)] = None,
    utm_campaign: Annotated[str | None, Query(max_length=255)] = None,
    utm_term: Annotated[str | None, Query(max_length=255)] = None,
    utm_content: Annotated[str | None, Query(max_length=255)] = None,
):
    """Initiate GitHub OAuth login flow.

    Requires a valid CSRF token to prevent login CSRF attacks.
    Get a token from GET /auth/oauth/csrf-token first.

    Redirects the user to GitHub's OAuth consent screen.
    """
    return await _oauth_login(
        get_identity_provider(OAuthProvider.GITHUB),
        request,
        csrf_token,
        anonymous_id,
        experiment_variant or exp_trial_disclosure,
    )


@router.get("/github/callback")
async def github_callback(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: RateLimitOAuth,
):
    """Handle GitHub OAuth callback.

    Creates or links user account and returns JWT tokens via frontend redirect.
    """
    return await _oauth_callback(get_identity_provider(OAuthProvider.GITHUB), request, db)


# =============================================================================
# Account Linking (for authenticated users)
# =============================================================================


@router.get("/accounts", response_model=LinkedAccountsResponse)
async def get_linked_accounts(
    user: RequiredUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LinkedAccountsResponse:
    """Get OAuth accounts linked to current user.

    Returns which providers are connected and whether user has a password set.
    """
    oauth_service = OAuthService(db)
    accounts = await oauth_service.get_user_oauth_accounts(user.id)

    linked_provider_values = {acc.provider.value for acc in accounts}
    providers = [
        LinkedAccountStatus(
            provider=provider.key,
            display_name=provider.display_name,
            linked=provider.key in linked_provider_values,
        )
        for provider in list_identity_providers()
    ]
    legacy_flags = _legacy_provider_flags(providers, "linked")
    return LinkedAccountsResponse(
        providers=providers,
        google=legacy_flags["google"],
        github=legacy_flags["github"],
        has_password=user.hashed_password is not None,
    )


@router.delete("/accounts/{provider}", response_model=MessageResponse)
async def unlink_account(
    provider: str,
    request: Request,
    user: RequiredUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageResponse:
    """Unlink an OAuth provider from current user.

    Cannot unlink if it would leave the user with no authentication method.
    """
    try:
        oauth_provider = OAuthProvider(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid provider")

    oauth_service = OAuthService(db)
    try:
        unlinked = await oauth_service.unlink_oauth_account(user.id, oauth_provider)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not unlinked:
        raise HTTPException(status_code=404, detail="OAuth account not found")

    # Audit log the OAuth account unlink
    await audit_oauth_account_unlinked(db, user.id, request, provider=provider)
    await db.commit()

    return MessageResponse(message=f"{provider.title()} account unlinked")


# =============================================================================
# Helpers
# =============================================================================


def _oauth_success_redirect(
    access_token: str,
    refresh_token: str,
    is_new_user: bool,
) -> RedirectResponse:
    """Redirect to frontend with OAuth tokens.

    Uses fragment identifier (#) instead of query params (?) to prevent:
    - Token leakage via browser history
    - Token exposure in server logs and referrer headers
    - Token visibility to analytics and CDNs
    """
    params = urlencode(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "is_new": str(is_new_user).lower(),
        }
    )
    return RedirectResponse(
        url=f"{settings.frontend_url}/oauth/callback#{params}",
        status_code=status.HTTP_302_FOUND,
    )


def _oauth_error_redirect(error: str) -> RedirectResponse:
    """Redirect to frontend with OAuth error."""
    params = urlencode({"error": error})
    return RedirectResponse(
        url=f"{settings.frontend_url}/oauth/callback?{params}",
        status_code=status.HTTP_302_FOUND,
    )
