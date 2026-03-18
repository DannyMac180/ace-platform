"""Workspace-scoped cloud sync helpers for hosted personal workspaces."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ace_core.portability import (
    PortablePlaybook,
    PortablePlaybookVersion,
    PortableScope,
    PortableTrace,
)
from ace_platform.core.playbook_matching import refresh_playbook_embedding
from ace_platform.db.models import (
    Outcome,
    OutcomeStatus,
    Playbook,
    PlaybookSource,
    PlaybookStatus,
    PlaybookVersion,
    Workspace,
    WorkspaceDeploymentMode,
    WorkspacePlan,
    WorkspaceSyncTombstone,
)

SYNC_ENTITY_PLAYBOOK = "playbook"


@dataclass(slots=True, frozen=True)
class SyncCursorToken:
    """Opaque cursor token materialized into a sortable tuple."""

    occurred_at: datetime
    entity_type: str
    entity_id: str


@dataclass(slots=True)
class HostedSyncEvent:
    """Concrete server sync event returned by pull and push flows."""

    id: str
    entity_type: str
    entity_id: str
    operation: str
    occurred_at: datetime
    payload: PortablePlaybook | None = None

    @property
    def cursor_token(self) -> SyncCursorToken:
        return SyncCursorToken(
            occurred_at=self.occurred_at,
            entity_type=self.entity_type,
            entity_id=self.entity_id,
        )


@dataclass(slots=True)
class WorkspaceSyncConflictError(Exception):
    """Raised when a pushed mutation is stale relative to server state."""

    event_id: str
    entity_type: str
    entity_id: str
    message: str
    server_event: HostedSyncEvent | None = None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def encode_sync_cursor(token: SyncCursorToken | None) -> str | None:
    """Encode a cursor token into a stable string."""

    if token is None:
        return None
    return f"{_as_utc(token.occurred_at).isoformat()}|{token.entity_type}|{token.entity_id}"


def decode_sync_cursor(cursor: str | None) -> SyncCursorToken | None:
    """Decode a cursor string produced by `encode_sync_cursor`."""

    if not cursor:
        return None

    occurred_at, entity_type, entity_id = cursor.split("|", 2)
    return SyncCursorToken(
        occurred_at=_as_utc(datetime.fromisoformat(occurred_at)),
        entity_type=entity_type,
        entity_id=entity_id,
    )


def _cursor_key(token: SyncCursorToken) -> tuple[datetime, str, str]:
    return (_as_utc(token.occurred_at), token.entity_type, token.entity_id)


def _event_sort_key(event: HostedSyncEvent) -> tuple[datetime, str, str]:
    return _cursor_key(event.cursor_token)


def _is_after_cursor(token: SyncCursorToken, cursor: SyncCursorToken | None) -> bool:
    if cursor is None:
        return True
    return _cursor_key(token) > _cursor_key(cursor)


def ensure_personal_sync_workspace(workspace: Workspace) -> UUID:
    """Validate that the workspace is in-scope for single-user cloud sync."""

    if workspace.plan != WorkspacePlan.PERSONAL:
        raise ValueError("Cloud sync currently supports personal workspaces only.")
    if workspace.deployment_mode != WorkspaceDeploymentMode.CLOUD:
        raise ValueError("Cloud sync requires a hosted cloud workspace.")
    if len(workspace.memberships) != 1:
        raise ValueError("Cloud sync currently supports single-user workspaces only.")
    if workspace.entitlements is None or not workspace.entitlements.cloud_sync:
        raise ValueError("Cloud sync is not enabled for this workspace.")
    return workspace.memberships[0].user_id


def compute_playbook_sync_updated_at(playbook: Playbook) -> datetime:
    """Return the authoritative server timestamp for a playbook sync snapshot."""

    timestamps = [_as_utc(playbook.created_at), _as_utc(playbook.updated_at)]
    timestamps.extend(_as_utc(version.created_at) for version in playbook.versions)
    timestamps.extend(_as_utc(outcome.updated_at) for outcome in playbook.outcomes)
    return max(timestamps)


def serialize_playbook_snapshot(playbook: Playbook, workspace: Workspace) -> PortablePlaybook:
    """Serialize one playbook into the hosted sync payload shape."""

    versions = [
        PortablePlaybookVersion(
            id=str(version.id),
            version_number=version.version_number,
            content=version.content,
            bullet_count=version.bullet_count,
            diff_summary=version.diff_summary,
            created_at=version.created_at,
        )
        for version in sorted(playbook.versions, key=lambda item: item.version_number)
    ]

    traces = [
        PortableTrace(
            id=str(outcome.id),
            task_description=outcome.task_description,
            outcome=outcome.outcome_status.value,
            notes=outcome.notes,
            reasoning_trace=outcome.reasoning_trace,
            created_at=outcome.created_at,
            processed_at=outcome.processed_at,
        )
        for outcome in sorted(
            playbook.outcomes,
            key=lambda item: (_as_utc(item.created_at), str(item.id)),
        )
    ]

    current_version_id = str(playbook.current_version_id) if playbook.current_version_id else None
    current_version_number = (
        playbook.current_version.version_number if playbook.current_version else None
    )

    return PortablePlaybook(
        id=str(playbook.id),
        name=playbook.name,
        description=playbook.description,
        status=playbook.status.value,
        source=playbook.source.value,
        scope=PortableScope(kind="workspace", id=str(workspace.id)),
        current_version_id=current_version_id,
        current_version_number=current_version_number,
        versions=versions,
        traces=traces,
        created_at=playbook.created_at,
        updated_at=compute_playbook_sync_updated_at(playbook),
        metadata={"workspace_id": str(workspace.id)},
    )


def build_playbook_sync_event(playbook: Playbook, workspace: Workspace) -> HostedSyncEvent:
    """Build an upsert event for one current server playbook snapshot."""

    occurred_at = compute_playbook_sync_updated_at(playbook)
    entity_id = str(playbook.id)
    return HostedSyncEvent(
        id=f"{SYNC_ENTITY_PLAYBOOK}:{entity_id}:{_as_utc(occurred_at).isoformat()}",
        entity_type=SYNC_ENTITY_PLAYBOOK,
        entity_id=entity_id,
        operation="upsert",
        occurred_at=occurred_at,
        payload=serialize_playbook_snapshot(playbook, workspace),
    )


def build_tombstone_sync_event(tombstone: WorkspaceSyncTombstone) -> HostedSyncEvent:
    """Build a delete event from a stored tombstone."""

    occurred_at = _as_utc(tombstone.deleted_at)
    entity_id = str(tombstone.entity_id)
    return HostedSyncEvent(
        id=f"{SYNC_ENTITY_PLAYBOOK}:{entity_id}:delete:{occurred_at.isoformat()}",
        entity_type=tombstone.entity_type,
        entity_id=entity_id,
        operation="delete",
        occurred_at=occurred_at,
        payload=None,
    )


async def record_playbook_tombstone(
    db: AsyncSession,
    workspace_id: UUID,
    playbook_id: UUID,
    *,
    deleted_at: datetime | None = None,
) -> WorkspaceSyncTombstone:
    """Create or update a playbook deletion tombstone."""

    resolved_deleted_at = _as_utc(deleted_at or datetime.now(UTC))
    tombstone = await db.get(
        WorkspaceSyncTombstone,
        (workspace_id, SYNC_ENTITY_PLAYBOOK, playbook_id),
    )
    if tombstone is None:
        tombstone = WorkspaceSyncTombstone(
            workspace_id=workspace_id,
            entity_type=SYNC_ENTITY_PLAYBOOK,
            entity_id=playbook_id,
            deleted_at=resolved_deleted_at,
        )
        db.add(tombstone)
    else:
        tombstone.deleted_at = resolved_deleted_at

    await db.flush()
    return tombstone


async def clear_playbook_tombstone(
    db: AsyncSession,
    workspace_id: UUID,
    playbook_id: UUID,
) -> None:
    """Remove a tombstone once the playbook exists again."""

    tombstone = await db.get(
        WorkspaceSyncTombstone,
        (workspace_id, SYNC_ENTITY_PLAYBOOK, playbook_id),
    )
    if tombstone is not None:
        await db.delete(tombstone)
        await db.flush()


async def list_workspace_sync_events(
    db: AsyncSession,
    workspace: Workspace,
    *,
    cursor: str | None = None,
) -> tuple[list[HostedSyncEvent], str | None]:
    """Return current hosted sync events for a personal workspace."""

    owner_user_id = ensure_personal_sync_workspace(workspace)
    parsed_cursor = decode_sync_cursor(cursor)

    playbook_result = await db.execute(
        select(Playbook)
        .where(Playbook.user_id == owner_user_id)
        .options(
            selectinload(Playbook.current_version),
            selectinload(Playbook.versions),
            selectinload(Playbook.outcomes),
        )
        .order_by(Playbook.created_at.asc(), Playbook.id.asc())
    )
    playbooks = list(playbook_result.scalars().unique().all())

    tombstone_result = await db.execute(
        select(WorkspaceSyncTombstone)
        .where(WorkspaceSyncTombstone.workspace_id == workspace.id)
        .order_by(WorkspaceSyncTombstone.deleted_at.asc(), WorkspaceSyncTombstone.entity_id.asc())
    )
    tombstones = list(tombstone_result.scalars().all())

    events: list[HostedSyncEvent] = []
    for playbook in playbooks:
        event = build_playbook_sync_event(playbook, workspace)
        if _is_after_cursor(event.cursor_token, parsed_cursor):
            events.append(event)

    for tombstone in tombstones:
        event = build_tombstone_sync_event(tombstone)
        if _is_after_cursor(event.cursor_token, parsed_cursor):
            events.append(event)

    events.sort(key=_event_sort_key)
    next_cursor = encode_sync_cursor(events[-1].cursor_token) if events else cursor
    return events, next_cursor


async def load_workspace_playbook(
    db: AsyncSession,
    *,
    owner_user_id: UUID,
    playbook_id: UUID,
) -> Playbook | None:
    """Load one user-owned playbook with sync-relevant relationships."""

    result = await db.execute(
        select(Playbook)
        .where(Playbook.id == playbook_id, Playbook.user_id == owner_user_id)
        .options(
            selectinload(Playbook.current_version),
            selectinload(Playbook.versions),
            selectinload(Playbook.outcomes),
        )
    )
    return result.scalars().unique().one_or_none()


def _parse_uuid(value: str | None, *, field_name: str) -> UUID:
    if not value:
        raise ValueError(f"{field_name} is required")
    return UUID(value)


def _portable_version_fingerprint(version: PortablePlaybookVersion) -> dict[str, Any]:
    return {
        "version_number": version.version_number,
        "content": version.content,
        "bullet_count": version.bullet_count,
        "diff_summary": version.diff_summary,
    }


def _portable_trace_fingerprint(trace: PortableTrace) -> dict[str, Any]:
    return {
        "id": trace.id,
        "task_description": trace.task_description,
        "outcome": trace.outcome,
        "notes": trace.notes,
        "reasoning_trace": trace.reasoning_trace,
        "processed_at": _as_utc(trace.processed_at).isoformat() if trace.processed_at else None,
    }


def _portable_playbook_fingerprint(playbook: PortablePlaybook) -> dict[str, Any]:
    return {
        "id": playbook.id,
        "name": playbook.name,
        "description": playbook.description,
        "status": playbook.status,
        "current_version_number": playbook.current_version_number,
        "versions": [
            _portable_version_fingerprint(version)
            for version in sorted(playbook.versions, key=lambda item: item.version_number)
        ],
        "traces": [
            _portable_trace_fingerprint(trace)
            for trace in sorted(
                playbook.traces,
                key=lambda item: (
                    _as_utc(item.created_at).isoformat() if item.created_at else "",
                    item.id or "",
                    item.task_description,
                ),
            )
        ],
    }


def is_retry_of_current_playbook_state(
    current_event: HostedSyncEvent | None,
    incoming_payload: PortablePlaybook,
) -> bool:
    """Return whether an incoming playbook upsert already matches server state."""

    if (
        current_event is None
        or current_event.operation != "upsert"
        or current_event.payload is None
    ):
        return False
    return _portable_playbook_fingerprint(current_event.payload) == _portable_playbook_fingerprint(
        incoming_payload
    )


async def _build_current_server_event(
    db: AsyncSession,
    workspace: Workspace,
    owner_user_id: UUID,
    playbook_id: UUID,
) -> HostedSyncEvent | None:
    playbook = await load_workspace_playbook(
        db, owner_user_id=owner_user_id, playbook_id=playbook_id
    )
    if playbook is not None:
        return build_playbook_sync_event(playbook, workspace)

    tombstone = await db.get(
        WorkspaceSyncTombstone,
        (workspace.id, SYNC_ENTITY_PLAYBOOK, playbook_id),
    )
    if tombstone is not None:
        return build_tombstone_sync_event(tombstone)
    return None


async def _assert_playbook_base_is_current(
    db: AsyncSession,
    workspace: Workspace,
    owner_user_id: UUID,
    *,
    event_id: str,
    playbook_id: UUID,
    base_updated_at: datetime | None,
) -> None:
    playbook = await load_workspace_playbook(
        db, owner_user_id=owner_user_id, playbook_id=playbook_id
    )
    if playbook is not None:
        current_updated_at = compute_playbook_sync_updated_at(playbook)
        if base_updated_at is None:
            raise WorkspaceSyncConflictError(
                event_id=event_id,
                entity_type=SYNC_ENTITY_PLAYBOOK,
                entity_id=str(playbook_id),
                message="base_updated_at is required to update an existing synced playbook.",
                server_event=build_playbook_sync_event(playbook, workspace),
            )
        if current_updated_at > _as_utc(base_updated_at):
            raise WorkspaceSyncConflictError(
                event_id=event_id,
                entity_type=SYNC_ENTITY_PLAYBOOK,
                entity_id=str(playbook_id),
                message="The server has a newer playbook snapshot than this client mutation.",
                server_event=build_playbook_sync_event(playbook, workspace),
            )

    tombstone = await db.get(
        WorkspaceSyncTombstone,
        (workspace.id, SYNC_ENTITY_PLAYBOOK, playbook_id),
    )
    if tombstone is not None:
        if base_updated_at is None or _as_utc(base_updated_at) < _as_utc(tombstone.deleted_at):
            raise WorkspaceSyncConflictError(
                event_id=event_id,
                entity_type=SYNC_ENTITY_PLAYBOOK,
                entity_id=str(playbook_id),
                message="The server has already deleted this playbook more recently.",
                server_event=build_tombstone_sync_event(tombstone),
            )


async def apply_playbook_sync_upsert(
    db: AsyncSession,
    workspace: Workspace,
    *,
    event_id: str,
    entity_id: str,
    payload: PortablePlaybook,
    base_updated_at: datetime | None,
) -> HostedSyncEvent:
    """Apply a pushed playbook snapshot into the hosted store."""

    owner_user_id = ensure_personal_sync_workspace(workspace)
    playbook_id = _parse_uuid(payload.id or entity_id, field_name="payload.id")
    if entity_id != str(playbook_id):
        raise ValueError("entity_id must match payload.id for playbook sync.")

    current_server_event = await _build_current_server_event(
        db, workspace, owner_user_id, playbook_id
    )
    if is_retry_of_current_playbook_state(current_server_event, payload):
        return current_server_event

    await _assert_playbook_base_is_current(
        db,
        workspace,
        owner_user_id,
        event_id=event_id,
        playbook_id=playbook_id,
        base_updated_at=base_updated_at,
    )

    playbook = await load_workspace_playbook(
        db, owner_user_id=owner_user_id, playbook_id=playbook_id
    )
    playbook_was_created = playbook is None
    if playbook is None:
        playbook_kwargs = {
            "id": playbook_id,
            "user_id": owner_user_id,
            "name": payload.name,
            "description": payload.description,
            "status": PlaybookStatus(payload.status),
            "source": PlaybookSource(payload.source or PlaybookSource.USER_CREATED.value),
        }
        if payload.created_at is not None:
            playbook_kwargs["created_at"] = payload.created_at
        playbook = Playbook(**playbook_kwargs)
        db.add(playbook)
        await db.flush()
    else:
        playbook.name = payload.name
        playbook.description = payload.description
        playbook.status = PlaybookStatus(payload.status)
        playbook.source = PlaybookSource(payload.source or playbook.source.value)

    await clear_playbook_tombstone(db, workspace.id, playbook_id)

    existing_versions = [] if playbook_was_created else list(playbook.versions)
    versions_by_number = {version.version_number: version for version in existing_versions}
    versions_by_id = {str(version.id): version for version in existing_versions}
    for portable_version in sorted(payload.versions, key=lambda item: item.version_number):
        version = None
        if portable_version.id is not None:
            version = versions_by_id.get(portable_version.id)
        if version is None:
            version = versions_by_number.get(portable_version.version_number)

        if version is None:
            version_kwargs = {
                "playbook_id": playbook.id,
                "version_number": portable_version.version_number,
                "content": portable_version.content,
                "bullet_count": portable_version.bullet_count,
                "diff_summary": portable_version.diff_summary,
            }
            if portable_version.id is not None:
                version_kwargs["id"] = _parse_uuid(portable_version.id, field_name="version.id")
            if portable_version.created_at is not None:
                version_kwargs["created_at"] = portable_version.created_at
            version = PlaybookVersion(**version_kwargs)
            db.add(version)
            await db.flush()
            if not playbook_was_created:
                playbook.versions.append(version)

        version.content = portable_version.content
        version.bullet_count = portable_version.bullet_count
        version.diff_summary = portable_version.diff_summary
        versions_by_number[version.version_number] = version
        versions_by_id[str(version.id)] = version

    existing_outcomes = [] if playbook_was_created else list(playbook.outcomes)
    outcomes_by_id = {str(outcome.id): outcome for outcome in existing_outcomes}
    for portable_trace in payload.traces:
        trace_id = _parse_uuid(portable_trace.id, field_name="trace.id")
        outcome = outcomes_by_id.get(str(trace_id))
        if outcome is None:
            outcome_kwargs = {
                "id": trace_id,
                "playbook_id": playbook.id,
                "task_description": portable_trace.task_description,
                "outcome_status": OutcomeStatus(portable_trace.outcome),
                "notes": portable_trace.notes,
                "reasoning_trace": portable_trace.reasoning_trace,
            }
            if portable_trace.created_at is not None:
                outcome_kwargs["created_at"] = portable_trace.created_at
            if portable_trace.processed_at is not None:
                outcome_kwargs["processed_at"] = portable_trace.processed_at
            outcome = Outcome(**outcome_kwargs)
            db.add(outcome)
            await db.flush()
            if not playbook_was_created:
                playbook.outcomes.append(outcome)
            outcomes_by_id[str(trace_id)] = outcome
            continue

        outcome.task_description = portable_trace.task_description
        outcome.outcome_status = OutcomeStatus(portable_trace.outcome)
        outcome.notes = portable_trace.notes
        outcome.reasoning_trace = portable_trace.reasoning_trace
        outcome.processed_at = portable_trace.processed_at

    current_version = None
    if payload.current_version_number is not None:
        current_version = versions_by_number.get(payload.current_version_number)
    elif payload.current_version_id is not None:
        current_version = versions_by_id.get(payload.current_version_id)
    elif versions_by_number:
        current_version = max(versions_by_number.values(), key=lambda item: item.version_number)

    playbook.current_version_id = current_version.id if current_version is not None else None
    playbook.updated_at = datetime.now(UTC)

    await refresh_playbook_embedding(
        playbook,
        content=current_version.content if current_version is not None else None,
    )
    await db.flush()

    refreshed = await load_workspace_playbook(
        db, owner_user_id=owner_user_id, playbook_id=playbook.id
    )
    if refreshed is None:
        raise RuntimeError("Synced playbook disappeared before it could be reloaded.")
    return build_playbook_sync_event(refreshed, workspace)


async def apply_playbook_sync_delete(
    db: AsyncSession,
    workspace: Workspace,
    *,
    event_id: str,
    entity_id: str,
    base_updated_at: datetime | None,
) -> HostedSyncEvent:
    """Apply a pushed delete mutation into the hosted store."""

    owner_user_id = ensure_personal_sync_workspace(workspace)
    playbook_id = _parse_uuid(entity_id, field_name="entity_id")

    current_server_event = await _build_current_server_event(
        db, workspace, owner_user_id, playbook_id
    )
    if current_server_event is not None and current_server_event.operation == "delete":
        return current_server_event

    await _assert_playbook_base_is_current(
        db,
        workspace,
        owner_user_id,
        event_id=event_id,
        playbook_id=playbook_id,
        base_updated_at=base_updated_at,
    )

    playbook = await load_workspace_playbook(
        db, owner_user_id=owner_user_id, playbook_id=playbook_id
    )
    tombstone = await record_playbook_tombstone(db, workspace.id, playbook_id)
    if playbook is not None:
        await db.delete(playbook)
        await db.flush()

    return build_tombstone_sync_event(tombstone)
