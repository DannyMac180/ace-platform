"""Email service for sending transactional emails via Resend.

This module provides email sending capabilities for:
- Email verification
- Password reset
- Notifications (future)
"""

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from jose import JWTError, jwt

from ace_platform.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Token type constants
TOKEN_TYPE_EMAIL_VERIFICATION = "email_verification"


@dataclass
class EmailResult:
    """Result of an email send operation."""

    success: bool
    message_id: str | None = None
    error: str | None = None


def is_email_enabled() -> bool:
    """Check if email sending is enabled (Resend API key configured)."""
    return bool(settings.resend_api_key)


def create_email_verification_token(user_id: UUID, email: str) -> str:
    """Create a JWT token for email verification.

    Args:
        user_id: The user's ID.
        email: The email being verified (included to prevent token reuse after email change).

    Returns:
        JWT token string.
    """
    expire = datetime.now(UTC) + timedelta(hours=settings.email_verification_token_expire_hours)
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": TOKEN_TYPE_EMAIL_VERIFICATION,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_email_verification_token(token: str) -> tuple[UUID, str] | None:
    """Decode and validate an email verification token.

    Args:
        token: The JWT token to decode.

    Returns:
        Tuple of (user_id, email) if valid, None if invalid/expired.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )

        # Verify token type
        if payload.get("type") != TOKEN_TYPE_EMAIL_VERIFICATION:
            return None

        user_id = UUID(payload["sub"])
        email = payload["email"]
        return user_id, email

    except (JWTError, KeyError, ValueError):
        return None


async def send_verification_email(email: str, verification_url: str) -> EmailResult:
    """Send email verification email.

    Args:
        email: Recipient email address.
        verification_url: Full URL for email verification.

    Returns:
        EmailResult with success status.
    """
    if not is_email_enabled():
        logger.warning("Email not configured, skipping verification email")
        return EmailResult(success=False, error="Email service not configured")

    try:
        import resend

        resend.api_key = settings.resend_api_key

        result = resend.Emails.send(
            {
                "from": f"{settings.email_from_name} <{settings.email_from_address}>",
                "to": [email],
                "subject": "Verify your email address",
                "html": f"""
                <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h1 style="color: #1a1a1a; font-size: 24px; margin-bottom: 20px;">Verify your email</h1>
                    <p style="color: #4a4a4a; font-size: 16px; line-height: 1.5;">
                        Welcome to ACE Platform! Please verify your email address to get started.
                    </p>
                    <a href="{verification_url}"
                       style="display: inline-block; background-color: #2563eb; color: white; padding: 12px 24px;
                              text-decoration: none; border-radius: 6px; margin: 20px 0; font-weight: 500;">
                        Verify Email
                    </a>
                    <p style="color: #6b7280; font-size: 14px; margin-top: 20px;">
                        Or copy and paste this link into your browser:<br>
                        <a href="{verification_url}" style="color: #2563eb; word-break: break-all;">{verification_url}</a>
                    </p>
                    <p style="color: #9ca3af; font-size: 12px; margin-top: 30px;">
                        This link expires in {settings.email_verification_token_expire_hours} hours.
                        If you didn't create an account, you can ignore this email.
                    </p>
                </div>
                """,
            }
        )

        logger.info(f"Verification email sent to {email}", extra={"message_id": result.get("id")})
        return EmailResult(success=True, message_id=result.get("id"))

    except Exception as e:
        logger.error(f"Failed to send verification email to {email}", exc_info=True)
        return EmailResult(success=False, error=str(e))


async def send_welcome_email(email: str, name: str | None = None) -> EmailResult:
    """Send welcome email after verification.

    Args:
        email: Recipient email address.
        name: Optional user name.

    Returns:
        EmailResult with success status.
    """
    if not is_email_enabled():
        return EmailResult(success=False, error="Email service not configured")

    try:
        import resend

        resend.api_key = settings.resend_api_key

        greeting = f"Hi {name}," if name else "Hi there,"

        result = resend.Emails.send(
            {
                "from": f"{settings.email_from_name} <{settings.email_from_address}>",
                "to": [email],
                "subject": "Welcome to ACE Platform!",
                "html": f"""
                <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h1 style="color: #1a1a1a; font-size: 24px; margin-bottom: 20px;">Welcome to ACE Platform!</h1>
                    <p style="color: #4a4a4a; font-size: 16px; line-height: 1.5;">
                        {greeting}
                    </p>
                    <p style="color: #4a4a4a; font-size: 16px; line-height: 1.5;">
                        Your email is now verified and you're ready to start building self-improving playbooks.
                    </p>
                    <h2 style="color: #1a1a1a; font-size: 18px; margin-top: 24px;">Quick Start</h2>
                    <ol style="color: #4a4a4a; font-size: 16px; line-height: 1.8;">
                        <li>Create your first playbook in the dashboard</li>
                        <li>Generate an API key for Claude Code integration</li>
                        <li>Start recording outcomes as you work</li>
                        <li>Watch your playbook evolve and improve</li>
                    </ol>
                    <p style="color: #9ca3af; font-size: 12px; margin-top: 30px;">
                        Need help? Reply to this email or visit our documentation.
                    </p>
                </div>
                """,
            }
        )

        logger.info(f"Welcome email sent to {email}", extra={"message_id": result.get("id")})
        return EmailResult(success=True, message_id=result.get("id"))

    except Exception as e:
        logger.error(f"Failed to send welcome email to {email}", exc_info=True)
        return EmailResult(success=False, error=str(e))


# =============================================================================
# Password Reset
# =============================================================================

# Token expiry time (1 hour)
PASSWORD_RESET_TOKEN_EXPIRE_HOURS = 1


def generate_password_reset_token() -> str:
    """Generate a secure random password reset token.

    Returns:
        A 32-byte URL-safe random token string.
    """
    return secrets.token_urlsafe(32)


def hash_password_reset_token(token: str) -> str:
    """Hash a password reset token for secure storage.

    Uses SHA-256 for fast, secure hashing (bcrypt is overkill for random tokens).

    Args:
        token: The plaintext token to hash.

    Returns:
        The SHA-256 hash of the token.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def verify_password_reset_token(token: str, token_hash: str) -> bool:
    """Verify a password reset token against its hash.

    Uses timing-safe comparison to prevent timing attacks.

    Args:
        token: The plaintext token to verify.
        token_hash: The stored hash to compare against.

    Returns:
        True if the token matches the hash.
    """
    return secrets.compare_digest(hash_password_reset_token(token), token_hash)


async def send_password_reset_email(email: str, reset_url: str) -> EmailResult:
    """Send password reset email.

    Args:
        email: Recipient email address.
        reset_url: Full URL for password reset.

    Returns:
        EmailResult with success status.
    """
    if not is_email_enabled():
        logger.warning("Email not configured, skipping password reset email")
        return EmailResult(success=False, error="Email service not configured")

    try:
        import resend

        resend.api_key = settings.resend_api_key

        result = resend.Emails.send(
            {
                "from": f"{settings.email_from_name} <{settings.email_from_address}>",
                "to": [email],
                "subject": "Reset your password",
                "html": f"""
                <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h1 style="color: #1a1a1a; font-size: 24px; margin-bottom: 20px;">Reset your password</h1>
                    <p style="color: #4a4a4a; font-size: 16px; line-height: 1.5;">
                        We received a request to reset your password. Click the button below to choose a new password.
                    </p>
                    <a href="{reset_url}"
                       style="display: inline-block; background-color: #2563eb; color: white; padding: 12px 24px;
                              text-decoration: none; border-radius: 6px; margin: 20px 0; font-weight: 500;">
                        Reset Password
                    </a>
                    <p style="color: #6b7280; font-size: 14px; margin-top: 20px;">
                        Or copy and paste this link into your browser:<br>
                        <a href="{reset_url}" style="color: #2563eb; word-break: break-all;">{reset_url}</a>
                    </p>
                    <p style="color: #9ca3af; font-size: 12px; margin-top: 30px;">
                        This link expires in {PASSWORD_RESET_TOKEN_EXPIRE_HOURS} hour.
                        If you didn't request a password reset, you can safely ignore this email.
                    </p>
                </div>
                """,
            }
        )

        logger.info(f"Password reset email sent to {email}", extra={"message_id": result.get("id")})
        return EmailResult(success=True, message_id=result.get("id"))

    except Exception as e:
        logger.error(f"Failed to send password reset email to {email}", exc_info=True)
        return EmailResult(success=False, error=str(e))
