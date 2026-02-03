"""Unit tests for logged-in password management endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException, Request

from ace_platform.api.routes.auth import (
    ChangePasswordRequest,
    SetPasswordRequest,
    change_password,
    set_password,
)
from ace_platform.core.security import hash_password, verify_password


@pytest.mark.asyncio
async def test_set_password_sets_hash_for_oauth_only_user():
    user = MagicMock()
    user.id = uuid4()
    user.hashed_password = None

    db = AsyncMock()
    db.commit = AsyncMock()

    with patch("ace_platform.api.routes.auth.audit_password_change", new=AsyncMock()):
        resp = await set_password(
            SetPasswordRequest(new_password="newpassword123"),
            MagicMock(spec=Request),
            user,
            db,
        )

    assert resp.message == "Password set"
    assert user.hashed_password is not None
    assert verify_password("newpassword123", user.hashed_password)


@pytest.mark.asyncio
async def test_set_password_rejects_if_already_set():
    user = MagicMock()
    user.id = uuid4()
    user.hashed_password = hash_password("existingpassword123")

    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await set_password(
            SetPasswordRequest(new_password="newpassword123"),
            MagicMock(spec=Request),
            user,
            db,
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_change_password_updates_hash_when_current_matches():
    user = MagicMock()
    user.id = uuid4()
    user.hashed_password = hash_password("oldpassword123")

    db = AsyncMock()
    db.commit = AsyncMock()

    with patch("ace_platform.api.routes.auth.audit_password_change", new=AsyncMock()):
        resp = await change_password(
            ChangePasswordRequest(
                current_password="oldpassword123",
                new_password="newpassword123",
            ),
            MagicMock(spec=Request),
            user,
            db,
        )

    assert resp.message == "Password changed"
    assert verify_password("newpassword123", user.hashed_password)


@pytest.mark.asyncio
async def test_change_password_rejects_when_no_password_set():
    user = MagicMock()
    user.id = uuid4()
    user.hashed_password = None

    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await change_password(
            ChangePasswordRequest(current_password="x", new_password="newpassword123"),
            MagicMock(spec=Request),
            user,
            db,
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_change_password_rejects_when_current_incorrect():
    user = MagicMock()
    user.id = uuid4()
    user.hashed_password = hash_password("oldpassword123")

    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await change_password(
            ChangePasswordRequest(
                current_password="wrongpassword",
                new_password="newpassword123",
            ),
            MagicMock(spec=Request),
            user,
            db,
        )

    assert exc_info.value.status_code == 400
