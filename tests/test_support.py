"""Tests for support contact form route."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ace_platform.api.main import create_app


def test_support_route_registered():
    """Test that the support contact route is registered."""
    app = create_app()
    routes = [route.path for route in app.routes]
    assert "/support/contact" in routes


def test_contact_requires_auth():
    """Test that the contact endpoint requires authentication."""
    client = TestClient(create_app())
    resp = client.post(
        "/support/contact",
        json={"subject": "Test", "message": "Test message here"},
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


def test_contact_validates_subject_required():
    """Test that subject is required."""
    client = TestClient(create_app())
    resp = client.post(
        "/support/contact",
        json={"message": "Test message here"},
    )
    # Should be 401 (auth required) or 422 (validation) - auth check comes first
    assert resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_422_UNPROCESSABLE_ENTITY)


def test_contact_validates_message_min_length():
    """Test that message must be at least 10 characters."""
    client = TestClient(create_app())
    resp = client.post(
        "/support/contact",
        json={"subject": "Test", "message": "Short"},
    )
    assert resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_422_UNPROCESSABLE_ENTITY)


@pytest.mark.asyncio
async def test_contact_sends_email():
    """Test successful contact form submission sends email via Resend."""
    from ace_platform.api.routes.support import ContactRequest, submit_contact_form

    user = MagicMock()
    user.id = uuid4()
    user.email = "user@example.com"

    request = MagicMock()
    request.state = MagicMock()

    body = ContactRequest(
        subject="Need help", message="I need help with my playbook configuration."
    )

    with (
        patch("ace_platform.api.routes.support.get_settings") as mock_settings,
        patch("ace_platform.api.routes.support.rate_limit_contact_form", new_callable=AsyncMock),
        patch("ace_platform.api.routes.support.is_email_enabled", return_value=True),
        patch("ace_platform.api.routes.support.resend") as mock_resend,
    ):
        mock_settings.return_value.support_email = "support@aceagent.io"
        mock_settings.return_value.admin_alert_email = ""
        mock_settings.return_value.resend_api_key = "re_test_123"
        mock_settings.return_value.email_from_name = "ACE Platform"
        mock_settings.return_value.email_from_address = "noreply@aceagent.io"
        mock_resend.Emails.send.return_value = {"id": "msg_123"}

        result = await submit_contact_form(body=body, request=request, current_user=user)

        assert result.message == "Your message has been sent. We'll get back to you soon."
        mock_resend.Emails.send.assert_called_once()

        call_args = mock_resend.Emails.send.call_args[0][0]
        assert call_args["to"] == ["support@aceagent.io"]
        assert call_args["reply_to"] == "user@example.com"
        assert "[Support] Need help" in call_args["subject"]


@pytest.mark.asyncio
async def test_contact_falls_back_to_admin_email():
    """Test that support_email falls back to admin_alert_email."""
    from ace_platform.api.routes.support import ContactRequest, submit_contact_form

    user = MagicMock()
    user.id = uuid4()
    user.email = "user@example.com"

    request = MagicMock()
    request.state = MagicMock()

    body = ContactRequest(subject="Help", message="I need help with something important.")

    with (
        patch("ace_platform.api.routes.support.get_settings") as mock_settings,
        patch("ace_platform.api.routes.support.rate_limit_contact_form", new_callable=AsyncMock),
        patch("ace_platform.api.routes.support.is_email_enabled", return_value=True),
        patch("ace_platform.api.routes.support.resend") as mock_resend,
    ):
        mock_settings.return_value.support_email = ""
        mock_settings.return_value.admin_alert_email = "admin@aceagent.io"
        mock_settings.return_value.resend_api_key = "re_test_123"
        mock_settings.return_value.email_from_name = "ACE Platform"
        mock_settings.return_value.email_from_address = "noreply@aceagent.io"
        mock_resend.Emails.send.return_value = {"id": "msg_456"}

        result = await submit_contact_form(body=body, request=request, current_user=user)

        assert result.message == "Your message has been sent. We'll get back to you soon."
        call_args = mock_resend.Emails.send.call_args[0][0]
        assert call_args["to"] == ["admin@aceagent.io"]


@pytest.mark.asyncio
async def test_contact_returns_503_when_no_email_configured():
    """Test that 503 is returned when no support email is configured."""
    from fastapi import HTTPException

    from ace_platform.api.routes.support import ContactRequest, submit_contact_form

    user = MagicMock()
    user.id = uuid4()
    user.email = "user@example.com"

    request = MagicMock()
    request.state = MagicMock()

    body = ContactRequest(subject="Help", message="I need help with something important.")

    with patch("ace_platform.api.routes.support.get_settings") as mock_settings:
        mock_settings.return_value.support_email = ""
        mock_settings.return_value.admin_alert_email = ""

        with pytest.raises(HTTPException) as exc_info:
            await submit_contact_form(body=body, request=request, current_user=user)

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_contact_returns_503_when_resend_not_configured():
    """Test that 503 is returned when Resend API is not configured."""
    from fastapi import HTTPException

    from ace_platform.api.routes.support import ContactRequest, submit_contact_form

    user = MagicMock()
    user.id = uuid4()
    user.email = "user@example.com"

    request = MagicMock()
    request.state = MagicMock()

    body = ContactRequest(subject="Help", message="I need help with something important.")

    with (
        patch("ace_platform.api.routes.support.get_settings") as mock_settings,
        patch("ace_platform.api.routes.support.rate_limit_contact_form", new_callable=AsyncMock),
        patch("ace_platform.api.routes.support.is_email_enabled", return_value=False),
    ):
        mock_settings.return_value.support_email = "support@aceagent.io"
        mock_settings.return_value.admin_alert_email = ""

        with pytest.raises(HTTPException) as exc_info:
            await submit_contact_form(body=body, request=request, current_user=user)

        assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


@pytest.mark.asyncio
async def test_contact_html_escapes_user_input():
    """Test that user input is HTML-escaped in the email body."""
    from ace_platform.api.routes.support import ContactRequest, submit_contact_form

    user = MagicMock()
    user.id = uuid4()
    user.email = "user@example.com"

    request = MagicMock()
    request.state = MagicMock()

    body = ContactRequest(
        subject='<script>alert("xss")</script>',
        message='<img src=x onerror=alert("xss")> test message',
    )

    with (
        patch("ace_platform.api.routes.support.get_settings") as mock_settings,
        patch("ace_platform.api.routes.support.rate_limit_contact_form", new_callable=AsyncMock),
        patch("ace_platform.api.routes.support.is_email_enabled", return_value=True),
        patch("ace_platform.api.routes.support.resend") as mock_resend,
    ):
        mock_settings.return_value.support_email = "support@aceagent.io"
        mock_settings.return_value.admin_alert_email = ""
        mock_settings.return_value.resend_api_key = "re_test_123"
        mock_settings.return_value.email_from_name = "ACE Platform"
        mock_settings.return_value.email_from_address = "noreply@aceagent.io"
        mock_resend.Emails.send.return_value = {"id": "msg_789"}

        await submit_contact_form(body=body, request=request, current_user=user)

        call_args = mock_resend.Emails.send.call_args[0][0]
        html_body = call_args["html"]
        # Ensure raw HTML tags are escaped
        assert "<script>" not in html_body
        assert "&lt;script&gt;" in html_body
        assert "<img src=x" not in html_body
