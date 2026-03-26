# ruff: noqa: E402
"""Tests for hosted workspace sync routes."""

import os
from datetime import UTC, datetime

DEFAULT_TEST_DATABASE_URL_SYNC = "postgresql://postgres:postgres@localhost:5432/ace_platform_test"


def _derive_async_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


TEST_DATABASE_URL_SYNC = (
    os.environ.get("TEST_DATABASE_URL_SYNC")
    or os.environ.get("TEST_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or DEFAULT_TEST_DATABASE_URL_SYNC
)
TEST_DATABASE_URL_ASYNC = (
    os.environ.get("TEST_DATABASE_URL_ASYNC")
    or os.environ.get("DATABASE_URL_ASYNC")
    or _derive_async_database_url(TEST_DATABASE_URL_SYNC)
)

os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL_SYNC)
os.environ.setdefault("DATABASE_URL_ASYNC", TEST_DATABASE_URL_ASYNC)

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from ace_core.portability import PortablePlaybook, PortablePlaybookVersion
from ace_platform.api.deps import get_db
from ace_platform.core.security import create_access_token, hash_password
from ace_platform.core.workspace_sync import HostedSyncEvent, is_retry_of_current_playbook_state
from ace_platform.db.models import Base, SubscriptionStatus, User

RUN_INTEGRATION_TESTS = os.environ.get("RUN_WORKSPACE_INTEGRATION_TESTS") == "1"


async def _no_rate_limit(*args, **kwargs) -> None:
    """Disable rate limiting in sync integration tests."""


def test_retry_detection_tolerates_server_enriched_review_metadata() -> None:
    now = datetime(2026, 3, 25, 20, 10, tzinfo=UTC)
    current_payload = PortablePlaybook(
        id="pb-1",
        name="Promoted",
        description="desc",
        status="active",
        source="imported",
        current_version_number=1,
        versions=[PortablePlaybookVersion(version_number=1, content="v1", bullet_count=1)],
        traces=[],
        metadata={
            "workspace_id": "ws-1",
            "review_status": "draft",
            "review_status_updated_at": now.isoformat(),
            "review_history": [],
        },
        created_at=now,
        updated_at=now,
    )
    incoming_payload = PortablePlaybook(
        id="pb-1",
        name="Promoted",
        description="desc",
        status="active",
        source="imported",
        current_version_number=1,
        versions=[PortablePlaybookVersion(version_number=1, content="v1", bullet_count=1)],
        traces=[],
        created_at=now,
        updated_at=now,
    )
    current_event = HostedSyncEvent(
        id="evt-1",
        entity_type="playbook",
        entity_id="pb-1",
        operation="upsert",
        occurred_at=now,
        payload=current_payload,
    )

    assert is_retry_of_current_playbook_state(current_event, incoming_payload) is True


def test_retry_detection_still_rejects_changed_review_state() -> None:
    now = datetime(2026, 3, 25, 20, 12, tzinfo=UTC)
    current_payload = PortablePlaybook(
        id="pb-1",
        name="Promoted",
        description="desc",
        status="active",
        source="imported",
        current_version_number=1,
        versions=[PortablePlaybookVersion(version_number=1, content="v1", bullet_count=1)],
        traces=[],
        metadata={
            "workspace_id": "ws-1",
            "review_status": "approved",
            "review_status_updated_at": now.isoformat(),
            "review_history": [{"id": "hist-1", "to_review_status": "approved"}],
        },
        created_at=now,
        updated_at=now,
    )
    incoming_payload = PortablePlaybook(
        id="pb-1",
        name="Promoted",
        description="desc",
        status="active",
        source="imported",
        current_version_number=1,
        versions=[PortablePlaybookVersion(version_number=1, content="v1", bullet_count=1)],
        traces=[],
        created_at=now,
        updated_at=now,
    )
    current_event = HostedSyncEvent(
        id="evt-2",
        entity_type="playbook",
        entity_id="pb-1",
        operation="upsert",
        occurred_at=now,
        payload=current_payload,
    )

    assert is_retry_of_current_playbook_state(current_event, incoming_payload) is False


class TestWorkspaceSyncRoutesUnit:
    """Unit tests for route registration on the main app."""

    @pytest.fixture
    def app(self):
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        return TestClient(app)

    def test_sync_routes_are_registered(self, app):
        routes = [route.path for route in app.routes]
        assert "/v1/workspaces/{workspace_id}/sync/pull" in routes
        assert "/v1/workspaces/{workspace_id}/sync/push" in routes
        assert "/workspaces/{workspace_id}/sync/pull" in routes
        assert "/workspaces/{workspace_id}/sync/push" in routes

    def test_sync_push_requires_auth(self, client):
        response = client.post(
            "/v1/workspaces/00000000-0000-0000-0000-000000000000/sync/push",
            json={"events": []},
        )
        assert response.status_code == 401


@pytest.mark.skipif(
    not RUN_INTEGRATION_TESTS,
    reason="Set RUN_WORKSPACE_INTEGRATION_TESTS=1 to run workspace sync integration tests",
)
class TestWorkspaceSyncRoutesIntegration:
    """Integration coverage for personal-workspace sync push/pull behavior."""

    @pytest.fixture(scope="function")
    async def async_engine(self):
        engine = create_async_engine(
            TEST_DATABASE_URL_ASYNC,
            echo=False,
            poolclass=NullPool,
        )

        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
            await conn.run_sync(Base.metadata.create_all)

        yield engine

        await engine.dispose()

    @pytest.fixture
    async def async_session_maker(self, async_engine):
        yield async_sessionmaker(
            bind=async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @pytest.fixture
    async def async_session(self, async_session_maker):
        async with async_session_maker() as session:
            yield session

    @pytest.fixture
    async def app(self, async_session_maker, monkeypatch):
        from ace_platform.api.main import create_app

        async def _get_test_db():
            async with async_session_maker() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        app = create_app()
        app.dependency_overrides[get_db] = _get_test_db
        monkeypatch.setattr("ace_platform.api.routes.playbooks.rate_limit_outcome", _no_rate_limit)
        yield app
        app.dependency_overrides.clear()

    @pytest.fixture
    async def client(self, app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client

    async def _create_paid_user(
        self,
        async_session: AsyncSession,
        *,
        email: str,
        password: str = "password123",
    ) -> dict[str, str | User]:
        user = User(
            email=email,
            hashed_password=hash_password(password),
            is_active=True,
            email_verified=True,
            subscription_tier="starter",
            subscription_status=SubscriptionStatus.ACTIVE,
        )
        async_session.add(user)
        await async_session.commit()
        return {"user": user, "token": create_access_token(user.id)}

    async def _workspace_id(self, client, headers: dict[str, str]) -> str:
        response = await client.get("/workspaces", headers=headers)
        assert response.status_code == 200
        return response.json()[0]["id"]

    async def test_pull_returns_playbook_snapshots_and_history_updates(
        self,
        client,
        async_session: AsyncSession,
    ):
        user = await self._create_paid_user(
            async_session,
            email="workspace-sync-pull@example.com",
        )
        headers = {"Authorization": f"Bearer {user['token']}"}
        workspace_id = await self._workspace_id(client, headers)

        create_response = await client.post(
            "/playbooks",
            json={
                "name": "Personal Sync",
                "initial_content": "[pb-1] helpful=1 harmful=0 :: Keep context durable",
            },
            headers=headers,
        )
        assert create_response.status_code == 201
        playbook_id = create_response.json()["id"]

        first_pull = await client.get(f"/v1/workspaces/{workspace_id}/sync/pull", headers=headers)
        assert first_pull.status_code == 200
        first_payload = first_pull.json()
        assert len(first_payload["events"]) == 1
        first_event = first_payload["events"][0]
        assert first_event["entity_type"] == "playbook"
        assert first_event["operation"] == "upsert"
        assert first_event["entity_id"] == playbook_id
        assert first_event["payload"]["name"] == "Personal Sync"
        assert len(first_event["payload"]["versions"]) == 1
        assert first_event["payload"]["traces"] == []

        incremental_cursor = first_payload["next_cursor"]
        assert incremental_cursor is not None

        outcome_response = await client.post(
            f"/playbooks/{playbook_id}/outcomes",
            json={
                "task_description": "Validated the workspace sync path",
                "outcome": "success",
                "notes": "History should round-trip with the playbook snapshot.",
            },
            headers=headers,
        )
        assert outcome_response.status_code == 201

        second_pull = await client.get(
            f"/v1/workspaces/{workspace_id}/sync/pull",
            headers=headers,
            params={"cursor": incremental_cursor},
        )
        assert second_pull.status_code == 200
        second_payload = second_pull.json()
        assert len(second_payload["events"]) == 1
        synced_playbook = second_payload["events"][0]["payload"]
        assert len(synced_playbook["traces"]) == 1
        assert (
            synced_playbook["traces"][0]["task_description"] == "Validated the workspace sync path"
        )

    async def test_push_updates_playbook_and_rejects_stale_snapshot(
        self,
        client,
        async_session: AsyncSession,
    ):
        user = await self._create_paid_user(
            async_session,
            email="workspace-sync-push@example.com",
        )
        headers = {"Authorization": f"Bearer {user['token']}"}
        workspace_id = await self._workspace_id(client, headers)

        create_response = await client.post(
            "/playbooks",
            json={
                "name": "Before Sync Push",
                "initial_content": "[pb-2] helpful=1 harmful=0 :: Seed",
            },
            headers=headers,
        )
        assert create_response.status_code == 201
        playbook_id = create_response.json()["id"]

        pull_response = await client.get(
            f"/v1/workspaces/{workspace_id}/sync/pull", headers=headers
        )
        assert pull_response.status_code == 200
        original_event = pull_response.json()["events"][0]
        original_snapshot = original_event["payload"]
        original_updated_at = original_snapshot["updated_at"]

        renamed_snapshot = dict(original_snapshot)
        renamed_snapshot["name"] = "Renamed From Device B"
        push_response = await client.post(
            f"/v1/workspaces/{workspace_id}/sync/push",
            headers=headers,
            json={
                "events": [
                    {
                        "id": "client-upsert-1",
                        "entity_type": "playbook",
                        "entity_id": playbook_id,
                        "operation": "upsert",
                        "base_updated_at": original_updated_at,
                        "payload": renamed_snapshot,
                    }
                ]
            },
        )
        assert push_response.status_code == 200
        push_payload = push_response.json()
        assert push_payload["conflicts"] == []
        assert push_payload["applied_events"][0]["payload"]["name"] == "Renamed From Device B"
        assert push_payload["next_cursor"] is not None

        get_response = await client.get(f"/playbooks/{playbook_id}", headers=headers)
        assert get_response.status_code == 200
        assert get_response.json()["name"] == "Renamed From Device B"

        stale_snapshot = dict(original_snapshot)
        stale_snapshot["name"] = "Stale Device Name"
        stale_response = await client.post(
            f"/v1/workspaces/{workspace_id}/sync/push",
            headers=headers,
            json={
                "events": [
                    {
                        "id": "client-upsert-stale",
                        "entity_type": "playbook",
                        "entity_id": playbook_id,
                        "operation": "upsert",
                        "base_updated_at": original_updated_at,
                        "payload": stale_snapshot,
                    }
                ]
            },
        )
        assert stale_response.status_code == 409
        stale_payload = stale_response.json()
        assert stale_payload["applied_events"] == []
        assert len(stale_payload["conflicts"]) == 1
        assert "newer playbook snapshot" in stale_payload["conflicts"][0]["message"]
        assert (
            stale_payload["conflicts"][0]["server_event"]["payload"]["name"]
            == "Renamed From Device B"
        )

    async def test_pull_returns_delete_event_after_standard_playbook_delete(
        self,
        client,
        async_session: AsyncSession,
    ):
        user = await self._create_paid_user(
            async_session,
            email="workspace-sync-delete@example.com",
        )
        headers = {"Authorization": f"Bearer {user['token']}"}
        workspace_id = await self._workspace_id(client, headers)

        create_response = await client.post(
            "/playbooks",
            json={"name": "Delete Me", "initial_content": "[pb-3] helpful=1 harmful=0 :: delete"},
            headers=headers,
        )
        assert create_response.status_code == 201
        playbook_id = create_response.json()["id"]

        first_pull = await client.get(f"/v1/workspaces/{workspace_id}/sync/pull", headers=headers)
        assert first_pull.status_code == 200
        cursor = first_pull.json()["next_cursor"]
        assert cursor is not None

        delete_response = await client.delete(f"/playbooks/{playbook_id}", headers=headers)
        assert delete_response.status_code == 204

        second_pull = await client.get(
            f"/v1/workspaces/{workspace_id}/sync/pull",
            headers=headers,
            params={"cursor": cursor},
        )
        assert second_pull.status_code == 200
        payload = second_pull.json()
        assert len(payload["events"]) == 1
        delete_event = payload["events"][0]
        assert delete_event["operation"] == "delete"
        assert delete_event["entity_id"] == playbook_id
        assert delete_event["payload"] is None
