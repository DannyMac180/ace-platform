"""Sentry context enrichment helpers.

This module provides functions to enrich Sentry error reports with
application-specific context such as user IDs, playbook IDs, and job IDs.

Usage:
    from ace_platform.core.sentry_context import (
        set_user_context,
        set_playbook_context,
        set_job_context,
    )

    # In an authenticated route
    set_user_context(user_id=user.id, email=user.email)

    # When processing a playbook
    set_playbook_context(playbook_id=playbook.id, playbook_name=playbook.name)

    # When processing an evolution job
    set_job_context(job_id=job.id, status=job.status)
"""

from collections.abc import Mapping

import sentry_sdk

REDACTED_HEADER_VALUE = "[REDACTED]"

# Explicitly sensitive header names that should never be sent to Sentry
SENSITIVE_REQUEST_HEADERS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "x-auth-token",
    "x-access-token",
}

# Additional marker substrings for secret-bearing header names
SENSITIVE_HEADER_MARKERS = (
    "token",
    "secret",
    "api-key",
    "session",
)


def set_user_context(
    user_id: str | None = None,
    email: str | None = None,
    username: str | None = None,
) -> None:
    """Set user context for Sentry error reports.

    This enriches error reports with user information to help identify
    which users are affected by issues.

    Args:
        user_id: The user's unique identifier.
        email: The user's email address.
        username: The user's display name.
    """
    if not any([user_id, email, username]):
        return

    sentry_sdk.set_user(
        {
            "id": user_id,
            "email": email,
            "username": username,
        }
    )


def clear_user_context() -> None:
    """Clear user context from Sentry scope.

    Call this after processing a request to ensure user context
    doesn't leak to subsequent requests.
    """
    sentry_sdk.set_user(None)


def set_playbook_context(
    playbook_id: str | None = None,
    playbook_name: str | None = None,
    version_id: str | None = None,
    owner_id: str | None = None,
) -> None:
    """Set playbook context for Sentry error reports.

    Args:
        playbook_id: The playbook's unique identifier.
        playbook_name: The playbook's name.
        version_id: The current playbook version ID.
        owner_id: The playbook owner's user ID.
    """
    context = {}
    if playbook_id:
        context["playbook_id"] = playbook_id
        sentry_sdk.set_tag("playbook_id", playbook_id)
    if playbook_name:
        context["playbook_name"] = playbook_name
    if version_id:
        context["version_id"] = version_id
    if owner_id:
        context["owner_id"] = owner_id

    if context:
        sentry_sdk.set_context("playbook", context)


def set_job_context(
    job_id: str | None = None,
    job_type: str | None = None,
    status: str | None = None,
    playbook_id: str | None = None,
) -> None:
    """Set evolution job context for Sentry error reports.

    Args:
        job_id: The job's unique identifier.
        job_type: The type of job (e.g., "evolution").
        status: The job's current status.
        playbook_id: The associated playbook ID.
    """
    context = {}
    if job_id:
        context["job_id"] = job_id
        sentry_sdk.set_tag("job_id", job_id)
    if job_type:
        context["job_type"] = job_type
    if status:
        context["status"] = status
    if playbook_id:
        context["playbook_id"] = playbook_id

    if context:
        sentry_sdk.set_context("job", context)


def add_breadcrumb(
    message: str,
    category: str = "custom",
    level: str = "info",
    data: dict | None = None,
) -> None:
    """Add a breadcrumb to the Sentry trail.

    Breadcrumbs help understand the sequence of events leading to an error.

    Args:
        message: Description of what happened.
        category: Category for grouping (e.g., "auth", "evolution", "api").
        level: Severity level (debug, info, warning, error, critical).
        data: Additional structured data.
    """
    sentry_sdk.add_breadcrumb(
        message=message,
        category=category,
        level=level,
        data=data or {},
    )


def sanitize_request_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return headers safe for telemetry by redacting sensitive values.

    Args:
        headers: Request header mapping.

    Returns:
        Dict with sensitive header values replaced by ``[REDACTED]``.
    """
    sanitized: dict[str, str] = {}

    for name, value in headers.items():
        normalized_name = name.lower()

        is_sensitive = normalized_name in SENSITIVE_REQUEST_HEADERS or any(
            marker in normalized_name for marker in SENSITIVE_HEADER_MARKERS
        )

        sanitized[name] = REDACTED_HEADER_VALUE if is_sensitive else value

    return sanitized
