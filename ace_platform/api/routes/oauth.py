"""OAuth authentication routes for Google and GitHub login.

This module provides REST API endpoints for:
- Provider discovery (GET /auth/oauth/providers)
- Google OAuth flow (GET /auth/oauth/google/login, /auth/oauth/google/callback)
- GitHub OAuth flow (GET /auth/oauth/github/login, /auth/oauth/github/callback)
- Account linking (GET /auth/oauth/accounts, DELETE /auth/oauth/accounts/{provider})
"""

import logging
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.api.auth import RequiredUser
from ace_platform.api.deps import get_db
from ace_platform.config import get_settings
from ace_platform.core.oauth import (
    is_github_oauth_enabled,
    is_google_oauth_enabled,
    oauth,
)
from ace_platform.core.oauth_service import OAuthService
from ace_platform.core.rate_limit import RateLimitOAuth
from ace_platform.core.security import create_access_token, create_refresh_token
from ace_platform.db.models import OAuthProvider

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
async def google_login(request: Request, _: RateLimitOAuth):
    """Initiate Google OAuth login flow.

    Redirects the user to Google's OAuth consent screen.
    """
    if not is_google_oauth_enabled():
        raise HTTPException(status_code=400, detail="Google OAuth not configured")

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
        logger.error("Google OAuth token exchange failed", exc_info=True, extra={"error": str(e)})
        return _oauth_error_redirect("Failed to authenticate with Google. Please try again.")

    user_info = token.get("userinfo")
    if not user_info:
        return _oauth_error_redirect("Failed to get user info from Google")

    email = user_info.get("email")
    if not email:
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

    if not user.is_active:
        return _oauth_error_redirect("Account is disabled")

    # Create JWT tokens
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    # Redirect to frontend with tokens
    return _oauth_success_redirect(access_token, refresh_token, is_new)


# =============================================================================
# GitHub OAuth
# =============================================================================


@router.get("/github/login")
async def github_login(request: Request, _: RateLimitOAuth):
    """Initiate GitHub OAuth login flow.

    Redirects the user to GitHub's OAuth consent screen.
    """
    if not is_github_oauth_enabled():
        raise HTTPException(status_code=400, detail="GitHub OAuth not configured")

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
        logger.error("GitHub OAuth token exchange failed", exc_info=True, extra={"error": str(e)})
        return _oauth_error_redirect("Failed to authenticate with GitHub. Please try again.")

    # GitHub requires separate API call to get user info
    try:
        resp = await oauth.github.get("user", token=token)
        user_info = resp.json()
    except Exception as e:
        logger.error("GitHub user info fetch failed", exc_info=True, extra={"error": str(e)})
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

    if not user.is_active:
        return _oauth_error_redirect("Account is disabled")

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
