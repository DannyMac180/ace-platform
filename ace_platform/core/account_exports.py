"""Shared account-export payload builder."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ace_platform.db.models import ApiKey, AuditLog, Playbook, UsageRecord, User, UserOAuthAccount


def isoformat_or_none(value: datetime | None) -> str | None:
    """Convert a datetime into an ISO8601 string."""

    return value.isoformat() if value is not None else None


def stringify_uuid(value: object | None) -> str | None:
    """Convert UUID-like values into strings."""

    return str(value) if value is not None else None


def json_default(value: Any) -> Any:
    """Serialize values that are not JSON-native."""

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


async def build_account_export_payload(db: AsyncSession, user: User) -> dict[str, Any]:
    """Build the downloadable account-export payload for one user."""

    playbooks_result = await db.execute(
        select(Playbook)
        .where(Playbook.user_id == user.id)
        .options(
            selectinload(Playbook.versions),
            selectinload(Playbook.outcomes),
            selectinload(Playbook.evolution_jobs),
        )
        .order_by(Playbook.created_at.desc())
    )
    playbooks = playbooks_result.scalars().all()

    api_keys_result = await db.execute(
        select(ApiKey).where(ApiKey.user_id == user.id).order_by(ApiKey.created_at.desc())
    )
    api_keys = api_keys_result.scalars().all()

    oauth_result = await db.execute(
        select(UserOAuthAccount)
        .where(UserOAuthAccount.user_id == user.id)
        .order_by(UserOAuthAccount.created_at.desc())
    )
    oauth_accounts = oauth_result.scalars().all()

    usage_result = await db.execute(
        select(UsageRecord)
        .where(UsageRecord.user_id == user.id)
        .order_by(UsageRecord.created_at.desc())
    )
    usage_records = usage_result.scalars().all()

    audit_result = await db.execute(
        select(AuditLog)
        .where(AuditLog.user_id == user.id)
        .order_by(AuditLog.created_at.desc())
        .limit(500)
    )
    audit_logs = audit_result.scalars().all()

    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "user": {
            "id": str(user.id),
            "email": user.email,
            "is_active": user.is_active,
            "email_verified": user.email_verified,
            "subscription_tier": user.subscription_tier,
            "subscription_status": user.subscription_status.value,
            "subscription_current_period_end": isoformat_or_none(
                user.subscription_current_period_end
            ),
            "has_used_trial": user.has_used_trial,
            "trial_ends_at": isoformat_or_none(user.trial_ends_at),
            "has_payment_method": user.has_payment_method,
            "stripe_customer_id": user.stripe_customer_id,
            "stripe_subscription_id": user.stripe_subscription_id,
            "created_at": isoformat_or_none(user.created_at),
            "updated_at": isoformat_or_none(user.updated_at),
        },
        "playbooks": [
            {
                "id": str(playbook.id),
                "name": playbook.name,
                "description": playbook.description,
                "status": playbook.status.value,
                "review_status": playbook.review_status.value,
                "review_status_updated_at": isoformat_or_none(playbook.review_status_updated_at),
                "review_history": playbook.review_history,
                "source": playbook.source.value,
                "current_version_id": stringify_uuid(playbook.current_version_id),
                "created_at": isoformat_or_none(playbook.created_at),
                "updated_at": isoformat_or_none(playbook.updated_at),
                "versions": [
                    {
                        "id": str(version.id),
                        "version_number": version.version_number,
                        "content": version.content,
                        "bullet_count": version.bullet_count,
                        "diff_summary": version.diff_summary,
                        "created_by_job_id": stringify_uuid(version.created_by_job_id),
                        "created_at": isoformat_or_none(version.created_at),
                    }
                    for version in playbook.versions
                ],
                "outcomes": [
                    {
                        "id": str(outcome.id),
                        "task_description": outcome.task_description,
                        "outcome_status": outcome.outcome_status.value,
                        "notes": outcome.notes,
                        "reasoning_trace": outcome.reasoning_trace,
                        "created_at": isoformat_or_none(outcome.created_at),
                        "processed_at": isoformat_or_none(outcome.processed_at),
                        "evolution_job_id": stringify_uuid(outcome.evolution_job_id),
                    }
                    for outcome in playbook.outcomes
                ],
                "evolutions": [
                    {
                        "id": str(job.id),
                        "status": job.status.value,
                        "from_version_id": stringify_uuid(job.from_version_id),
                        "to_version_id": stringify_uuid(job.to_version_id),
                        "outcomes_processed": job.outcomes_processed,
                        "error_message": job.error_message,
                        "created_at": isoformat_or_none(job.created_at),
                        "started_at": isoformat_or_none(job.started_at),
                        "completed_at": isoformat_or_none(job.completed_at),
                        "token_totals": job.token_totals,
                        "ace_core_version": job.ace_core_version,
                    }
                    for job in playbook.evolution_jobs
                ],
            }
            for playbook in playbooks
        ],
        "api_keys": [
            {
                "id": str(api_key.id),
                "name": api_key.name,
                "key_prefix": api_key.key_prefix,
                "scopes": api_key.scopes,
                "created_at": isoformat_or_none(api_key.created_at),
                "last_used_at": isoformat_or_none(api_key.last_used_at),
                "revoked_at": isoformat_or_none(api_key.revoked_at),
                "is_active": api_key.is_active,
            }
            for api_key in api_keys
        ],
        "oauth_accounts": [
            {
                "id": str(account.id),
                "provider": account.provider.value,
                "provider_user_id": account.provider_user_id,
                "provider_email": account.provider_email,
                "created_at": isoformat_or_none(account.created_at),
                "updated_at": isoformat_or_none(account.updated_at),
            }
            for account in oauth_accounts
        ],
        "usage_records": [
            {
                "id": str(record.id),
                "playbook_id": stringify_uuid(record.playbook_id),
                "evolution_job_id": stringify_uuid(record.evolution_job_id),
                "operation": record.operation,
                "model": record.model,
                "prompt_tokens": record.prompt_tokens,
                "completion_tokens": record.completion_tokens,
                "total_tokens": record.total_tokens,
                "cost_usd": str(record.cost_usd),
                "request_id": record.request_id,
                "extra_data": record.extra_data,
                "created_at": isoformat_or_none(record.created_at),
            }
            for record in usage_records
        ],
        "audit_logs": [
            {
                "id": str(log.id),
                "event_type": log.event_type.value,
                "severity": log.severity.value,
                "created_at": log.created_at.isoformat(),
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "details": log.details,
            }
            for log in audit_logs
        ],
    }


__all__ = [
    "build_account_export_payload",
    "isoformat_or_none",
    "json_default",
    "stringify_uuid",
]
