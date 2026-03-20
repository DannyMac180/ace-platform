"""Hosted personal workspace backup and restore services."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ace_platform.core.account_exports import (
    build_account_export_payload,
    isoformat_or_none,
    json_default,
)
from ace_platform.db.models import (
    ApiKey,
    EvolutionJob,
    EvolutionJobStatus,
    Membership,
    MembershipRole,
    OAuthProvider,
    Outcome,
    OutcomeStatus,
    Playbook,
    PlaybookReviewStatus,
    PlaybookSource,
    PlaybookStatus,
    PlaybookVersion,
    SubscriptionStatus,
    UsageRecord,
    User,
    UserOAuthAccount,
    Workspace,
    WorkspaceBackup,
    WorkspaceBillingProvider,
    WorkspaceDeploymentMode,
    WorkspaceEntitlement,
    WorkspacePlan,
    WorkspaceSubscription,
    WorkspaceSubscriptionStatus,
    get_default_workspace_inference_config,
)

WORKSPACE_BACKUP_RETENTION_COUNT = 10
WORKSPACE_BACKUP_SCHEMA_VERSION = 1
RESTOREABLE_PERSONAL_PLAN = WorkspacePlan.PERSONAL
RESTOREABLE_DEPLOYMENT_MODE = WorkspaceDeploymentMode.CLOUD


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _parse_decimal(value: str | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(value)


def _workspace_is_restoreable(workspace: Workspace) -> bool:
    return (
        workspace.plan == RESTOREABLE_PERSONAL_PLAN
        and workspace.deployment_mode == RESTOREABLE_DEPLOYMENT_MODE
    )


async def get_restoreable_personal_workspace(
    db: AsyncSession,
    workspace_id: UUID,
) -> Workspace | None:
    """Load a hosted personal workspace with the data needed for backup/restore."""

    result = await db.execute(
        select(Workspace)
        .where(Workspace.id == workspace_id)
        .options(
            selectinload(Workspace.memberships).selectinload(Membership.user),
            selectinload(Workspace.entitlements),
            selectinload(Workspace.subscription),
        )
    )
    workspace = result.scalars().unique().one_or_none()
    if workspace is None or not _workspace_is_restoreable(workspace):
        return None
    return workspace


async def list_restoreable_personal_workspaces(db: AsyncSession) -> list[Workspace]:
    """List all hosted personal workspaces eligible for managed backups."""

    result = await db.execute(
        select(Workspace)
        .join(WorkspaceEntitlement)
        .where(
            Workspace.plan == RESTOREABLE_PERSONAL_PLAN,
            Workspace.deployment_mode == RESTOREABLE_DEPLOYMENT_MODE,
            WorkspaceEntitlement.hosted_backups.is_(True),
        )
        .options(
            selectinload(Workspace.memberships).selectinload(Membership.user),
            selectinload(Workspace.entitlements),
            selectinload(Workspace.subscription),
        )
        .order_by(Workspace.created_at.asc())
    )
    return list(result.scalars().unique().all())


def _serialize_membership(membership: Membership) -> dict[str, Any]:
    return {
        "workspace_id": str(membership.workspace_id),
        "user_id": str(membership.user_id),
        "role": membership.role.value,
        "created_at": isoformat_or_none(membership.created_at),
        "updated_at": isoformat_or_none(membership.updated_at),
    }


def _serialize_workspace(workspace: Workspace) -> dict[str, Any]:
    return {
        "id": str(workspace.id),
        "name": workspace.name,
        "plan": workspace.plan.value,
        "deployment_mode": workspace.deployment_mode.value,
        "seat_limit": workspace.seat_limit,
        "usage_limits": workspace.usage_limits,
        "inference_config": workspace.inference_config,
        "created_at": isoformat_or_none(workspace.created_at),
        "updated_at": isoformat_or_none(workspace.updated_at),
    }


def _restore_workspace_inference_config(workspace_payload: dict[str, Any]) -> dict[str, Any]:
    plan = WorkspacePlan(workspace_payload["plan"])
    deployment_mode = WorkspaceDeploymentMode(workspace_payload["deployment_mode"])
    return workspace_payload.get("inference_config") or get_default_workspace_inference_config(
        plan=plan,
        deployment_mode=deployment_mode,
    )


def _serialize_entitlements(entitlements: WorkspaceEntitlement | None) -> dict[str, Any] | None:
    if entitlements is None:
        return None
    return {
        "cloud_sync": entitlements.cloud_sync,
        "hosted_backups": entitlements.hosted_backups,
        "managed_inference": entitlements.managed_inference,
        "hosted_evals": entitlements.hosted_evals,
        "invite_members": entitlements.invite_members,
        "shared_workspace": entitlements.shared_workspace,
        "approvals": entitlements.approvals,
        "rbac": entitlements.rbac,
        "sso": entitlements.sso,
        "audit_logs": entitlements.audit_logs,
        "created_at": isoformat_or_none(entitlements.created_at),
        "updated_at": isoformat_or_none(entitlements.updated_at),
    }


def _serialize_subscription(subscription: WorkspaceSubscription | None) -> dict[str, Any] | None:
    if subscription is None:
        return None
    return {
        "billing_provider": subscription.billing_provider.value,
        "status": subscription.status.value,
        "plan_code": subscription.plan_code,
        "provider_customer_id": subscription.provider_customer_id,
        "provider_subscription_id": subscription.provider_subscription_id,
        "current_period_end": isoformat_or_none(subscription.current_period_end),
        "trial_ends_at": isoformat_or_none(subscription.trial_ends_at),
        "created_at": isoformat_or_none(subscription.created_at),
        "updated_at": isoformat_or_none(subscription.updated_at),
    }


def _serialize_private_user(user: User) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "email": user.email,
        "hashed_password": user.hashed_password,
        "is_active": user.is_active,
        "is_admin": user.is_admin,
        "email_verified": user.email_verified,
        "stripe_customer_id": user.stripe_customer_id,
        "stripe_subscription_id": user.stripe_subscription_id,
        "subscription_tier": user.subscription_tier,
        "subscription_status": user.subscription_status.value,
        "subscription_current_period_end": isoformat_or_none(user.subscription_current_period_end),
        "signup_source": user.signup_source,
        "signup_channel": user.signup_channel,
        "signup_campaign": user.signup_campaign,
        "signup_anonymous_id": user.signup_anonymous_id,
        "signup_variant": user.signup_variant,
        "signup_attribution": user.signup_attribution,
        "has_used_trial": user.has_used_trial,
        "trial_ends_at": isoformat_or_none(user.trial_ends_at),
        "has_payment_method": user.has_payment_method,
        "stripe_default_payment_method_id": user.stripe_default_payment_method_id,
        "created_at": isoformat_or_none(user.created_at),
        "updated_at": isoformat_or_none(user.updated_at),
    }


def _serialize_private_api_key(api_key: ApiKey) -> dict[str, Any]:
    return {
        "id": str(api_key.id),
        "name": api_key.name,
        "key_prefix": api_key.key_prefix,
        "hashed_key": api_key.hashed_key,
        "scopes": api_key.scopes,
        "created_at": isoformat_or_none(api_key.created_at),
        "last_used_at": isoformat_or_none(api_key.last_used_at),
        "revoked_at": isoformat_or_none(api_key.revoked_at),
    }


def _serialize_private_oauth_account(account: UserOAuthAccount) -> dict[str, Any]:
    return {
        "id": str(account.id),
        "provider": account.provider.value,
        "provider_user_id": account.provider_user_id,
        "provider_email": account.provider_email,
        "access_token": account.access_token,
        "refresh_token": account.refresh_token,
        "token_expires_at": isoformat_or_none(account.token_expires_at),
        "raw_user_info": account.raw_user_info,
        "created_at": isoformat_or_none(account.created_at),
        "updated_at": isoformat_or_none(account.updated_at),
    }


async def build_workspace_backup_payload(
    db: AsyncSession,
    workspace: Workspace,
) -> dict[str, Any]:
    """Build the persisted snapshot payload for one hosted personal workspace."""

    if not _workspace_is_restoreable(workspace):
        raise ValueError("Only hosted personal workspaces support managed backups.")

    owner_membership = next(
        (membership for membership in workspace.memberships if membership.user is not None),
        None,
    )
    if owner_membership is None or owner_membership.user is None:
        raise ValueError("Workspace has no restorable owner membership.")

    account_export = await build_account_export_payload(db, owner_membership.user)
    api_keys_result = await db.execute(
        select(ApiKey)
        .where(ApiKey.user_id == owner_membership.user.id)
        .order_by(ApiKey.created_at.desc())
    )
    oauth_result = await db.execute(
        select(UserOAuthAccount)
        .where(UserOAuthAccount.user_id == owner_membership.user.id)
        .order_by(UserOAuthAccount.created_at.desc())
    )
    api_keys = api_keys_result.scalars().all()
    oauth_accounts = oauth_result.scalars().all()
    return {
        "schema_version": WORKSPACE_BACKUP_SCHEMA_VERSION,
        "captured_at": datetime.now(UTC).isoformat(),
        "workspace": _serialize_workspace(workspace),
        "memberships": [_serialize_membership(membership) for membership in workspace.memberships],
        "entitlements": _serialize_entitlements(workspace.entitlements),
        "subscription": _serialize_subscription(workspace.subscription),
        "account_export": account_export,
        "restore_private": {
            "user": _serialize_private_user(owner_membership.user),
            "api_keys": [_serialize_private_api_key(api_key) for api_key in api_keys],
            "oauth_accounts": [
                _serialize_private_oauth_account(account) for account in oauth_accounts
            ],
        },
    }


async def enforce_workspace_backup_retention(
    db: AsyncSession,
    workspace_id: UUID,
    *,
    retain_count: int = WORKSPACE_BACKUP_RETENTION_COUNT,
) -> int:
    """Keep only the most recent N backups for one workspace."""

    result = await db.execute(
        select(WorkspaceBackup)
        .where(WorkspaceBackup.workspace_id == workspace_id)
        .order_by(WorkspaceBackup.created_at.desc(), WorkspaceBackup.id.desc())
    )
    backups = list(result.scalars().all())
    removed = 0
    for backup in backups[retain_count:]:
        await db.delete(backup)
        removed += 1
    return removed


async def create_workspace_backup_snapshot(
    db: AsyncSession,
    workspace: Workspace,
    *,
    trigger_source: str,
) -> WorkspaceBackup:
    """Persist one backup snapshot and apply retention."""

    payload = await build_workspace_backup_payload(db, workspace)
    owner_user_id = next(
        (membership.user_id for membership in workspace.memberships if membership.user is not None),
        None,
    )
    record = WorkspaceBackup(
        workspace_id=workspace.id,
        owner_user_id=owner_user_id,
        trigger_source=trigger_source,
        payload=payload,
        backup_size_bytes=len(json.dumps(payload, default=json_default).encode("utf-8")),
    )
    db.add(record)
    await db.flush()
    await enforce_workspace_backup_retention(db, workspace.id)
    await db.refresh(record)
    return record


async def list_workspace_backups(
    db: AsyncSession,
    workspace_id: UUID,
    *,
    limit: int = 20,
) -> list[WorkspaceBackup]:
    """List recent backups for one workspace."""

    result = await db.execute(
        select(WorkspaceBackup)
        .where(WorkspaceBackup.workspace_id == workspace_id)
        .order_by(WorkspaceBackup.created_at.desc(), WorkspaceBackup.id.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_workspace_backup(
    db: AsyncSession,
    workspace_id: UUID,
    backup_id: UUID,
) -> WorkspaceBackup | None:
    """Load one backup record for a workspace."""

    result = await db.execute(
        select(WorkspaceBackup).where(
            WorkspaceBackup.workspace_id == workspace_id,
            WorkspaceBackup.id == backup_id,
        )
    )
    return result.scalar_one_or_none()


async def backup_hosted_personal_workspaces(db: AsyncSession) -> dict[str, int]:
    """Create scheduled backups for every eligible hosted personal workspace."""

    workspaces = await list_restoreable_personal_workspaces(db)
    created = 0
    for workspace in workspaces:
        await create_workspace_backup_snapshot(db, workspace, trigger_source="scheduled")
        created += 1
    return {"workspace_count": len(workspaces), "backups_created": created}


def _restore_user_metadata(user: User, payload: dict[str, Any]) -> None:
    user.email = payload["email"]
    user.hashed_password = payload.get("hashed_password")
    user.is_active = bool(payload["is_active"])
    user.is_admin = bool(payload.get("is_admin", user.is_admin))
    user.email_verified = bool(payload["email_verified"])
    user.signup_source = payload.get("signup_source")
    user.signup_channel = payload.get("signup_channel")
    user.signup_campaign = payload.get("signup_campaign")
    user.signup_anonymous_id = payload.get("signup_anonymous_id")
    user.signup_variant = payload.get("signup_variant")
    user.signup_attribution = payload.get("signup_attribution")
    user.subscription_tier = payload["subscription_tier"]
    user.subscription_status = SubscriptionStatus(payload["subscription_status"])
    user.subscription_current_period_end = _parse_datetime(
        payload["subscription_current_period_end"]
    )
    user.has_used_trial = bool(payload["has_used_trial"])
    user.trial_ends_at = _parse_datetime(payload["trial_ends_at"])
    user.has_payment_method = bool(payload["has_payment_method"])
    user.stripe_customer_id = payload["stripe_customer_id"]
    user.stripe_subscription_id = payload["stripe_subscription_id"]
    user.stripe_default_payment_method_id = payload.get("stripe_default_payment_method_id")
    user.created_at = _parse_datetime(payload["created_at"]) or user.created_at
    user.updated_at = _parse_datetime(payload["updated_at"]) or user.updated_at


async def _delete_current_user_content(
    db: AsyncSession,
    user_id: UUID,
    *,
    include_auth_artifacts: bool,
) -> None:
    playbooks_result = await db.execute(select(Playbook).where(Playbook.user_id == user_id))
    for playbook in playbooks_result.scalars().all():
        await db.delete(playbook)

    usage_result = await db.execute(select(UsageRecord).where(UsageRecord.user_id == user_id))
    for usage_record in usage_result.scalars().all():
        await db.delete(usage_record)

    if include_auth_artifacts:
        api_key_result = await db.execute(select(ApiKey).where(ApiKey.user_id == user_id))
        for api_key in api_key_result.scalars().all():
            await db.delete(api_key)

        oauth_result = await db.execute(
            select(UserOAuthAccount).where(UserOAuthAccount.user_id == user_id)
        )
        for oauth_account in oauth_result.scalars().all():
            await db.delete(oauth_account)

    await db.flush()


async def _restore_playbooks(
    db: AsyncSession, user_id: UUID, playbook_payloads: list[dict[str, Any]]
) -> None:
    playbooks_by_id: dict[str, Playbook] = {}
    versions_by_id: dict[str, PlaybookVersion] = {}

    for payload in playbook_payloads:
        playbook = Playbook(
            id=UUID(payload["id"]),
            user_id=user_id,
            name=payload["name"],
            description=payload["description"],
            status=PlaybookStatus(payload["status"]),
            review_status=PlaybookReviewStatus(
                payload.get("review_status", PlaybookReviewStatus.DRAFT.value)
            ),
            review_status_updated_at=_parse_datetime(payload.get("review_status_updated_at"))
            or datetime.now(UTC),
            review_history=list(payload.get("review_history") or []),
            source=PlaybookSource(payload["source"]),
            created_at=_parse_datetime(payload["created_at"]) or datetime.now(UTC),
            updated_at=_parse_datetime(payload["updated_at"]) or datetime.now(UTC),
        )
        db.add(playbook)
        playbooks_by_id[payload["id"]] = playbook
    await db.flush()

    for payload in playbook_payloads:
        for version_payload in payload["versions"]:
            version = PlaybookVersion(
                id=UUID(version_payload["id"]),
                playbook_id=UUID(payload["id"]),
                version_number=version_payload["version_number"],
                content=version_payload["content"],
                bullet_count=version_payload["bullet_count"],
                diff_summary=version_payload["diff_summary"],
                created_at=_parse_datetime(version_payload["created_at"]) or datetime.now(UTC),
            )
            db.add(version)
            versions_by_id[version_payload["id"]] = version
    await db.flush()

    for payload in playbook_payloads:
        for job_payload in payload["evolutions"]:
            db.add(
                EvolutionJob(
                    id=UUID(job_payload["id"]),
                    playbook_id=UUID(payload["id"]),
                    status=EvolutionJobStatus(job_payload["status"]),
                    from_version_id=UUID(job_payload["from_version_id"])
                    if job_payload["from_version_id"]
                    else None,
                    to_version_id=UUID(job_payload["to_version_id"])
                    if job_payload["to_version_id"]
                    else None,
                    outcomes_processed=job_payload["outcomes_processed"],
                    started_at=_parse_datetime(job_payload["started_at"]),
                    completed_at=_parse_datetime(job_payload["completed_at"]),
                    error_message=job_payload["error_message"],
                    token_totals=job_payload.get("token_totals"),
                    ace_core_version=job_payload.get("ace_core_version"),
                    created_at=_parse_datetime(job_payload["created_at"]) or datetime.now(UTC),
                )
            )
    await db.flush()

    for payload in playbook_payloads:
        for version_payload in payload["versions"]:
            created_by_job_id = version_payload["created_by_job_id"]
            if created_by_job_id:
                versions_by_id[version_payload["id"]].created_by_job_id = UUID(created_by_job_id)

        for outcome_payload in payload["outcomes"]:
            db.add(
                Outcome(
                    id=UUID(outcome_payload["id"]),
                    playbook_id=UUID(payload["id"]),
                    task_description=outcome_payload["task_description"],
                    outcome_status=OutcomeStatus(outcome_payload["outcome_status"]),
                    notes=outcome_payload["notes"],
                    reasoning_trace=outcome_payload["reasoning_trace"],
                    created_at=_parse_datetime(outcome_payload["created_at"]) or datetime.now(UTC),
                    processed_at=_parse_datetime(outcome_payload["processed_at"]),
                    evolution_job_id=UUID(outcome_payload["evolution_job_id"])
                    if outcome_payload["evolution_job_id"]
                    else None,
                )
            )

        playbooks_by_id[payload["id"]].current_version_id = (
            UUID(payload["current_version_id"]) if payload["current_version_id"] else None
        )

    await db.flush()


async def _restore_usage_records(
    db: AsyncSession,
    user_id: UUID,
    usage_payloads: list[dict[str, Any]],
) -> None:
    for payload in usage_payloads:
        db.add(
            UsageRecord(
                id=UUID(payload["id"]),
                user_id=user_id,
                playbook_id=UUID(payload["playbook_id"]) if payload["playbook_id"] else None,
                evolution_job_id=UUID(payload["evolution_job_id"])
                if payload["evolution_job_id"]
                else None,
                operation=payload["operation"],
                model=payload["model"],
                prompt_tokens=payload["prompt_tokens"],
                completion_tokens=payload["completion_tokens"],
                total_tokens=payload["total_tokens"],
                cost_usd=_parse_decimal(payload["cost_usd"]) or Decimal("0"),
                request_id=payload["request_id"],
                extra_data=payload["extra_data"],
                created_at=_parse_datetime(payload["created_at"]) or datetime.now(UTC),
            )
        )
    await db.flush()


async def _restore_api_keys(
    db: AsyncSession,
    user_id: UUID,
    api_key_payloads: list[dict[str, Any]],
) -> None:
    for payload in api_key_payloads:
        db.add(
            ApiKey(
                id=UUID(payload["id"]),
                user_id=user_id,
                name=payload["name"],
                key_prefix=payload["key_prefix"],
                hashed_key=payload["hashed_key"],
                scopes=payload["scopes"],
                created_at=_parse_datetime(payload["created_at"]) or datetime.now(UTC),
                last_used_at=_parse_datetime(payload["last_used_at"]),
                revoked_at=_parse_datetime(payload["revoked_at"]),
            )
        )
    await db.flush()


async def _restore_oauth_accounts(
    db: AsyncSession,
    user_id: UUID,
    oauth_payloads: list[dict[str, Any]],
) -> None:
    for payload in oauth_payloads:
        db.add(
            UserOAuthAccount(
                id=UUID(payload["id"]),
                user_id=user_id,
                provider=OAuthProvider(payload["provider"]),
                provider_user_id=payload["provider_user_id"],
                provider_email=payload["provider_email"],
                access_token=payload.get("access_token"),
                refresh_token=payload.get("refresh_token"),
                token_expires_at=_parse_datetime(payload.get("token_expires_at")),
                raw_user_info=payload.get("raw_user_info"),
                created_at=_parse_datetime(payload["created_at"]) or datetime.now(UTC),
                updated_at=_parse_datetime(payload["updated_at"]) or datetime.now(UTC),
            )
        )
    await db.flush()


async def restore_workspace_backup(
    db: AsyncSession,
    backup: WorkspaceBackup,
) -> dict[str, Any]:
    """Restore one backup payload back into the hosted personal workspace."""

    payload = backup.payload
    workspace_payload = payload["workspace"]
    account_export = payload["account_export"]
    user_payload = account_export["user"]
    private_payload = payload.get("restore_private") or {}
    private_user_payload = private_payload.get("user", user_payload)
    user = await db.get(User, UUID(private_user_payload["id"]))
    if user is not None and sa_inspect(user).deleted:
        db.expunge(user)
        user = None
    if user is None:
        user = User(id=UUID(private_user_payload["id"]), email=private_user_payload["email"])
        db.add(user)
        await db.flush()

    _restore_user_metadata(user, private_user_payload)

    workspace_result = await db.execute(
        select(Workspace)
        .where(Workspace.id == UUID(workspace_payload["id"]))
        .options(
            selectinload(Workspace.entitlements),
            selectinload(Workspace.subscription),
        )
    )
    workspace = workspace_result.scalars().one_or_none()
    if workspace is not None and sa_inspect(workspace).deleted:
        db.expunge(workspace)
        workspace = None
    workspace_created = workspace is None
    if workspace is None:
        workspace = Workspace(
            id=UUID(workspace_payload["id"]),
            name=workspace_payload["name"],
            plan=WorkspacePlan(workspace_payload["plan"]),
            deployment_mode=WorkspaceDeploymentMode(workspace_payload["deployment_mode"]),
            seat_limit=workspace_payload["seat_limit"],
            usage_limits=workspace_payload["usage_limits"],
            inference_config=_restore_workspace_inference_config(workspace_payload),
            created_at=_parse_datetime(workspace_payload["created_at"]) or datetime.now(UTC),
            updated_at=_parse_datetime(workspace_payload["updated_at"]) or datetime.now(UTC),
        )
        db.add(workspace)
        await db.flush()
    else:
        workspace.name = workspace_payload["name"]
        workspace.plan = WorkspacePlan(workspace_payload["plan"])
        workspace.deployment_mode = WorkspaceDeploymentMode(workspace_payload["deployment_mode"])
        workspace.seat_limit = workspace_payload["seat_limit"]
        workspace.usage_limits = workspace_payload["usage_limits"]
        workspace.inference_config = _restore_workspace_inference_config(workspace_payload)
        workspace.updated_at = _parse_datetime(workspace_payload["updated_at"]) or datetime.now(UTC)

    entitlements_payload = payload["entitlements"]
    if entitlements_payload is not None:
        if workspace_created or workspace.entitlements is None:
            workspace.entitlements = WorkspaceEntitlement(workspace_id=workspace.id)
        for field_name in (
            "cloud_sync",
            "hosted_backups",
            "managed_inference",
            "hosted_evals",
            "invite_members",
            "shared_workspace",
            "approvals",
            "rbac",
            "sso",
            "audit_logs",
        ):
            setattr(workspace.entitlements, field_name, bool(entitlements_payload[field_name]))

    subscription_payload = payload["subscription"]
    if subscription_payload is not None:
        if workspace_created or workspace.subscription is None:
            workspace.subscription = WorkspaceSubscription(
                workspace_id=workspace.id,
                billing_provider=WorkspaceBillingProvider(subscription_payload["billing_provider"]),
                status=WorkspaceSubscriptionStatus(subscription_payload["status"]),
                plan_code=subscription_payload["plan_code"],
            )
        workspace.subscription.billing_provider = WorkspaceBillingProvider(
            subscription_payload["billing_provider"]
        )
        workspace.subscription.status = WorkspaceSubscriptionStatus(subscription_payload["status"])
        workspace.subscription.plan_code = subscription_payload["plan_code"]
        workspace.subscription.provider_customer_id = subscription_payload["provider_customer_id"]
        workspace.subscription.provider_subscription_id = subscription_payload[
            "provider_subscription_id"
        ]
        workspace.subscription.current_period_end = _parse_datetime(
            subscription_payload["current_period_end"]
        )
        workspace.subscription.trial_ends_at = _parse_datetime(
            subscription_payload["trial_ends_at"]
        )

    memberships_result = await db.execute(
        select(Membership).where(Membership.workspace_id == workspace.id)
    )
    for membership in memberships_result.scalars().all():
        await db.delete(membership)
    await db.flush()

    for membership_payload in payload["memberships"]:
        db.add(
            Membership(
                workspace_id=workspace.id,
                user_id=UUID(membership_payload["user_id"]),
                role=MembershipRole(membership_payload["role"]),
                created_at=_parse_datetime(membership_payload["created_at"]) or datetime.now(UTC),
                updated_at=_parse_datetime(membership_payload["updated_at"]) or datetime.now(UTC),
            )
        )
    await db.flush()

    await _delete_current_user_content(
        db,
        user.id,
        include_auth_artifacts=bool(private_payload),
    )
    await _restore_playbooks(db, user.id, account_export["playbooks"])
    await _restore_usage_records(db, user.id, account_export["usage_records"])
    if private_payload:
        await _restore_api_keys(db, user.id, private_payload.get("api_keys", []))
        await _restore_oauth_accounts(db, user.id, private_payload.get("oauth_accounts", []))

    backup.restored_at = datetime.now(UTC)
    await db.flush()
    return {
        "workspace_id": str(workspace.id),
        "backup_id": str(backup.id),
        "restored_playbooks": len(account_export["playbooks"]),
        "restored_usage_records": len(account_export["usage_records"]),
        "restored_api_keys": len(private_payload.get("api_keys", [])),
        "restored_oauth_accounts": len(private_payload.get("oauth_accounts", [])),
    }


__all__ = [
    "WORKSPACE_BACKUP_RETENTION_COUNT",
    "backup_hosted_personal_workspaces",
    "build_workspace_backup_payload",
    "create_workspace_backup_snapshot",
    "enforce_workspace_backup_retention",
    "get_restoreable_personal_workspace",
    "get_workspace_backup",
    "list_restoreable_personal_workspaces",
    "list_workspace_backups",
    "restore_workspace_backup",
]
