"""Focused tests for the hosted OAuth callback and token-storage flow."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ace_platform.core.identity import OAuthIdentity
from ace_platform.core.oauth_tokens import is_encrypted_oauth_token
from ace_platform.db.models import OAuthProvider, User, UserOAuthAccount


def _make_mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.flush = AsyncMock()
    db.get = AsyncMock()
    db.execute = AsyncMock()
    db.delete = AsyncMock()
    return db


def _make_user(email: str = "oauth@example.com") -> User:
    now = datetime.now(timezone.utc)
    return User(
        id=uuid4(),
        email=email,
        hashed_password=None,
        is_active=True,
        email_verified=True,
        created_at=now,
        updated_at=now,
    )


def _make_oauth_account(provider: OAuthProvider = OAuthProvider.GOOGLE) -> UserOAuthAccount:
    now = datetime.now(timezone.utc)
    return UserOAuthAccount(
        id=uuid4(),
        user_id=uuid4(),
        provider=provider,
        provider_user_id="provider-user-123",
        provider_email="oauth@example.com",
        created_at=now,
        updated_at=now,
    )


def test_user_oauth_account_encrypts_tokens_at_rest():
    account = _make_oauth_account()
    account.access_token = "provider-access-token"
    account.refresh_token = "provider-refresh-token"

    assert account.access_token == "provider-access-token"
    assert account.refresh_token == "provider-refresh-token"
    assert account._access_token_ciphertext != "provider-access-token"
    assert account._refresh_token_ciphertext != "provider-refresh-token"
    assert is_encrypted_oauth_token(account._access_token_ciphertext) is True
    assert is_encrypted_oauth_token(account._refresh_token_ciphertext) is True


def test_user_oauth_account_reads_legacy_plaintext_tokens():
    account = _make_oauth_account()
    account._access_token_ciphertext = "legacy-access-token"
    account._refresh_token_ciphertext = "legacy-refresh-token"

    assert account.access_token == "legacy-access-token"
    assert account.refresh_token == "legacy-refresh-token"


@pytest.mark.asyncio
async def test_oauth_service_encrypts_tokens_for_new_user(monkeypatch):
    from ace_platform.core import oauth_service as oauth_service_module

    db = _make_mock_db()
    service = oauth_service_module.OAuthService(db)

    no_oauth_result = MagicMock()
    no_oauth_result.scalar_one_or_none.return_value = None
    no_user_result = MagicMock()
    no_user_result.scalar_one_or_none.return_value = None
    db.execute.side_effect = [no_oauth_result, no_user_result]

    ensure_workspace = AsyncMock()
    monkeypatch.setattr(
        oauth_service_module, "ensure_personal_workspace_for_user", ensure_workspace
    )

    _, is_new = await service.get_or_create_user_from_oauth(
        provider=OAuthProvider.GOOGLE,
        provider_user_id="google-123",
        email="oauth@example.com",
        user_info={"sub": "google-123", "email": "oauth@example.com"},
        access_token="provider-access-token",
        refresh_token="provider-refresh-token",
    )

    added_models = [call.args[0] for call in db.add.call_args_list]
    oauth_account = next(model for model in added_models if isinstance(model, UserOAuthAccount))

    assert is_new is True
    assert oauth_account.access_token == "provider-access-token"
    assert oauth_account.refresh_token == "provider-refresh-token"
    assert oauth_account._access_token_ciphertext != "provider-access-token"
    assert oauth_account._refresh_token_ciphertext != "provider-refresh-token"
    assert is_encrypted_oauth_token(oauth_account._access_token_ciphertext) is True
    assert is_encrypted_oauth_token(oauth_account._refresh_token_ciphertext) is True


@pytest.mark.asyncio
async def test_oauth_service_updates_existing_account_with_encrypted_tokens():
    from ace_platform.core.oauth_service import OAuthService

    db = _make_mock_db()
    service = OAuthService(db)
    user = _make_user()
    oauth_account = _make_oauth_account()
    oauth_account.user = user

    existing_result = MagicMock()
    existing_result.scalar_one_or_none.return_value = oauth_account
    db.execute.return_value = existing_result

    returned_user, is_new = await service.get_or_create_user_from_oauth(
        provider=OAuthProvider.GITHUB,
        provider_user_id="github-123",
        email=user.email,
        user_info={"id": "github-123", "email": user.email},
        access_token="updated-provider-access",
        refresh_token="updated-provider-refresh",
    )

    assert returned_user == user
    assert is_new is False
    assert oauth_account.access_token == "updated-provider-access"
    assert oauth_account.refresh_token == "updated-provider-refresh"
    assert oauth_account._access_token_ciphertext != "updated-provider-access"
    assert oauth_account._refresh_token_ciphertext != "updated-provider-refresh"
    assert is_encrypted_oauth_token(oauth_account._access_token_ciphertext) is True
    assert is_encrypted_oauth_token(oauth_account._refresh_token_ciphertext) is True


@pytest.mark.asyncio
async def test_google_callback_redirects_with_fragment_tokens(monkeypatch):
    from ace_platform.api.routes import oauth as oauth_routes

    db = _make_mock_db()
    user = _make_user()
    request = SimpleNamespace(session={}, query_params={})
    oauth_service = MagicMock()
    oauth_service.get_or_create_user_from_oauth = AsyncMock(return_value=(user, True))

    provider = SimpleNamespace(
        provider=OAuthProvider.GOOGLE,
        display_name="Google",
        key="google",
        session_state_key="_state_google_",
        is_enabled=lambda: True,
        exchange_token=AsyncMock(
            return_value={
                "userinfo": {"sub": "google-123", "email": user.email},
                "access_token": "provider-access-token",
                "refresh_token": "provider-refresh-token",
            }
        ),
        resolve_identity=AsyncMock(
            return_value=OAuthIdentity(
                provider_user_id="google-123",
                email=user.email,
                user_info={"sub": "google-123", "email": user.email},
                access_token="provider-access-token",
                refresh_token="provider-refresh-token",
            )
        ),
    )
    monkeypatch.setattr(oauth_routes, "get_identity_provider", lambda _provider: provider)
    monkeypatch.setattr(oauth_routes, "OAuthService", lambda _db: oauth_service)
    monkeypatch.setattr(oauth_routes, "bootstrap_workspace_for_user", AsyncMock())
    monkeypatch.setattr(oauth_routes, "audit_oauth_login_success", AsyncMock())
    monkeypatch.setattr(oauth_routes, "audit_oauth_login_failure", AsyncMock())
    monkeypatch.setattr(oauth_routes, "create_access_token", lambda _user_id: "ace-access-token")
    monkeypatch.setattr(oauth_routes, "create_refresh_token", lambda _user_id: "ace-refresh-token")
    monkeypatch.setattr(oauth_routes.settings, "frontend_url", "https://app.aceagent.test")
    monkeypatch.setattr(oauth_routes.settings, "acquisition_tracking_enabled", False)

    response = await oauth_routes.google_callback(request, db, None)

    assert response.status_code == 302
    assert response.headers["location"] == (
        "https://app.aceagent.test/oauth/callback"
        "#access_token=ace-access-token&refresh_token=ace-refresh-token&is_new=true"
    )

    call_kwargs = oauth_service.get_or_create_user_from_oauth.call_args.kwargs
    assert call_kwargs["provider"] == OAuthProvider.GOOGLE
    assert call_kwargs["access_token"] == "provider-access-token"
    assert call_kwargs["refresh_token"] == "provider-refresh-token"
