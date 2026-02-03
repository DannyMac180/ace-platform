"""Audit logging service for security events.

This module provides functions to log security-relevant events to the audit_logs table.
All security-sensitive operations should call the appropriate audit function.

Usage:
    from ace_platform.core.audit import audit_login_success, audit_login_failure

    # On successful login
    await audit_login_success(db, user.id, request)

    # On failed login
    await audit_login_failure(db, email, request, reason="Invalid password")
"""

import logging
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.db.models import AuditEventType, AuditLog, AuditSeverity

logger = logging.getLogger(__name__)


def get_client_ip(request: Request) -> str | None:
    """Extract client IP address from request.

    Checks X-Forwarded-For header for proxied requests, falls back to direct client.
    """
    # Check for forwarded header (from reverse proxy/load balancer)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs; first is original client
        return forwarded_for.split(",")[0].strip()

    # Check X-Real-IP header (common in nginx)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip

    # Fall back to direct client
    if request.client:
        return request.client.host

    return None


def get_user_agent(request: Request) -> str | None:
    """Extract user agent from request headers."""
    user_agent = request.headers.get("User-Agent")
    if user_agent:
        # Truncate to max field length
        return user_agent[:512]
    return None


async def log_audit_event(
    db: AsyncSession,
    event_type: AuditEventType,
    *,
    user_id: UUID | None = None,
    severity: AuditSeverity = AuditSeverity.INFO,
    ip_address: str | None = None,
    user_agent: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Log a security audit event.

    This is the core function for audit logging. Prefer using the specific
    helper functions (audit_login_success, etc.) for common events.

    Args:
        db: Database session.
        event_type: Type of security event.
        user_id: ID of the user involved (None for anonymous events).
        severity: Event severity level.
        ip_address: Client IP address.
        user_agent: Client user agent string.
        details: Additional event-specific details as JSON.

    Returns:
        The created AuditLog record.
    """
    audit_log = AuditLog(
        user_id=user_id,
        event_type=event_type,
        severity=severity,
        ip_address=ip_address,
        user_agent=user_agent,
        details=details,
    )
    db.add(audit_log)
    await db.flush()

    # Also log to application logger for monitoring
    log_msg = f"AUDIT: {event_type.value}"
    if user_id:
        log_msg += f" user={user_id}"
    if details:
        log_msg += f" details={details}"

    if severity == AuditSeverity.CRITICAL:
        logger.warning(log_msg)
    elif severity == AuditSeverity.WARNING:
        logger.info(log_msg)
    else:
        logger.debug(log_msg)

    return audit_log


async def is_new_ip_for_user(
    db: AsyncSession,
    user_id: UUID,
    ip_address: str,
) -> bool:
    """Check if this IP address is new for the given user.

    Returns True if this is the first time this IP has been used for a successful login.
    Checks both password logins and OAuth logins.
    """
    from sqlalchemy import func, or_, select

    count = await db.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.user_id == user_id,
            or_(
                AuditLog.event_type == AuditEventType.LOGIN_SUCCESS,
                AuditLog.event_type == AuditEventType.OAUTH_LOGIN_SUCCESS,
            ),
            AuditLog.ip_address == ip_address,
        )
    )
    return count == 0


async def has_previous_logins(
    db: AsyncSession,
    user_id: UUID,
) -> bool:
    """Check if user has any previous successful logins.

    Returns True if user has logged in before (any IP).
    Used to avoid sending new IP alerts on first-ever login.
    """
    from sqlalchemy import func, or_, select

    count = await db.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.user_id == user_id,
            or_(
                AuditLog.event_type == AuditEventType.LOGIN_SUCCESS,
                AuditLog.event_type == AuditEventType.OAUTH_LOGIN_SUCCESS,
            ),
        )
    )
    return count > 0


# =============================================================================
# Authentication Events
# =============================================================================


async def audit_login_success(
    db: AsyncSession,
    user_id: UUID,
    request: Request,
    *,
    method: str = "password",
) -> AuditLog:
    """Log a successful login attempt."""
    return await log_audit_event(
        db,
        AuditEventType.LOGIN_SUCCESS,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        details={"method": method},
    )


async def audit_login_failure(
    db: AsyncSession,
    request: Request,
    *,
    email: str | None = None,
    user_id: UUID | None = None,
    reason: str = "Invalid credentials",
) -> AuditLog:
    """Log a failed login attempt."""
    details: dict[str, Any] = {"reason": reason}
    if email:
        details["email"] = email

    return await log_audit_event(
        db,
        AuditEventType.LOGIN_FAILURE,
        user_id=user_id,
        severity=AuditSeverity.WARNING,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        details=details,
    )


async def audit_logout(
    db: AsyncSession,
    user_id: UUID,
    request: Request,
) -> AuditLog:
    """Log a user logout."""
    return await log_audit_event(
        db,
        AuditEventType.LOGOUT,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )


async def audit_oauth_login_success(
    db: AsyncSession,
    user_id: UUID,
    request: Request,
    *,
    provider: str,
    is_new_user: bool = False,
) -> AuditLog:
    """Log a successful OAuth login."""
    return await log_audit_event(
        db,
        AuditEventType.OAUTH_LOGIN_SUCCESS,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        details={"provider": provider, "is_new_user": is_new_user},
    )


async def audit_oauth_login_failure(
    db: AsyncSession,
    request: Request,
    *,
    provider: str,
    reason: str,
    email: str | None = None,
) -> AuditLog:
    """Log a failed OAuth login attempt."""
    details: dict[str, Any] = {"provider": provider, "reason": reason}
    if email:
        details["email"] = email

    return await log_audit_event(
        db,
        AuditEventType.OAUTH_LOGIN_FAILURE,
        severity=AuditSeverity.WARNING,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        details=details,
    )


# =============================================================================
# Password Events
# =============================================================================


async def audit_password_change(
    db: AsyncSession,
    user_id: UUID,
    request: Request,
) -> AuditLog:
    """Log a password change."""
    return await log_audit_event(
        db,
        AuditEventType.PASSWORD_CHANGE,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )


async def audit_password_reset_request(
    db: AsyncSession,
    user_id: UUID,
    request: Request,
) -> AuditLog:
    """Log a password reset request."""
    return await log_audit_event(
        db,
        AuditEventType.PASSWORD_RESET_REQUEST,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )


async def audit_password_reset_complete(
    db: AsyncSession,
    user_id: UUID,
    request: Request,
) -> AuditLog:
    """Log a completed password reset."""
    return await log_audit_event(
        db,
        AuditEventType.PASSWORD_RESET_COMPLETE,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )


# =============================================================================
# Email Verification Events
# =============================================================================


async def audit_email_verification_sent(
    db: AsyncSession,
    user_id: UUID,
    request: Request | None = None,
) -> AuditLog:
    """Log an email verification being sent."""
    return await log_audit_event(
        db,
        AuditEventType.EMAIL_VERIFICATION_SENT,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        ip_address=get_client_ip(request) if request else None,
        user_agent=get_user_agent(request) if request else None,
    )


async def audit_email_verified(
    db: AsyncSession,
    user_id: UUID,
    request: Request,
) -> AuditLog:
    """Log a successful email verification."""
    return await log_audit_event(
        db,
        AuditEventType.EMAIL_VERIFIED,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )


# =============================================================================
# API Key Events
# =============================================================================


async def audit_api_key_created(
    db: AsyncSession,
    user_id: UUID,
    request: Request,
    *,
    key_id: UUID,
    key_name: str,
) -> AuditLog:
    """Log an API key creation."""
    return await log_audit_event(
        db,
        AuditEventType.API_KEY_CREATED,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        details={"key_id": str(key_id), "key_name": key_name},
    )


async def audit_api_key_revoked(
    db: AsyncSession,
    user_id: UUID,
    request: Request,
    *,
    key_id: UUID,
) -> AuditLog:
    """Log an API key revocation."""
    return await log_audit_event(
        db,
        AuditEventType.API_KEY_REVOKED,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        details={"key_id": str(key_id)},
    )


# =============================================================================
# Account Events
# =============================================================================


async def audit_account_created(
    db: AsyncSession,
    user_id: UUID,
    request: Request,
    *,
    method: str = "email",
) -> AuditLog:
    """Log a new account creation."""
    return await log_audit_event(
        db,
        AuditEventType.ACCOUNT_CREATED,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        details={"method": method},
    )


async def audit_account_locked(
    db: AsyncSession,
    user_id: UUID,
    request: Request | None = None,
    *,
    reason: str = "Too many failed login attempts",
) -> AuditLog:
    """Log an account being locked."""
    return await log_audit_event(
        db,
        AuditEventType.ACCOUNT_LOCKED,
        user_id=user_id,
        severity=AuditSeverity.CRITICAL,
        ip_address=get_client_ip(request) if request else None,
        user_agent=get_user_agent(request) if request else None,
        details={"reason": reason},
    )


async def audit_account_unlocked(
    db: AsyncSession,
    user_id: UUID,
    request: Request | None = None,
    *,
    reason: str = "Manual unlock",
) -> AuditLog:
    """Log an account being unlocked."""
    return await log_audit_event(
        db,
        AuditEventType.ACCOUNT_UNLOCKED,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        ip_address=get_client_ip(request) if request else None,
        user_agent=get_user_agent(request) if request else None,
        details={"reason": reason},
    )


async def audit_account_deleted(
    db: AsyncSession,
    user_id: UUID,
    request: Request,
) -> AuditLog:
    """Log a user-initiated account deletion."""
    return await log_audit_event(
        db,
        AuditEventType.ACCOUNT_DELETED,
        user_id=user_id,
        severity=AuditSeverity.CRITICAL,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )


async def audit_data_exported(
    db: AsyncSession,
    user_id: UUID,
    request: Request,
    *,
    export_size_bytes: int | None = None,
) -> AuditLog:
    """Log a user-initiated data export."""
    details = {"export_size_bytes": export_size_bytes} if export_size_bytes is not None else None
    return await log_audit_event(
        db,
        AuditEventType.DATA_EXPORTED,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        details=details,
    )


# =============================================================================
# Authorization Events
# =============================================================================


async def audit_permission_denied(
    db: AsyncSession,
    user_id: UUID | None,
    request: Request,
    *,
    resource: str,
    action: str,
    reason: str = "Insufficient permissions",
) -> AuditLog:
    """Log a permission denied event."""
    return await log_audit_event(
        db,
        AuditEventType.PERMISSION_DENIED,
        user_id=user_id,
        severity=AuditSeverity.WARNING,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        details={"resource": resource, "action": action, "reason": reason},
    )


# =============================================================================
# Subscription Events
# =============================================================================


async def audit_subscription_created(
    db: AsyncSession,
    user_id: UUID,
    *,
    tier: str,
    stripe_subscription_id: str | None = None,
) -> AuditLog:
    """Log a subscription creation."""
    return await log_audit_event(
        db,
        AuditEventType.SUBSCRIPTION_CREATED,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        details={"tier": tier, "stripe_subscription_id": stripe_subscription_id},
    )


async def audit_subscription_updated(
    db: AsyncSession,
    user_id: UUID,
    *,
    old_tier: str | None = None,
    new_tier: str,
    reason: str | None = None,
) -> AuditLog:
    """Log a subscription update."""
    details: dict[str, Any] = {"new_tier": new_tier}
    if old_tier:
        details["old_tier"] = old_tier
    if reason:
        details["reason"] = reason

    return await log_audit_event(
        db,
        AuditEventType.SUBSCRIPTION_UPDATED,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        details=details,
    )


async def audit_subscription_canceled(
    db: AsyncSession,
    user_id: UUID,
    *,
    tier: str,
    reason: str | None = None,
) -> AuditLog:
    """Log a subscription cancellation."""
    details: dict[str, Any] = {"tier": tier}
    if reason:
        details["reason"] = reason

    return await log_audit_event(
        db,
        AuditEventType.SUBSCRIPTION_CANCELED,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        details=details,
    )


async def audit_payment_method_added(
    db: AsyncSession,
    user_id: UUID,
    request: Request | None = None,
) -> AuditLog:
    """Log a payment method being added."""
    return await log_audit_event(
        db,
        AuditEventType.PAYMENT_METHOD_ADDED,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        ip_address=get_client_ip(request) if request else None,
        user_agent=get_user_agent(request) if request else None,
    )


async def audit_payment_method_removed(
    db: AsyncSession,
    user_id: UUID,
    request: Request | None = None,
) -> AuditLog:
    """Log a payment method being removed."""
    return await log_audit_event(
        db,
        AuditEventType.PAYMENT_METHOD_REMOVED,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        ip_address=get_client_ip(request) if request else None,
        user_agent=get_user_agent(request) if request else None,
    )


# =============================================================================
# OAuth Account Events
# =============================================================================


async def audit_oauth_account_linked(
    db: AsyncSession,
    user_id: UUID,
    request: Request,
    *,
    provider: str,
) -> AuditLog:
    """Log an OAuth account being linked."""
    return await log_audit_event(
        db,
        AuditEventType.OAUTH_ACCOUNT_LINKED,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        details={"provider": provider},
    )


async def audit_oauth_account_unlinked(
    db: AsyncSession,
    user_id: UUID,
    request: Request,
    *,
    provider: str,
) -> AuditLog:
    """Log an OAuth account being unlinked."""
    return await log_audit_event(
        db,
        AuditEventType.OAUTH_ACCOUNT_UNLINKED,
        user_id=user_id,
        severity=AuditSeverity.INFO,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
        details={"provider": provider},
    )
