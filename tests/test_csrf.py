"""Tests for CSRF protection functionality."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from ace_platform.api.middleware import (
    CSRF_TOKEN_HEADER,
    CSRF_TOKEN_LENGTH,
    CSRF_TOKEN_SESSION_KEY,
    ensure_csrf_token,
    generate_csrf_token,
    get_csrf_token_from_session,
    validate_csrf_token,
)


class TestGenerateCSRFToken:
    """Tests for CSRF token generation."""

    def test_generates_url_safe_token(self):
        """Token should be URL-safe."""
        token = generate_csrf_token()
        # URL-safe base64 uses alphanumeric, dash, and underscore
        assert all(c.isalnum() or c in "-_" for c in token)

    def test_generates_token_of_correct_length(self):
        """Token should have sufficient length for security."""
        token = generate_csrf_token()
        # URL-safe base64 encoding of N bytes produces ~4/3 * N characters
        # 32 bytes -> approximately 43 characters
        assert len(token) >= 40

    def test_generates_unique_tokens(self):
        """Each generated token should be unique."""
        tokens = {generate_csrf_token() for _ in range(100)}
        assert len(tokens) == 100


class TestGetCSRFTokenFromSession:
    """Tests for retrieving CSRF token from session."""

    def test_returns_none_when_no_session(self):
        """Should return None if request has no session."""
        request = MagicMock(spec=[])  # No 'session' attribute
        assert get_csrf_token_from_session(request) is None

    def test_returns_none_when_token_not_in_session(self):
        """Should return None if token not in session."""
        request = MagicMock()
        request.session = {}
        assert get_csrf_token_from_session(request) is None

    def test_returns_token_when_present(self):
        """Should return token when present in session."""
        token = "test-token-123"
        request = MagicMock()
        request.session = {CSRF_TOKEN_SESSION_KEY: token}
        assert get_csrf_token_from_session(request) == token


class TestEnsureCSRFToken:
    """Tests for ensuring CSRF token exists in session."""

    def test_creates_token_when_missing(self):
        """Should create new token if none exists."""
        request = MagicMock()
        request.session = {}

        token = ensure_csrf_token(request)

        assert token is not None
        assert len(token) >= 40
        assert request.session[CSRF_TOKEN_SESSION_KEY] == token

    def test_returns_existing_token(self):
        """Should return existing token without creating new one."""
        existing_token = "existing-token-abc"
        request = MagicMock()
        request.session = {CSRF_TOKEN_SESSION_KEY: existing_token}

        token = ensure_csrf_token(request)

        assert token == existing_token


class TestValidateCSRFToken:
    """Tests for CSRF token validation."""

    @pytest.mark.asyncio
    async def test_raises_when_no_session_token(self):
        """Should raise 403 if no token in session."""
        request = MagicMock()
        request.session = {}
        request.headers = {CSRF_TOKEN_HEADER: "some-token"}

        with pytest.raises(HTTPException) as exc_info:
            await validate_csrf_token(request)

        assert exc_info.value.status_code == 403
        assert "missing from session" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_raises_when_no_header_token(self):
        """Should raise 403 if no token in header."""
        request = MagicMock()
        request.session = {CSRF_TOKEN_SESSION_KEY: "session-token"}
        request.headers = {}

        with pytest.raises(HTTPException) as exc_info:
            await validate_csrf_token(request)

        assert exc_info.value.status_code == 403
        assert "missing from request" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_raises_when_tokens_dont_match(self):
        """Should raise 403 if tokens don't match."""
        request = MagicMock()
        request.session = {CSRF_TOKEN_SESSION_KEY: "token-A"}
        request.headers = {CSRF_TOKEN_HEADER: "token-B"}

        with pytest.raises(HTTPException) as exc_info:
            await validate_csrf_token(request)

        assert exc_info.value.status_code == 403
        assert "validation failed" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_passes_when_tokens_match(self):
        """Should pass validation when tokens match."""
        token = generate_csrf_token()
        request = MagicMock()
        request.session = {CSRF_TOKEN_SESSION_KEY: token}
        request.headers = {CSRF_TOKEN_HEADER: token}

        # Should not raise
        await validate_csrf_token(request)

    @pytest.mark.asyncio
    async def test_uses_constant_time_comparison(self):
        """Should use constant-time comparison to prevent timing attacks."""
        # This test verifies that secrets.compare_digest is used
        with patch("ace_platform.api.middleware.secrets.compare_digest") as mock_compare:
            mock_compare.return_value = True

            token = "test-token"
            request = MagicMock()
            request.session = {CSRF_TOKEN_SESSION_KEY: token}
            request.headers = {CSRF_TOKEN_HEADER: token}

            await validate_csrf_token(request)

            mock_compare.assert_called_once_with(token, token)


class TestCSRFTokenConstants:
    """Tests for CSRF token configuration constants."""

    def test_token_length_is_secure(self):
        """Token length should be at least 32 bytes for security."""
        assert CSRF_TOKEN_LENGTH >= 32

    def test_header_name_follows_convention(self):
        """CSRF header should follow X-CSRF-Token convention."""
        assert CSRF_TOKEN_HEADER == "X-CSRF-Token"

    def test_session_key_is_prefixed(self):
        """Session key should be prefixed to avoid collisions."""
        assert CSRF_TOKEN_SESSION_KEY.startswith("_")
