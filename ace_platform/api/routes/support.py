"""Support contact form route."""

import html
import logging

import resend
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ace_platform.api.auth import RequiredUser
from ace_platform.config import get_settings
from ace_platform.core.email import is_email_enabled
from ace_platform.core.rate_limit import rate_limit_contact_form

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/support", tags=["support"])


class ContactRequest(BaseModel):
    """Support contact form request."""

    subject: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=10, max_length=5000)


class ContactResponse(BaseModel):
    """Support contact form response."""

    message: str


@router.post("/contact", response_model=ContactResponse)
async def submit_contact_form(
    body: ContactRequest,
    request: Request,
    current_user: RequiredUser,
) -> ContactResponse:
    """Submit a support contact form.

    Sends an email to the configured support address with the user's message.
    Rate limited to 3 requests per hour per user.
    """
    settings = get_settings()

    # Determine support email destination
    support_email = settings.support_email or settings.admin_alert_email
    if not support_email:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Support email is not configured",
        )

    # Rate limit by user ID
    await rate_limit_contact_form(request, str(current_user.id))

    # Send email via Resend
    if not is_email_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Email service is not configured",
        )

    # HTML-escape user input to prevent XSS in email
    safe_subject = html.escape(body.subject)
    safe_message = html.escape(body.message)
    safe_email = html.escape(current_user.email)

    try:
        resend.api_key = settings.resend_api_key

        result = resend.Emails.send(
            {
                "from": f"{settings.email_from_name} <{settings.email_from_address}>",
                "to": [support_email],
                "reply_to": current_user.email,
                "subject": f"[Support] {safe_subject}",
                "html": f"""
                <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #1a1a1a; font-size: 20px; margin-bottom: 16px;">Support Request</h2>
                    <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                        <tr>
                            <td style="padding: 8px 12px; color: #6b7280; font-size: 14px; border-bottom: 1px solid #e5e7eb;">From</td>
                            <td style="padding: 8px 12px; color: #1a1a1a; font-size: 14px; border-bottom: 1px solid #e5e7eb;">{safe_email}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 12px; color: #6b7280; font-size: 14px; border-bottom: 1px solid #e5e7eb;">Subject</td>
                            <td style="padding: 8px 12px; color: #1a1a1a; font-size: 14px; border-bottom: 1px solid #e5e7eb;">{safe_subject}</td>
                        </tr>
                    </table>
                    <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; white-space: pre-wrap; font-size: 14px; color: #1a1a1a; line-height: 1.6;">{safe_message}</div>
                    <p style="color: #9ca3af; font-size: 12px; margin-top: 20px;">
                        Reply directly to this email to respond to the user.
                    </p>
                </div>
                """,
            }
        )

        logger.info(
            f"Support contact email sent from {current_user.email}",
            extra={"message_id": result.get("id"), "user_id": str(current_user.id)},
        )
        return ContactResponse(message="Your message has been sent. We'll get back to you soon.")

    except Exception:
        logger.error(
            f"Failed to send support contact email from {current_user.email}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to send message. Please try again later.",
        )
