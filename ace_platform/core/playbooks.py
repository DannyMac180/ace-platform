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
from ace_platform.db.models import (
    Outcome,
    OutcomeStatus,
    Playbook,
    PlaybookSource,
    PlaybookStatus,
    PlaybookVersion,
    User,
)


@dataclass(slots=True)
class PlaybookImportSummary:
    """Summary of one imported playbook."""

    playbook_id: UUID
    version_count: int
    trace_count: int


class PlaybookImportLimitError(ValueError):
    """Raised when a bundle import would exceed the caller's plan limits."""


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
                metadata={"source_playbook_id": str(playbook.id)},
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
        playbook_kwargs = {
            "user_id": user.id,
            "name": portable_playbook.name,
            "description": portable_playbook.description,
            "status": PlaybookStatus(portable_playbook.status),
            "source": PlaybookSource.IMPORTED,
        }
        if portable_playbook.created_at is not None:
            playbook_kwargs["created_at"] = portable_playbook.created_at
        if portable_playbook.updated_at is not None:
            playbook_kwargs["updated_at"] = portable_playbook.updated_at

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

        if current_version_content is not None:
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


__all__ = [
    "PlaybookImportLimitError",
    "PlaybookImportSummary",
    "export_playbook_bundle",
    "import_playbook_bundle",
]
