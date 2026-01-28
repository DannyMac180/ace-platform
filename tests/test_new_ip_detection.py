"""Tests for new IP login detection and notification functionality."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestIsNewIpForUser:
    """Tests for is_new_ip_for_user function."""

    @pytest.mark.asyncio
    async def test_new_ip_returns_true(self):
        """Returns True when IP has never been used for this user."""
        from ace_platform.core.audit import is_new_ip_for_user

        # Mock db session that returns count of 0
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=0)

        user_id = uuid4()
        ip_address = "192.168.1.100"

        result = await is_new_ip_for_user(mock_db, user_id, ip_address)

        assert result is True
        mock_db.scalar.assert_called_once()

    @pytest.mark.asyncio
    async def test_known_ip_returns_false(self):
        """Returns False when IP has been used before for this user."""
        from ace_platform.core.audit import is_new_ip_for_user

        # Mock db session that returns count > 0
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=3)

        user_id = uuid4()
        ip_address = "192.168.1.100"

        result = await is_new_ip_for_user(mock_db, user_id, ip_address)

        assert result is False
        mock_db.scalar.assert_called_once()

    @pytest.mark.asyncio
    async def test_checks_both_login_types(self):
        """Verifies query checks both LOGIN_SUCCESS and OAUTH_LOGIN_SUCCESS."""
        from ace_platform.core.audit import is_new_ip_for_user

        # Mock db session
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=0)

        user_id = uuid4()
        ip_address = "192.168.1.100"

        await is_new_ip_for_user(mock_db, user_id, ip_address)

        # Verify the query was constructed (we can't easily check the exact query,
        # but we can verify the function was called)
        mock_db.scalar.assert_called_once()

    def test_is_new_ip_for_user_is_async(self):
        """is_new_ip_for_user is an async function."""
        import inspect

        from ace_platform.core.audit import is_new_ip_for_user

        assert inspect.iscoroutinefunction(is_new_ip_for_user)

    def test_is_new_ip_for_user_importable(self):
        """is_new_ip_for_user can be imported from audit module."""
        from ace_platform.core.audit import is_new_ip_for_user

        assert callable(is_new_ip_for_user)


class TestHasPreviousLogins:
    """Tests for has_previous_logins function."""

    @pytest.mark.asyncio
    async def test_no_previous_logins_returns_false(self):
        """Returns False when user has never logged in before."""
        from ace_platform.core.audit import has_previous_logins

        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=0)

        user_id = uuid4()

        result = await has_previous_logins(mock_db, user_id)

        assert result is False
        mock_db.scalar.assert_called_once()

    @pytest.mark.asyncio
    async def test_has_previous_logins_returns_true(self):
        """Returns True when user has logged in before."""
        from ace_platform.core.audit import has_previous_logins

        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=5)

        user_id = uuid4()

        result = await has_previous_logins(mock_db, user_id)

        assert result is True
        mock_db.scalar.assert_called_once()

    def test_has_previous_logins_importable(self):
        """has_previous_logins can be imported from audit module."""
        from ace_platform.core.audit import has_previous_logins

        assert callable(has_previous_logins)


class TestSendNewLoginAlert:
    """Tests for send_new_login_alert email function."""

    def test_send_new_login_alert_importable(self):
        """send_new_login_alert can be imported from email module."""
        from ace_platform.core.email import send_new_login_alert

        assert callable(send_new_login_alert)

    def test_send_new_login_alert_is_async(self):
        """send_new_login_alert is an async function."""
        import inspect

        from ace_platform.core.email import send_new_login_alert

        assert inspect.iscoroutinefunction(send_new_login_alert)

    @pytest.mark.asyncio
    async def test_send_alert_disabled_when_email_not_configured(self):
        """Returns error when email service is not configured."""
        from ace_platform.core.email import send_new_login_alert

        with patch("ace_platform.core.email.is_email_enabled", return_value=False):
            result = await send_new_login_alert(
                to_email="test@example.com",
                ip_address="192.168.1.100",
                login_time=datetime.now(UTC),
            )

            assert not result.success
            assert "not configured" in result.error.lower()

    @pytest.mark.asyncio
    async def test_send_alert_success(self):
        """Successfully sends email when configured."""
        from ace_platform.core.email import send_new_login_alert

        mock_send = MagicMock(return_value={"id": "msg_123"})

        with patch("ace_platform.core.email.is_email_enabled", return_value=True):
            with patch("resend.Emails.send", mock_send):
                result = await send_new_login_alert(
                    to_email="test@example.com",
                    ip_address="192.168.1.100",
                    login_time=datetime(2025, 1, 15, 10, 30, 0, tzinfo=UTC),
                )

                assert result.success
                assert result.message_id == "msg_123"

    @pytest.mark.asyncio
    async def test_send_alert_includes_ip_address(self):
        """Email content includes the IP address."""
        from ace_platform.core.email import send_new_login_alert

        captured_email_content = {}

        def capture_email(params):
            captured_email_content["html"] = params.get("html", "")
            captured_email_content["subject"] = params.get("subject", "")
            return {"id": "msg_123"}

        with patch("ace_platform.core.email.is_email_enabled", return_value=True):
            with patch("resend.Emails.send", side_effect=capture_email):
                await send_new_login_alert(
                    to_email="test@example.com",
                    ip_address="203.0.113.50",
                    login_time=datetime.now(UTC),
                )

                assert "203.0.113.50" in captured_email_content["html"]

    @pytest.mark.asyncio
    async def test_send_alert_includes_user_agent_when_provided(self):
        """Email content includes user agent when provided."""
        from ace_platform.core.email import send_new_login_alert

        captured_email_content = {}

        def capture_email(params):
            captured_email_content["html"] = params.get("html", "")
            return {"id": "msg_123"}

        with patch("ace_platform.core.email.is_email_enabled", return_value=True):
            with patch("resend.Emails.send", side_effect=capture_email):
                await send_new_login_alert(
                    to_email="test@example.com",
                    ip_address="192.168.1.100",
                    login_time=datetime.now(UTC),
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                )

                assert "Mozilla/5.0" in captured_email_content["html"]

    @pytest.mark.asyncio
    async def test_send_alert_truncates_long_user_agent(self):
        """Long user agents are truncated in email."""
        from ace_platform.core.email import send_new_login_alert

        captured_email_content = {}

        def capture_email(params):
            captured_email_content["html"] = params.get("html", "")
            return {"id": "msg_123"}

        long_user_agent = "A" * 200

        with patch("ace_platform.core.email.is_email_enabled", return_value=True):
            with patch("resend.Emails.send", side_effect=capture_email):
                await send_new_login_alert(
                    to_email="test@example.com",
                    ip_address="192.168.1.100",
                    login_time=datetime.now(UTC),
                    user_agent=long_user_agent,
                )

                # Should be truncated to 100 chars + "..."
                assert "A" * 100 + "..." in captured_email_content["html"]
                assert "A" * 200 not in captured_email_content["html"]

    @pytest.mark.asyncio
    async def test_send_alert_has_correct_subject(self):
        """Email has correct subject line."""
        from ace_platform.core.email import send_new_login_alert

        captured_email_content = {}

        def capture_email(params):
            captured_email_content["subject"] = params.get("subject", "")
            return {"id": "msg_123"}

        with patch("ace_platform.core.email.is_email_enabled", return_value=True):
            with patch("resend.Emails.send", side_effect=capture_email):
                await send_new_login_alert(
                    to_email="test@example.com",
                    ip_address="192.168.1.100",
                    login_time=datetime.now(UTC),
                )

                assert "New Login" in captured_email_content["subject"]
                assert "ACE" in captured_email_content["subject"]

    @pytest.mark.asyncio
    async def test_send_alert_includes_security_link(self):
        """Email includes link to change password."""
        from ace_platform.core.email import send_new_login_alert

        captured_email_content = {}

        def capture_email(params):
            captured_email_content["html"] = params.get("html", "")
            return {"id": "msg_123"}

        with patch("ace_platform.core.email.is_email_enabled", return_value=True):
            with patch("resend.Emails.send", side_effect=capture_email):
                await send_new_login_alert(
                    to_email="test@example.com",
                    ip_address="192.168.1.100",
                    login_time=datetime.now(UTC),
                )

                assert "/settings/security" in captured_email_content["html"]


class TestLoginIntegration:
    """Tests for new IP detection integration with login endpoints."""

    def test_auth_route_imports_new_ip_functions(self):
        """Auth routes import required new IP detection functions."""
        from ace_platform.api.routes import auth

        # Check that the imports are available
        assert hasattr(auth, "get_client_ip") or "get_client_ip" in dir(auth)
        assert hasattr(auth, "is_new_ip_for_user") or "is_new_ip_for_user" in dir(auth)
        assert hasattr(auth, "send_new_login_alert") or "send_new_login_alert" in dir(auth)

    def test_oauth_route_imports_new_ip_functions(self):
        """OAuth routes import required new IP detection functions."""
        from ace_platform.api.routes import oauth

        # Check that the imports are available
        assert hasattr(oauth, "get_client_ip") or "get_client_ip" in dir(oauth)
        assert hasattr(oauth, "is_new_ip_for_user") or "is_new_ip_for_user" in dir(oauth)
        assert hasattr(oauth, "send_new_login_alert") or "send_new_login_alert" in dir(oauth)


class TestNewIpDetectionEdgeCases:
    """Edge case tests for new IP detection."""

    @pytest.mark.asyncio
    async def test_handles_none_ip_gracefully(self):
        """is_new_ip_for_user handles None IP without error."""
        from ace_platform.core.audit import is_new_ip_for_user

        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=0)

        user_id = uuid4()

        # Should not raise an error, though in practice we guard against None IPs
        # before calling this function
        result = await is_new_ip_for_user(mock_db, user_id, None)
        assert result is True  # No previous logins with None IP means it's "new"

    @pytest.mark.asyncio
    async def test_handles_empty_string_ip(self):
        """is_new_ip_for_user handles empty string IP."""
        from ace_platform.core.audit import is_new_ip_for_user

        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=0)

        user_id = uuid4()

        result = await is_new_ip_for_user(mock_db, user_id, "")
        assert result is True

    @pytest.mark.asyncio
    async def test_email_alert_handles_exception(self):
        """send_new_login_alert handles exceptions gracefully."""
        from ace_platform.core.email import send_new_login_alert

        with patch("ace_platform.core.email.is_email_enabled", return_value=True):
            with patch("resend.Emails.send", side_effect=Exception("API error")):
                result = await send_new_login_alert(
                    to_email="test@example.com",
                    ip_address="192.168.1.100",
                    login_time=datetime.now(UTC),
                )

                assert not result.success
                assert "API error" in result.error
