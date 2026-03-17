from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from ace_core.portability import (
    PortableBundleOrigin,
    PortablePlaybook,
    PortablePlaybookBundle,
    PortablePlaybookVersion,
    PortableTrace,
    bundle_from_json,
    bundle_to_json,
)
from ace_platform.core.playbooks import export_playbook_bundle, import_playbook_bundle
from ace_platform.db.models import Outcome, OutcomeStatus, Playbook, PlaybookSource, PlaybookStatus


class _ScalarResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class _ExportSession:
    def __init__(self, playbooks):
        self._playbooks = playbooks

    async def execute(self, _query):
        return _ScalarResult(self._playbooks)


class _ImportSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.committed = False

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid4()

    async def commit(self) -> None:
        self.committed = True


def test_bundle_json_round_trip_preserves_playbooks_and_traces() -> None:
    timestamp = datetime(2026, 3, 17, 15, 10, tzinfo=UTC)
    bundle = PortablePlaybookBundle(
        exported_at=timestamp,
        origin=PortableBundleOrigin(system="ace-platform", context="hosted"),
        playbooks=[
            PortablePlaybook(
                id="pb-1",
                name="Import Export",
                description="Portable bundle",
                status="active",
                source="user_created",
                current_version_number=2,
                versions=[
                    PortablePlaybookVersion(
                        id="ver-1",
                        version_number=1,
                        content="v1",
                        bullet_count=1,
                        created_at=timestamp,
                    ),
                    PortablePlaybookVersion(
                        id="ver-2",
                        version_number=2,
                        content="v2",
                        bullet_count=2,
                        created_at=timestamp,
                    ),
                ],
                traces=[
                    PortableTrace(
                        id="trace-1",
                        task_description="Ship the CLI",
                        outcome="success",
                        notes="Worked",
                        reasoning_trace="Checked the API shape",
                        created_at=timestamp,
                    )
                ],
                created_at=timestamp,
                updated_at=timestamp,
            )
        ],
    )

    restored = bundle_from_json(bundle_to_json(bundle))

    assert restored == bundle
    assert restored.playbooks[0].versions[1].content == "v2"
    assert restored.playbooks[0].traces[0].reasoning_trace == "Checked the API shape"


@pytest.mark.asyncio
async def test_export_playbook_bundle_includes_versions_and_traces() -> None:
    timestamp = datetime(2026, 3, 17, 15, 15, tzinfo=UTC)
    current_version_id = uuid4()
    playbook = SimpleNamespace(
        id=uuid4(),
        name="Hosted Playbook",
        description="desc",
        status=PlaybookStatus.ACTIVE,
        source=PlaybookSource.USER_CREATED,
        current_version_id=current_version_id,
        current_version=SimpleNamespace(id=current_version_id, version_number=2),
        versions=[
            SimpleNamespace(
                id=current_version_id,
                version_number=2,
                content="latest",
                bullet_count=3,
                diff_summary="expanded",
                created_at=timestamp,
            ),
            SimpleNamespace(
                id=uuid4(),
                version_number=1,
                content="initial",
                bullet_count=1,
                diff_summary=None,
                created_at=timestamp,
            ),
        ],
        outcomes=[
            SimpleNamespace(
                id=uuid4(),
                task_description="Move artifacts",
                outcome_status=OutcomeStatus.SUCCESS,
                notes="portable",
                reasoning_trace="Exported to bundle",
                created_at=timestamp,
                processed_at=None,
            )
        ],
        created_at=timestamp,
        updated_at=timestamp,
    )

    bundle = await export_playbook_bundle(
        _ExportSession([playbook]),
        uuid4(),
        api_url="https://ace.example",
    )

    assert bundle.origin.api_url == "https://ace.example"
    assert len(bundle.playbooks) == 1
    assert [version.version_number for version in bundle.playbooks[0].versions] == [1, 2]
    assert bundle.playbooks[0].traces[0].reasoning_trace == "Exported to bundle"


@pytest.mark.asyncio
async def test_import_playbook_bundle_creates_imported_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedding_refresh = AsyncMock()
    monkeypatch.setattr("ace_platform.core.playbooks.refresh_playbook_embedding", embedding_refresh)

    timestamp = datetime(2026, 3, 17, 15, 20, tzinfo=UTC)
    bundle = PortablePlaybookBundle(
        exported_at=timestamp,
        playbooks=[
            PortablePlaybook(
                id="pb-1",
                name="Portable Playbook",
                description="desc",
                status="active",
                source="user_created",
                current_version_number=2,
                versions=[
                    PortablePlaybookVersion(
                        id="ver-1",
                        version_number=1,
                        content="first",
                        bullet_count=1,
                        created_at=timestamp,
                    ),
                    PortablePlaybookVersion(
                        id="ver-2",
                        version_number=2,
                        content="second",
                        bullet_count=2,
                        created_at=timestamp,
                    ),
                ],
                traces=[
                    PortableTrace(
                        id="trace-1",
                        task_description="Import hosted bundle",
                        outcome="partial",
                        notes="Imported",
                        reasoning_trace="Used portable bundle",
                        created_at=timestamp,
                    )
                ],
                created_at=timestamp,
                updated_at=timestamp,
            )
        ],
    )

    session = _ImportSession()
    summaries = await import_playbook_bundle(session, uuid4(), bundle)

    playbooks = [obj for obj in session.added if isinstance(obj, Playbook)]
    versions = [obj for obj in session.added if obj.__class__.__name__ == "PlaybookVersion"]
    traces = [obj for obj in session.added if isinstance(obj, Outcome)]

    assert session.committed is True
    assert len(summaries) == 1
    assert len(playbooks) == 1
    assert len(versions) == 2
    assert len(traces) == 1
    assert playbooks[0].source == PlaybookSource.IMPORTED
    assert playbooks[0].status == PlaybookStatus.ACTIVE
    assert playbooks[0].current_version_id is not None
    assert traces[0].outcome_status == OutcomeStatus.PARTIAL
    embedding_refresh.assert_awaited_once()
