"""Playbook import/export services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ace_core.portability import (
    PortableBundleOrigin,
    PortablePlaybook,
    PortablePlaybookBundle,
    PortablePlaybookVersion,
    PortableScope,
    PortableTrace,
)
from ace_platform.config import get_settings
from ace_platform.core.limits import (
    get_effective_tier_for_limits,
    get_tier_limits,
    is_user_trialing,
)
from ace_platform.core.playbook_matching import refresh_playbook_embedding
from ace_platform.core.playbook_reviews import build_review_event, derive_review_status
from ace_platform.core.workspaces import resolve_workspace_permissions
from ace_platform.db.models import (
    Outcome,
    OutcomeStatus,
    Playbook,
    PlaybookReviewAction,
    PlaybookReviewStatus,
    PlaybookSource,
    PlaybookStatus,
    PlaybookVersion,
    User,
    Workspace,
    WorkspaceMembership,
    WorkspacePlan,
)


@dataclass(slots=True)
class PlaybookImportSummary:
    """Summary of one imported playbook."""

    playbook_id: UUID
    version_count: int
    trace_count: int


@dataclass(slots=True)
class AccessiblePlaybookSummary:
    """One playbook visible through ownership or a shared team workspace."""

    playbook: Playbook
    owner_email: str | None
    shared_workspace_names: tuple[str, ...]
    is_owned_by_current_user: bool


class PlaybookImportLimitError(ValueError):
    """Raised when a bundle import would exceed the caller's plan limits."""


class PlaybookLimitError(ValueError):
    """Raised when creating or reusing a playbook would exceed plan limits."""


async def export_playbook_bundle(
    db: AsyncSession,
    user_id: UUID,
    *,
    api_url: str | None = None,
) -> PortablePlaybookBundle:
    """Export the user's playbooks into the portable bundle format."""

    result = await db.execute(
        select(Playbook)
        .where(Playbook.user_id == user_id)
        .options(selectinload(Playbook.versions), selectinload(Playbook.outcomes))
        .order_by(Playbook.created_at.asc())
    )
    playbooks = result.scalars().all()

    portable_playbooks: list[PortablePlaybook] = []
    for playbook in playbooks:
        review_status = getattr(playbook, "review_status", PlaybookReviewStatus.DRAFT)
        review_status_updated_at = getattr(playbook, "review_status_updated_at", None)
        review_history = list(getattr(playbook, "review_history", []) or [])
        review_status_value = (
            review_status.value
            if isinstance(review_status, PlaybookReviewStatus)
            else review_status
        )
        versions = [
            PortablePlaybookVersion(
                id=str(version.id),
                version_number=version.version_number,
                content=version.content,
                bullet_count=version.bullet_count,
                diff_summary=version.diff_summary,
                created_at=version.created_at,
            )
            for version in sorted(playbook.versions, key=lambda version: version.version_number)
        ]
        current_version_id = (
            str(playbook.current_version_id) if playbook.current_version_id is not None else None
        )
        current_version_number = None
        if current_version_id is not None:
            for version in versions:
                if version.id == current_version_id:
                    current_version_number = version.version_number
                    break

        portable_playbooks.append(
            PortablePlaybook(
                id=str(playbook.id),
                name=playbook.name,
                description=playbook.description,
                status=playbook.status.value,
                source=playbook.source.value,
                scope=PortableScope(kind="user", id=str(user_id)),
                current_version_id=current_version_id,
                current_version_number=current_version_number,
                versions=versions,
                traces=[
                    PortableTrace(
                        id=str(outcome.id),
                        task_description=outcome.task_description,
                        outcome=outcome.outcome_status.value,
                        notes=outcome.notes,
                        reasoning_trace=outcome.reasoning_trace,
                        created_at=outcome.created_at,
                        processed_at=outcome.processed_at,
                    )
                    for outcome in sorted(playbook.outcomes, key=lambda outcome: outcome.created_at)
                ],
                created_at=playbook.created_at,
                updated_at=playbook.updated_at,
                metadata={
                    "source_playbook_id": str(playbook.id),
                    "review_status": review_status_value,
                    "review_status_updated_at": review_status_updated_at.isoformat()
                    if review_status_updated_at
                    else None,
                    "review_history": review_history,
                },
            )
        )

    return PortablePlaybookBundle(
        exported_at=datetime.now(UTC),
        origin=PortableBundleOrigin(
            system="ace-platform",
            context="hosted",
            api_url=api_url,
            metadata={"user_id": str(user_id)},
        ),
        playbooks=portable_playbooks,
    )


async def import_playbook_bundle(
    db: AsyncSession,
    user: User,
    bundle: PortablePlaybookBundle,
) -> list[PlaybookImportSummary]:
    """Import a portable playbook bundle into the hosted store."""

    await _enforce_import_limit(db, user, bundle)

    imported: list[PlaybookImportSummary] = []
    settings = get_settings()

    for portable_playbook in bundle.playbooks:
        metadata = portable_playbook.metadata or {}
        lifecycle_status = PlaybookStatus(portable_playbook.status)
        review_status = derive_review_status(
            metadata=metadata,
            lifecycle_status=lifecycle_status,
        )
        review_status_updated_at = metadata.get("review_status_updated_at")
        review_history = list(metadata.get("review_history") or [])
        if not review_history:
            review_history = [
                build_review_event(
                    actor=user,
                    action=PlaybookReviewAction.CREATED,
                    from_status=None,
                    to_status=review_status,
                    created_at=portable_playbook.created_at,
                )
            ]

        playbook_kwargs = {
            "user_id": user.id,
            "name": portable_playbook.name,
            "description": portable_playbook.description,
            "status": lifecycle_status,
            "review_status": review_status,
            "review_history": review_history,
            "source": PlaybookSource.IMPORTED,
        }
        if portable_playbook.created_at is not None:
            playbook_kwargs["created_at"] = portable_playbook.created_at
        if portable_playbook.updated_at is not None:
            playbook_kwargs["updated_at"] = portable_playbook.updated_at
        if review_status_updated_at:
            playbook_kwargs["review_status_updated_at"] = datetime.fromisoformat(
                review_status_updated_at
            )

        playbook = Playbook(**playbook_kwargs)
        db.add(playbook)
        await db.flush()

        imported_version_ids: dict[str, UUID] = {}
        latest_imported_version_id: UUID | None = None
        current_version_content: str | None = None
        imported_versions = sorted(
            portable_playbook.versions,
            key=lambda version: version.version_number,
        )
        for portable_version in imported_versions:
            version_kwargs = {
                "playbook_id": playbook.id,
                "version_number": portable_version.version_number,
                "content": portable_version.content,
                "bullet_count": portable_version.bullet_count,
                "diff_summary": portable_version.diff_summary,
            }
            if portable_version.created_at is not None:
                version_kwargs["created_at"] = portable_version.created_at

            version = PlaybookVersion(**version_kwargs)
            db.add(version)
            await db.flush()
            latest_imported_version_id = version.id
            if portable_version.id is not None:
                imported_version_ids[portable_version.id] = version.id
            if portable_playbook.current_version_number == portable_version.version_number:
                playbook.current_version_id = version.id
                current_version_content = portable_version.content

        if playbook.current_version_id is None and portable_playbook.current_version_id is not None:
            playbook.current_version_id = imported_version_ids.get(
                portable_playbook.current_version_id
            )
            if playbook.current_version_id is not None:
                for portable_version in imported_versions:
                    if portable_version.id == portable_playbook.current_version_id:
                        current_version_content = portable_version.content
                        break

        if playbook.current_version_id is None:
            playbook.current_version_id = latest_imported_version_id
            if current_version_content is None and imported_versions:
                current_version_content = imported_versions[-1].content

        await refresh_playbook_embedding(
            playbook,
            content=current_version_content,
            settings=settings,
        )

        for portable_trace in portable_playbook.traces:
            trace_kwargs = {
                "playbook_id": playbook.id,
                "task_description": portable_trace.task_description,
                "outcome_status": OutcomeStatus(portable_trace.outcome),
                "notes": portable_trace.notes,
                "reasoning_trace": portable_trace.reasoning_trace,
            }
            if portable_trace.created_at is not None:
                trace_kwargs["created_at"] = portable_trace.created_at
            if portable_trace.processed_at is not None:
                trace_kwargs["processed_at"] = portable_trace.processed_at

            trace = Outcome(**trace_kwargs)
            db.add(trace)

        imported.append(
            PlaybookImportSummary(
                playbook_id=playbook.id,
                version_count=len(portable_playbook.versions),
                trace_count=len(portable_playbook.traces),
            )
        )

    await db.commit()
    return imported


async def list_shared_workspace_playbooks(
    db: AsyncSession,
    workspace: Workspace,
    *,
    current_user_id: UUID,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Playbook], int]:
    """List approved shared playbooks visible inside one workspace."""

    if workspace.plan == WorkspacePlan.PERSONAL:
        return [], 0

    base_query = (
        select(Playbook)
        .join(WorkspaceMembership, WorkspaceMembership.user_id == Playbook.user_id)
        .where(
            WorkspaceMembership.workspace_id == workspace.id,
            Playbook.status == PlaybookStatus.ACTIVE,
            Playbook.review_status == PlaybookReviewStatus.APPROVED,
        )
    )

    total = int(await db.scalar(select(func.count()).select_from(base_query.subquery())) or 0)
    offset = (page - 1) * page_size
    query = (
        base_query.options(
            selectinload(Playbook.user),
            selectinload(Playbook.current_version),
            selectinload(Playbook.versions),
            selectinload(Playbook.outcomes),
        )
        .order_by(
            Playbook.user_id == current_user_id,
            Playbook.updated_at.desc(),
            Playbook.created_at.desc(),
        )
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(query)
    return _scalar_result_items(result, unique=True), total


async def reuse_shared_workspace_playbook(
    db: AsyncSession,
    workspace: Workspace,
    *,
    current_user: User,
    source_playbook_id: UUID,
) -> Playbook:
    """Copy a shared workspace playbook into the caller's own playbooks."""

    source_playbook = await _get_shared_workspace_playbook(
        db,
        workspace,
        playbook_id=source_playbook_id,
    )
    if source_playbook is None:
        raise LookupError("Shared playbook not found")
    if source_playbook.user_id == current_user.id:
        raise ValueError("You already own this playbook.")

    await _enforce_owned_playbook_limit(db, current_user, action="reuse")

    copied_playbook = Playbook(
        user_id=current_user.id,
        name=source_playbook.name,
        description=source_playbook.description,
        status=PlaybookStatus.ACTIVE,
        source=PlaybookSource.IMPORTED,
    )
    db.add(copied_playbook)
    await db.flush()

    copied_version = None
    if source_playbook.current_version is not None:
        copied_version = PlaybookVersion(
            playbook_id=copied_playbook.id,
            version_number=1,
            content=source_playbook.current_version.content,
            bullet_count=source_playbook.current_version.bullet_count,
            diff_summary=source_playbook.current_version.diff_summary,
        )
        db.add(copied_version)
        await db.flush()
        copied_playbook.current_version_id = copied_version.id

    await refresh_playbook_embedding(
        copied_playbook,
        content=copied_version.content if copied_version is not None else None,
    )
    await db.flush()
    return copied_playbook


async def _enforce_import_limit(
    db: AsyncSession,
    user: User,
    bundle: PortablePlaybookBundle,
) -> None:
    import_count = len(bundle.playbooks)
    if import_count == 0:
        return

    effective_tier = get_effective_tier_for_limits(user)
    limits = get_tier_limits(effective_tier)
    if limits.max_playbooks is None:
        return

    existing_playbook_count = await db.scalar(
        select(func.count()).select_from(
            select(Playbook).where(Playbook.user_id == user.id).subquery()
        )
    )
    existing_playbook_count = int(existing_playbook_count or 0)

    if existing_playbook_count + import_count <= limits.max_playbooks:
        return

    if is_user_trialing(user):
        raise PlaybookImportLimitError(
            f"Importing {import_count} playbook(s) would exceed the maximum of "
            f"{limits.max_playbooks} playbook(s) included in your free trial. "
            "Subscribe to a paid plan to import more playbooks. Visit your account "
            "settings to view plans and upgrade."
        )

    raise PlaybookImportLimitError(
        f"Importing {import_count} playbook(s) would exceed the maximum number of "
        f"playbooks ({limits.max_playbooks}) for your {effective_tier.value} "
        "subscription. Please upgrade to import more playbooks."
    )


async def _get_shared_workspace_playbook(
    db: AsyncSession,
    workspace: Workspace,
    *,
    playbook_id: UUID,
) -> Playbook | None:
    result = await db.execute(
        select(Playbook)
        .join(WorkspaceMembership, WorkspaceMembership.user_id == Playbook.user_id)
        .where(
            WorkspaceMembership.workspace_id == workspace.id,
            Playbook.id == playbook_id,
            Playbook.status == PlaybookStatus.ACTIVE,
            Playbook.review_status == PlaybookReviewStatus.APPROVED,
        )
        .options(
            selectinload(Playbook.user),
            selectinload(Playbook.current_version),
            selectinload(Playbook.versions),
            selectinload(Playbook.outcomes),
        )
    )
    items = _scalar_result_items(result, unique=True)
    if not items:
        return None
    return items[0]


async def get_playbook_with_review_access(
    db: AsyncSession,
    *,
    playbook_id: UUID,
    current_user: User,
) -> Playbook | None:
    """Return a playbook the caller can review as owner or shared-workspace approver."""

    playbook_result = await db.execute(
        select(Playbook)
        .where(Playbook.id == playbook_id)
        .options(selectinload(Playbook.current_version))
    )
    playbook = playbook_result.scalar_one_or_none()
    if playbook is None:
        return None

    if playbook.user_id == current_user.id:
        return playbook

    membership_result = await db.execute(
        select(Workspace, WorkspaceMembership.role)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(
            WorkspaceMembership.user_id == current_user.id,
            Workspace.plan != WorkspacePlan.PERSONAL,
            Workspace.id.in_(
                select(WorkspaceMembership.workspace_id).where(
                    WorkspaceMembership.user_id == playbook.user_id
                )
            ),
        )
        .options(selectinload(Workspace.entitlements))
    )
    for workspace, role in membership_result.all():
        permissions = resolve_workspace_permissions(workspace, role)
        if permissions.can_approve_playbooks:
            return playbook

    return None


async def list_accessible_playbooks(
    db: AsyncSession,
    *,
    user_id: UUID,
) -> list[AccessiblePlaybookSummary]:
    """List playbooks the user can access directly or through a shared workspace."""

    owned_result = await db.execute(
        select(Playbook)
        .where(Playbook.user_id == user_id)
        .options(selectinload(Playbook.user), selectinload(Playbook.current_version))
        .order_by(Playbook.created_at.desc())
    )
    visible: dict[UUID, AccessiblePlaybookSummary] = {}
    for playbook in _scalar_result_items(owned_result):
        visible[playbook.id] = AccessiblePlaybookSummary(
            playbook=playbook,
            owner_email=playbook.user.email if playbook.user is not None else None,
            shared_workspace_names=(),
            is_owned_by_current_user=True,
        )

    workspace_result = await db.execute(
        select(Workspace)
        .join(WorkspaceMembership)
        .where(
            WorkspaceMembership.user_id == user_id,
            Workspace.plan != WorkspacePlan.PERSONAL,
        )
        .options(selectinload(Workspace.entitlements))
        .order_by(Workspace.created_at.asc(), Workspace.id.asc())
    )
    workspaces = [
        workspace
        for workspace in _scalar_result_items(workspace_result)
        if isinstance(workspace, Workspace)
    ]
    if workspaces and not isinstance(workspaces[0], Workspace):
        return list(visible.values())

    for workspace in workspaces:
        if workspace.entitlements is not None and not workspace.entitlements.shared_workspace:
            continue

        shared_playbooks, _ = await list_shared_workspace_playbooks(
            db,
            workspace,
            current_user_id=user_id,
            page=1,
            page_size=500,
        )
        for playbook in shared_playbooks:
            existing = visible.get(playbook.id)
            if existing is None:
                visible[playbook.id] = AccessiblePlaybookSummary(
                    playbook=playbook,
                    owner_email=playbook.user.email if playbook.user is not None else None,
                    shared_workspace_names=(workspace.name,),
                    is_owned_by_current_user=playbook.user_id == user_id,
                )
                continue

            if workspace.name not in existing.shared_workspace_names:
                visible[playbook.id] = AccessiblePlaybookSummary(
                    playbook=existing.playbook,
                    owner_email=existing.owner_email,
                    shared_workspace_names=existing.shared_workspace_names + (workspace.name,),
                    is_owned_by_current_user=existing.is_owned_by_current_user,
                )

    return list(visible.values())


async def get_accessible_playbook(
    db: AsyncSession,
    *,
    user_id: UUID,
    playbook_id: UUID,
) -> AccessiblePlaybookSummary | None:
    """Fetch one accessible playbook by id."""

    for summary in await list_accessible_playbooks(db, user_id=user_id):
        if summary.playbook.id == playbook_id:
            return summary
    return None


async def _enforce_owned_playbook_limit(
    db: AsyncSession,
    user: User,
    *,
    action: str,
) -> None:
    effective_tier = get_effective_tier_for_limits(user)
    limits = get_tier_limits(effective_tier)
    if limits.max_playbooks is None:
        return

    existing_playbook_count = await db.scalar(
        select(func.count()).select_from(
            select(Playbook).where(Playbook.user_id == user.id).subquery()
        )
    )
    existing_playbook_count = int(existing_playbook_count or 0)
    if existing_playbook_count < limits.max_playbooks:
        return

    if is_user_trialing(user):
        raise PlaybookLimitError(
            f"You've reached the maximum of {limits.max_playbooks} playbook(s) "
            f"included in your free trial. Subscribe to a paid plan to {action} more "
            "playbooks. Visit your account settings to view plans and upgrade."
        )

    raise PlaybookLimitError(
        f"You have reached the maximum number of playbooks ({limits.max_playbooks}) "
        f"for your {effective_tier.value} subscription. Please upgrade to {action} more playbooks."
    )


def _scalar_result_items(result, *, unique: bool = False) -> list:
    """Return scalar items from SQLAlchemy results or lightweight test doubles."""

    scalars = result.scalars()
    if unique and hasattr(scalars, "unique"):
        scalars = scalars.unique()
    return list(scalars.all())


__all__ = [
    "AccessiblePlaybookSummary",
    "PlaybookImportLimitError",
    "PlaybookImportSummary",
    "PlaybookLimitError",
    "export_playbook_bundle",
    "get_playbook_with_review_access",
    "get_accessible_playbook",
    "import_playbook_bundle",
    "list_accessible_playbooks",
    "list_shared_workspace_playbooks",
    "reuse_shared_workspace_playbook",
]
