"""Account management routes.

This module provides endpoints for account self-service:
- DELETE /account - Hard delete account and cascade user-owned data
- GET /account/export - Download a JSON export of user data
- GET /account/audit-logs - View recent security activity
"""

import json
import logging
from datetime import UTC, datetime
from typing import Annotated

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ace_platform.api.auth import RequiredUser
from ace_platform.api.deps import get_db
from ace_platform.config import get_settings
from ace_platform.core.account_exports import build_account_export_payload, json_default
from ace_platform.core.audit import audit_account_deleted, audit_data_exported
from ace_platform.core.security import verify_password
from ace_platform.db.models import AuditEventType, AuditLog, AuditSeverity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/account", tags=["account"])


# Dependency type aliases
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = RequiredUser


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str


class DeleteAccountRequest(BaseModel):
    """Request body for account deletion."""

    confirm: str = Field(..., description='Must be exactly "DELETE"')
    password: str | None = Field(None, description="Required if the account has a password set")


class AuditLogItem(BaseModel):
    """Audit log item returned to users."""

    id: str
    event_type: str
    severity: str
    created_at: datetime
    ip_address: str | None
    user_agent: str | None
    details: dict | None


class PaginatedAuditLogResponse(BaseModel):
    """Paginated audit log response."""

    items: list[AuditLogItem]
    total: int
    page: int
    page_size: int
    total_pages: int


@router.delete("", response_model=MessageResponse)
async def delete_account(
    body: DeleteAccountRequest,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
) -> MessageResponse:
    """Hard delete the authenticated user's account.

    This deletes the user row and cascades user-owned data. Audit logs are retained with
    user_id set to NULL via FK ondelete=SET NULL.
    """
    if body.confirm != "DELETE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Confirmation required. Type "DELETE" to confirm.',
        )

    # If the user has a password, require verifying it to prevent token theft deletions.
    if current_user.hashed_password:
        if not body.password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password is required to delete this account.",
            )
        if not verify_password(body.password, current_user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect password.",
            )

    # Best-effort Stripe cleanup (do not block deletion if Stripe fails)
    settings = get_settings()
    if settings.billing_enabled and settings.stripe_secret_key:
        try:
            client = stripe.StripeClient(settings.stripe_secret_key)
            if current_user.stripe_subscription_id:
                try:
                    client.subscriptions.cancel(current_user.stripe_subscription_id)
                except Exception as e:  # StripeError + other runtime issues
                    logger.warning(
                        "Failed to cancel Stripe subscription during account deletion",
                        extra={
                            "user_id": str(current_user.id),
                            "stripe_subscription_id": current_user.stripe_subscription_id,
                            "error": str(e),
                        },
                    )
            if current_user.stripe_customer_id:
                try:
                    client.customers.delete(current_user.stripe_customer_id)
                except Exception as e:  # StripeError + other runtime issues
                    logger.warning(
                        "Failed to delete Stripe customer during account deletion",
                        extra={
                            "user_id": str(current_user.id),
                            "stripe_customer_id": current_user.stripe_customer_id,
                            "error": str(e),
                        },
                    )
        except Exception as e:
            logger.warning(
                "Stripe client initialization failed during account deletion",
                extra={"user_id": str(current_user.id), "error": str(e)},
            )

    # Audit the deletion prior to removing the user record (FK will set user_id to NULL).
    await audit_account_deleted(db, current_user.id, request)
    await db.flush()

    await db.delete(current_user)
    await db.commit()

    return MessageResponse(message="Account deleted")


@router.get("/export")
async def export_account_data(
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
) -> Response:
    """Export user data as a downloadable JSON file."""
    export_data = await build_account_export_payload(db, current_user)
    payload = json.dumps(export_data, default=json_default).encode("utf-8")

    # Enforce a conservative max export size (25MB)
    max_bytes = 25 * 1024 * 1024
    if len(payload) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Export is too large to download. Please contact support to request an offline export.",
        )

    # Audit export only if it succeeds
    await audit_data_exported(db, current_user.id, request, export_size_bytes=len(payload))
    await db.commit()

    filename = f"ace-export-{datetime.now(UTC).date().isoformat()}.json"
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/audit-logs", response_model=PaginatedAuditLogResponse)
async def list_audit_logs(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Items per page"),
    event_type: AuditEventType | None = Query(None, description="Filter by event type"),
    severity: AuditSeverity | None = Query(None, description="Filter by severity"),
) -> PaginatedAuditLogResponse:
    """List audit logs for the authenticated user."""
    base_query = select(AuditLog).where(AuditLog.user_id == current_user.id)

    if event_type:
        base_query = base_query.where(AuditLog.event_type == event_type)
    if severity:
        base_query = base_query.where(AuditLog.severity == severity)

    count_query = select(func.count()).select_from(base_query.subquery())
    total = await db.scalar(count_query) or 0

    offset = (page - 1) * page_size
    logs_result = await db.execute(
        base_query.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size)
    )
    logs = logs_result.scalars().all()

    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return PaginatedAuditLogResponse(
        items=[
            AuditLogItem(
                id=str(log.id),
                event_type=log.event_type.value,
                severity=log.severity.value,
                created_at=log.created_at,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                details=log.details,
            )
            for log in logs
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
