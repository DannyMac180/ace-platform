"""Unit tests for transient API-key auth database failures."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import DBAPIError

from ace_platform.core import api_keys as api_key_service
from ace_platform.core.api_keys import API_KEY_PREFIX, authenticate_api_key_async, hash_api_key
from ace_platform.db.models import ApiKey, User


class _ScalarResult:
    def __init__(self, item):
        self._item = item

    def scalar_one_or_none(self):
        return self._item


class _AsyncSessionContextManager:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


def _build_user() -> User:
    return User(
        id=uuid4(),
        email="test@example.com",
        hashed_password="hashed",
        is_active=True,
    )


def _build_api_key(user_id) -> tuple[str, ApiKey]:
    full_key = f"{API_KEY_PREFIX}1234567890abcdefghijklmnopqrstuv"
    return full_key, ApiKey(
        id=uuid4(),
        user_id=user_id,
        name="Test Key",
        key_prefix=full_key[:8],
        hashed_key=hash_api_key(full_key),
        scopes=["outcomes:write"],
        last_used_at=None,
        revoked_at=None,
    )


class TestAuthenticateApiKeyResilience:
    async def test_recovers_from_disconnect_during_last_used_flush(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """A dropped connection on last_used_at update should not fail auth."""
        user = _build_user()
        full_key, initial_key = _build_api_key(user.id)
        _, refreshed_key = _build_api_key(user.id)
        recovery_db = MagicMock()
        recovery_db.execute = AsyncMock(return_value=_ScalarResult(refreshed_key))
        recovery_db.get = AsyncMock(return_value=user)

        db = MagicMock()
        db.execute = AsyncMock(return_value=_ScalarResult(initial_key))
        db.flush = AsyncMock(
            side_effect=DBAPIError(
                statement="UPDATE api_keys SET last_used_at = :last_used_at",
                params={},
                orig=Exception("connection was closed in the middle of operation"),
                connection_invalidated=True,
            )
        )
        db.rollback = AsyncMock()
        db.get = AsyncMock()
        db.expunge_all = MagicMock()
        monkeypatch.setattr(
            api_key_service,
            "AsyncSessionLocal",
            lambda: _AsyncSessionContextManager(recovery_db),
        )

        authenticated_key, authenticated_user = await authenticate_api_key_async(db, full_key)

        assert authenticated_key is refreshed_key
        assert authenticated_user is user
        assert db.execute.await_count == 1
        db.rollback.assert_awaited_once()
        db.get.assert_not_awaited()
        db.expunge_all.assert_called_once_with()
        recovery_db.execute.assert_awaited_once()
        recovery_db.get.assert_awaited_once_with(User, refreshed_key.user_id)

    async def test_revalidates_key_after_disconnect_rollback(self, monkeypatch: pytest.MonkeyPatch):
        """A key revoked before the recovery query should no longer authenticate."""
        user = _build_user()
        full_key, initial_key = _build_api_key(user.id)
        recovery_db = MagicMock()
        recovery_db.execute = AsyncMock(return_value=_ScalarResult(None))
        recovery_db.get = AsyncMock()

        db = MagicMock()
        db.execute = AsyncMock(return_value=_ScalarResult(initial_key))
        db.flush = AsyncMock(
            side_effect=DBAPIError(
                statement="UPDATE api_keys SET last_used_at = :last_used_at",
                params={},
                orig=Exception("connection was closed in the middle of operation"),
                connection_invalidated=True,
            )
        )
        db.rollback = AsyncMock()
        db.get = AsyncMock(return_value=user)
        db.expunge_all = MagicMock()
        monkeypatch.setattr(
            api_key_service,
            "AsyncSessionLocal",
            lambda: _AsyncSessionContextManager(recovery_db),
        )

        auth_result = await authenticate_api_key_async(db, full_key)

        assert auth_result is None
        assert db.execute.await_count == 1
        db.rollback.assert_awaited_once()
        db.get.assert_not_awaited()
        db.expunge_all.assert_called_once_with()
        recovery_db.execute.assert_awaited_once()
        recovery_db.get.assert_not_awaited()

    async def test_reraises_non_disconnect_db_errors(self):
        """Unexpected DB failures during flush should still propagate."""
        user = _build_user()
        full_key, key = _build_api_key(user.id)

        db = MagicMock()
        db.execute = AsyncMock(return_value=_ScalarResult(key))
        db.flush = AsyncMock(
            side_effect=DBAPIError(
                statement="UPDATE api_keys SET last_used_at = :last_used_at",
                params={},
                orig=Exception("duplicate key value violates unique constraint"),
            )
        )
        db.rollback = AsyncMock()
        db.get = AsyncMock(return_value=user)

        with pytest.raises(DBAPIError, match="duplicate key value"):
            await authenticate_api_key_async(db, full_key)

        db.rollback.assert_not_awaited()
