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
from ace_platform.core.oauth import (
    is_github_oauth_enabled,
    is_google_oauth_enabled,
    oauth,
)
from ace_platform.core.oauth_service import OAuthService
from ace_platform.core.rate_limit import RateLimitOAuth
from ace_platform.core.security import create_access_token, create_refresh_token
from ace_platform.db.models import AcquisitionEvent, AcquisitionEventType, OAuthProvider

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/oauth", tags=["OAuth"])
settings = get_settings()


# =============================================================================
# Response Schemas
# =============================================================================


class OAuthProvidersResponse(BaseModel):
    """Response listing available OAuth providers."""

    google: bool
    github: bool


class LinkedAccountsResponse(BaseModel):
    """Response listing user's linked OAuth accounts."""

    google: bool
    github: bool
    has_password: bool


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


_GOOGLE_SIGNUP_CTX_KEY = "oauth_signup_context_google"
_GITHUB_SIGNUP_CTX_KEY = "oauth_signup_context_github"


def _store_oauth_signup_context(
    request: Request,
    *,
    provider: OAuthProvider,
    anonymous_id: str | None,
    experiment_variant: str | None,
    attribution: dict[str, str] | None,
) -> None:
    """Persist signup attribution context through OAuth redirect flow."""
    key = _GOOGLE_SIGNUP_CTX_KEY if provider == OAuthProvider.GOOGLE else _GITHUB_SIGNUP_CTX_KEY
    request.session[key] = {
        "anonymous_id": anonymous_id,
        "experiment_variant": experiment_variant,
        "attribution": attribution,
    }


def _pop_oauth_signup_context(request: Request, provider: OAuthProvider) -> dict[str, Any]:
    """Pop and return OAuth signup attribution context for a provider."""
    key = _GOOGLE_SIGNUP_CTX_KEY if provider == OAuthProvider.GOOGLE else _GITHUB_SIGNUP_CTX_KEY
    value = request.session.pop(key, None)
    return value if isinstance(value, dict) else {}


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
    return OAuthProvidersResponse(
        google=is_google_oauth_enabled(),
        github=is_github_oauth_enabled(),
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
    if not is_google_oauth_enabled():
        raise HTTPException(status_code=400, detail="Google OAuth not configured")

    # Validate CSRF token
    _validate_oauth_csrf_token(request, csrf_token)

    _store_oauth_signup_context(
        request,
        provider=OAuthProvider.GOOGLE,
        anonymous_id=anonymous_id,
        experiment_variant=experiment_variant or exp_trial_disclosure,
        attribution=attribution_from_query_params(request.query_params),
    )

    redirect_uri = f"{settings.oauth_redirect_base_url}/auth/oauth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: RateLimitOAuth,
):
    """Handle Google OAuth callback.

    Creates or links user account and returns JWT tokens via frontend redirect.
    """
    if not is_google_oauth_enabled():
        raise HTTPException(status_code=400, detail="Google OAuth not configured")

    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        # Log detailed error info to help diagnose OAuth failures
        # Common causes: session cookie lost (missing state), network errors,
        # or Google rejecting the token exchange
        session_has_state = bool(request.session.get("_state_google_"))
        logger.error(
            "Google OAuth token exchange failed: %s: %s (session_has_state=%s)",
            type(e).__name__,
            str(e),
            session_has_state,
            exc_info=True,
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "session_has_state": session_has_state,
                "query_params": dict(request.query_params),
            },
        )
        await audit_oauth_login_failure(
            db, request, provider="google", reason=f"Token exchange failed: {type(e).__name__}: {e}"
        )
        await db.commit()
        return _oauth_error_redirect("Failed to authenticate with Google. Please try again.")

    user_info = token.get("userinfo")
    if not user_info:
        await audit_oauth_login_failure(db, request, provider="google", reason="No user info")
        await db.commit()
        return _oauth_error_redirect("Failed to get user info from Google")

    email = user_info.get("email")
    if not email:
        await audit_oauth_login_failure(db, request, provider="google", reason="No email provided")
        await db.commit()
        return _oauth_error_redirect("No email provided by Google")

    # Get or create user
    oauth_service = OAuthService(db)
    user, is_new = await oauth_service.get_or_create_user_from_oauth(
        provider=OAuthProvider.GOOGLE,
        provider_user_id=user_info["sub"],
        email=email,
        user_info=dict(user_info),
        access_token=token.get("access_token"),
        refresh_token=token.get("refresh_token"),
        token_expires_at=None,  # Google tokens handled differently
    )
    signup_context = _pop_oauth_signup_context(request, OAuthProvider.GOOGLE)
    tracking_enabled = settings.acquisition_tracking_enabled

    if tracking_enabled and is_new:
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

        event_data: dict[str, Any] = {"method": "oauth", "provider": "google"}
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

    if not user.is_active:
        await audit_oauth_login_failure(
            db, request, provider="google", reason="Account disabled", email=email
        )
        await db.commit()
        return _oauth_error_redirect("Account is disabled")

    # Check if this is a new IP BEFORE logging (to avoid race condition)
    # Only for existing users (not new signups)
    should_send_alert = False
    client_ip = None
    if not is_new:
        client_ip = get_client_ip(request)
        if client_ip:
            is_new_ip = await is_new_ip_for_user(db, user.id, client_ip)
            should_send_alert = is_new_ip

    # Audit log the successful OAuth login
    await audit_oauth_login_success(db, user.id, request, provider="google", is_new_user=is_new)
    await db.commit()

    # Send notification after commit if needed
    if should_send_alert:
        await send_new_login_alert(
            to_email=user.email,
            ip_address=client_ip,
            login_time=datetime.now(UTC),
            user_agent=get_user_agent(request),
        )

    # Create JWT tokens
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    # Redirect to frontend with tokens
    return _oauth_success_redirect(access_token, refresh_token, is_new)


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
    if not is_github_oauth_enabled():
        raise HTTPException(status_code=400, detail="GitHub OAuth not configured")

    # Validate CSRF token
    _validate_oauth_csrf_token(request, csrf_token)

    _store_oauth_signup_context(
        request,
        provider=OAuthProvider.GITHUB,
        anonymous_id=anonymous_id,
        experiment_variant=experiment_variant or exp_trial_disclosure,
        attribution=attribution_from_query_params(request.query_params),
    )

    redirect_uri = f"{settings.oauth_redirect_base_url}/auth/oauth/github/callback"
    return await oauth.github.authorize_redirect(request, redirect_uri)


@router.get("/github/callback")
async def github_callback(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: RateLimitOAuth,
):
    """Handle GitHub OAuth callback.

    Creates or links user account and returns JWT tokens via frontend redirect.
    """
    if not is_github_oauth_enabled():
        raise HTTPException(status_code=400, detail="GitHub OAuth not configured")

    try:
        token = await oauth.github.authorize_access_token(request)
    except Exception as e:
        session_has_state = bool(request.session.get("_state_github_"))
        logger.error(
            "GitHub OAuth token exchange failed: %s: %s (session_has_state=%s)",
            type(e).__name__,
            str(e),
            session_has_state,
            exc_info=True,
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "session_has_state": session_has_state,
                "query_params": dict(request.query_params),
            },
        )
        await audit_oauth_login_failure(
            db, request, provider="github", reason=f"Token exchange failed: {type(e).__name__}: {e}"
        )
        await db.commit()
        return _oauth_error_redirect("Failed to authenticate with GitHub. Please try again.")

    # GitHub requires separate API call to get user info
    try:
        resp = await oauth.github.get("user", token=token)
        user_info = resp.json()
    except Exception as e:
        logger.error("GitHub user info fetch failed", exc_info=True, extra={"error": str(e)})
        await audit_oauth_login_failure(
            db, request, provider="github", reason="User info fetch failed"
        )
        await db.commit()
        return _oauth_error_redirect("Failed to get user info from GitHub. Please try again.")

    # GitHub may not return email in user endpoint, fetch from emails endpoint
    email = user_info.get("email")
    if not email:
        try:
            emails_resp = await oauth.github.get("user/emails", token=token)
            emails = emails_resp.json()
            primary_email = next(
                (e for e in emails if e.get("primary") and e.get("verified")),
                None,
            )
            if primary_email:
                email = primary_email["email"]
        except Exception as e:
            logger.warning(
                "GitHub email fetch failed, will check for email in user info",
                extra={"error": str(e)},
            )

    if not email:
        await audit_oauth_login_failure(db, request, provider="github", reason="No verified email")
        await db.commit()
        return _oauth_error_redirect("No verified email found on GitHub account")

    # Get or create user
    oauth_service = OAuthService(db)
    user, is_new = await oauth_service.get_or_create_user_from_oauth(
        provider=OAuthProvider.GITHUB,
        provider_user_id=str(user_info["id"]),
        email=email,
        user_info=user_info,
        access_token=token.get("access_token"),
        refresh_token=token.get("refresh_token"),
    )
    signup_context = _pop_oauth_signup_context(request, OAuthProvider.GITHUB)
    tracking_enabled = settings.acquisition_tracking_enabled

    if tracking_enabled and is_new:
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

        event_data: dict[str, Any] = {"method": "oauth", "provider": "github"}
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

    if not user.is_active:
        await audit_oauth_login_failure(
            db, request, provider="github", reason="Account disabled", email=email
        )
        await db.commit()
        return _oauth_error_redirect("Account is disabled")

    # Check if this is a new IP BEFORE logging (to avoid race condition)
    # Only for existing users (not new signups)
    should_send_alert = False
    client_ip = None
    if not is_new:
        client_ip = get_client_ip(request)
        if client_ip:
            is_new_ip = await is_new_ip_for_user(db, user.id, client_ip)
            should_send_alert = is_new_ip

    # Audit log the successful OAuth login
    await audit_oauth_login_success(db, user.id, request, provider="github", is_new_user=is_new)
    await db.commit()

    # Send notification after commit if needed
    if should_send_alert:
        await send_new_login_alert(
            to_email=user.email,
            ip_address=client_ip,
            login_time=datetime.now(UTC),
            user_agent=get_user_agent(request),
        )

    # Create JWT tokens
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    return _oauth_success_redirect(access_token, refresh_token, is_new)


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

    providers = {acc.provider for acc in accounts}
    return LinkedAccountsResponse(
        google=OAuthProvider.GOOGLE in providers,
        github=OAuthProvider.GITHUB in providers,
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
