# ruff: noqa: E402
"""Tests for workspace tenancy routes."""

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

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
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from ace_platform.api.auth import require_paid_access
from ace_platform.api.deps import get_db
from ace_platform.api.routes.workspaces import WorkspaceCreateRequest, WorkspaceResponse
from ace_platform.core.security import create_access_token, hash_password
from ace_platform.db.models import Base, User, WorkspaceMembership

RUN_INTEGRATION_TESTS = os.environ.get("RUN_WORKSPACE_INTEGRATION_TESTS") == "1"


async def _no_rate_limit() -> None:
    """Disable rate limiting in route tests."""


class TestWorkspaceRoutesUnit:
    """Unit tests for workspace route registration and auth guards."""

    @pytest.fixture
    def app(self):
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        return TestClient(app)

    def test_workspace_routes_registered(self, app):
        routes = [route.path for route in app.routes]
        assert "/workspaces" in routes
        assert "/workspaces/bootstrap" in routes
        assert "/workspaces/{workspace_id}" in routes
        assert "/workspaces/{workspace_id}/memberships" in routes
        assert "/workspaces/{workspace_id}/memberships/{membership_id}" in routes
        assert "/v1/workspaces/{workspace_id}/playbooks/shared" in routes
        assert "/v1/workspaces/{workspace_id}/playbooks/shared/{playbook_id}/reuse" in routes
        assert "/v1/workspaces/{workspace_id}/sync/pull" in routes
        assert "/v1/workspaces/{workspace_id}/sync/push" in routes

    def test_workspace_list_requires_auth(self, client):
        response = client.get("/workspaces")
        assert response.status_code == 401

    def test_workspace_create_requires_auth(self, client):
        response = client.post("/workspaces", json={"name": "Team Alpha", "plan": "team"})
        assert response.status_code == 401

    def test_workspace_sync_pull_requires_auth(self, client):
        response = client.get(f"/v1/workspaces/{uuid4()}/sync/pull")
        assert response.status_code == 401

    def test_workspace_shared_playbooks_requires_auth(self, client):
        response = client.get("/v1/workspaces/me/playbooks/shared")
        assert response.status_code == 401

    def test_reuse_shared_workspace_playbook_requires_auth(self, client):
        response = client.post(f"/v1/workspaces/me/playbooks/shared/{uuid4()}/reuse")
        assert response.status_code == 401

    def test_workspace_models_include_inference_config(self):
        payload = WorkspaceCreateRequest.model_validate(
            {
                "name": "Team Alpha",
                "plan": "team",
                "inference_config": {
                    "mode": "managed_provider",
                    "provider": "openai",
                },
            }
        )

        assert payload.inference_config is not None
        assert payload.inference_config.mode.value == "managed_provider"
        assert payload.inference_config.provider.value == "openai"
        assert "inference_config" in WorkspaceResponse.model_json_schema()["properties"]


class TestSharedRegistryRoutesUnit:
    """Focused tests for shared playbook registry route serialization."""

    @pytest.fixture
    def app(self):
        from ace_platform.api.routes.workspaces import router

        app = FastAPI()
        app.include_router(router)

        class _DbStub:
            async def commit(self):
                return None

            async def refresh(self, *_args, **_kwargs):
                return None

        async def override_db():
            yield _DbStub()

        async def override_paid_access():
            return SimpleNamespace(
                id=uuid4(),
                subscription_status="active",
                subscription_tier="starter",
            )

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[require_paid_access] = override_paid_access
        return app

    @pytest.fixture
    def client(self, app):
        return TestClient(app)

    def test_shared_registry_route_serializes_owner_metadata(self, client, monkeypatch):
        from ace_platform.api.routes import workspaces as workspace_routes

        current_user_id = uuid4()

        async def override_paid_access():
            return SimpleNamespace(
                id=current_user_id,
                subscription_status="active",
                subscription_tier="starter",
            )

        client.app.dependency_overrides[require_paid_access] = override_paid_access

        async def fake_require_workspace(*_args, **_kwargs):
            return SimpleNamespace(id=uuid4())

        async def fake_list_shared(*_args, **_kwargs):
            owner = SimpleNamespace(id=uuid4(), email="owner@example.com")
            playbook = SimpleNamespace(
                id=uuid4(),
                name="Registry Playbook",
                description="Shared guidance",
                status="active",
                source="user_created",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                versions=[object()],
                outcomes=[object(), object()],
                user=owner,
                user_id=owner.id,
            )
            return [playbook], 1

        monkeypatch.setattr(
            workspace_routes,
            "_require_shared_registry_workspace",
            fake_require_workspace,
        )
        monkeypatch.setattr(
            workspace_routes,
            "list_shared_workspace_playbooks",
            fake_list_shared,
        )

        response = client.get("/v1/workspaces/me/playbooks/shared")

        assert response.status_code == 200
        payload = response.json()
        assert payload["items"][0]["owner"]["email"] == "owner@example.com"
        assert payload["items"][0]["version_count"] == 1
        assert payload["items"][0]["outcome_count"] == 2

    def test_reuse_shared_registry_route_returns_copied_playbook(self, client, monkeypatch):
        from ace_platform.api.routes import workspaces as workspace_routes

        playbook_id = uuid4()
        copied_version_id = uuid4()

        async def fake_require_workspace(*_args, **_kwargs):
            return SimpleNamespace(id=uuid4())

        async def fake_reuse(*_args, **_kwargs):
            return SimpleNamespace(
                id=playbook_id,
                name="Copied Playbook",
                description="Copied from team registry",
                status="active",
                source="imported",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                current_version_id=copied_version_id,
                current_version=SimpleNamespace(
                    id=copied_version_id,
                    version_number=1,
                    content="- copied",
                    bullet_count=1,
                    created_at=datetime.now(timezone.utc),
                ),
            )

        monkeypatch.setattr(
            workspace_routes,
            "_require_shared_registry_workspace",
            fake_require_workspace,
        )
        monkeypatch.setattr(
            workspace_routes,
            "reuse_shared_workspace_playbook",
            fake_reuse,
        )

        response = client.post(f"/v1/workspaces/me/playbooks/shared/{playbook_id}/reuse")

        assert response.status_code == 200
        payload = response.json()
        assert payload["id"] == str(playbook_id)
        assert payload["current_version"]["id"] == str(copied_version_id)


@pytest.mark.skipif(
    not RUN_INTEGRATION_TESTS,
    reason="Set RUN_WORKSPACE_INTEGRATION_TESTS=1 to run workspace integration tests",
)
class TestWorkspaceRoutesIntegration:
    """Integration tests for workspace routes."""

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
    async def app(self, async_session_maker):
        from ace_platform.api.main import create_app
        from ace_platform.core.rate_limit import rate_limit_login, rate_limit_register

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
        app.dependency_overrides[rate_limit_register] = _no_rate_limit
        app.dependency_overrides[rate_limit_login] = _no_rate_limit
        yield app
        app.dependency_overrides.clear()

    @pytest.fixture
    async def client(self, app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client

    async def _create_user(
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
        )
        async_session.add(user)
        await async_session.commit()
        return {"user": user, "token": create_access_token(user.id)}

    async def test_register_bootstraps_personal_workspace(self, client):
        response = await client.post(
            "/auth/register",
            json={"email": "workspace-register@example.com", "password": "password123"},
        )

        assert response.status_code == 201
        access_token = response.json()["access_token"]

        workspace_response = await client.get(
            "/workspaces",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert workspace_response.status_code == 200
        payload = workspace_response.json()
        assert len(payload) == 1
        assert payload[0]["plan"] == "personal"
        assert payload[0]["seat_limit"] == 1
        assert payload[0]["inference_config"]["mode"] == "managed_provider"
        assert payload[0]["current_user_role"] == "owner"

        entitlements_response = await client.get(
            "/v1/workspaces/me/entitlements",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert entitlements_response.status_code == 200
        entitlement_payload = entitlements_response.json()
        assert entitlement_payload["workspace_id"] == payload[0]["id"]
        assert entitlement_payload["plan"] == "personal"
        assert entitlement_payload["seat_limit"] == 1

    async def test_existing_user_without_workspace_is_bootstrapped_on_first_workspace_request(
        self,
        client,
        async_session: AsyncSession,
    ):
        existing_user = await self._create_user(
            async_session,
            email="legacy-workspace@example.com",
        )

        response = await client.get(
            "/workspaces",
            headers={"Authorization": f"Bearer {existing_user['token']}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["plan"] == "personal"
        assert payload[0]["inference_config"]["mode"] == "managed_provider"

        membership_count = await async_session.scalar(
            select(func.count())
            .select_from(WorkspaceMembership)
            .where(WorkspaceMembership.user_id == existing_user["user"].id)
        )
        assert membership_count == 1

    async def test_existing_user_without_workspace_is_bootstrapped_on_login(
        self,
        client,
        async_session: AsyncSession,
    ):
        await self._create_user(
            async_session,
            email="legacy-login@example.com",
            password="password123",
        )

        login_response = await client.post(
            "/auth/login",
            json={"email": "legacy-login@example.com", "password": "password123"},
        )

        assert login_response.status_code == 200
        access_token = login_response.json()["access_token"]

        workspace_response = await client.get(
            "/workspaces",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert workspace_response.status_code == 200
        assert len(workspace_response.json()) == 1

    async def test_workspace_crud_and_membership_management(
        self,
        client,
        async_session: AsyncSession,
    ):
        owner = await self._create_user(async_session, email="owner-workspace@example.com")
        teammate = await self._create_user(async_session, email="teammate-workspace@example.com")

        owner_headers = {"Authorization": f"Bearer {owner['token']}"}
        teammate_headers = {"Authorization": f"Bearer {teammate['token']}"}

        assert (
            await client.post("/workspaces/bootstrap", headers=owner_headers)
        ).status_code == 200
        assert (
            await client.post("/workspaces/bootstrap", headers=teammate_headers)
        ).status_code == 200

        create_response = await client.post(
            "/workspaces",
            json={"name": "Team Alpha", "plan": "team", "seat_limit": 3},
            headers=owner_headers,
        )
        assert create_response.status_code == 201
        assert create_response.json()["inference_config"]["mode"] == "managed_provider"
        workspace_id = create_response.json()["id"]

        add_response = await client.post(
            f"/workspaces/{workspace_id}/memberships",
            json={"user_email": "teammate-workspace@example.com", "role": "member"},
            headers=owner_headers,
        )
        assert add_response.status_code == 201
        assert add_response.json()["role"] == "member"
        membership_id = add_response.json()["id"]

        list_response = await client.get(
            f"/workspaces/{workspace_id}/memberships",
            headers=owner_headers,
        )
        assert list_response.status_code == 200
        memberships = list_response.json()
        assert len(memberships) == 2

        update_response = await client.patch(
            f"/workspaces/{workspace_id}/memberships/{membership_id}",
            json={"role": "admin"},
            headers=owner_headers,
        )
        assert update_response.status_code == 200
        assert update_response.json()["role"] == "admin"

        delete_membership_response = await client.delete(
            f"/workspaces/{workspace_id}/memberships/{membership_id}",
            headers=owner_headers,
        )
        assert delete_membership_response.status_code == 204

        delete_workspace_response = await client.delete(
            f"/workspaces/{workspace_id}",
            headers=owner_headers,
        )
        assert delete_workspace_response.status_code == 204

    async def test_workspace_invariants_prevent_last_owner_removal_and_stranding_member(
        self,
        client,
        async_session: AsyncSession,
    ):
        owner = await self._create_user(async_session, email="solo-owner@example.com")
        member = await self._create_user(async_session, email="solo-member@example.com")

        owner_headers = {"Authorization": f"Bearer {owner['token']}"}

        create_response = await client.post(
            "/workspaces",
            json={"name": "Team Beta", "plan": "team", "seat_limit": 2},
            headers=owner_headers,
        )
        assert create_response.status_code == 201
        workspace_id = create_response.json()["id"]

        add_response = await client.post(
            f"/workspaces/{workspace_id}/memberships",
            json={"user_id": str(member["user"].id), "role": "member"},
            headers=owner_headers,
        )
        assert add_response.status_code == 201
        owner_memberships = await client.get(
            f"/workspaces/{workspace_id}/memberships",
            headers=owner_headers,
        )
        assert owner_memberships.status_code == 200
        owner_membership_id = next(
            membership["id"]
            for membership in owner_memberships.json()
            if membership["user_id"] == str(owner["user"].id)
        )

        demote_owner_response = await client.patch(
            f"/workspaces/{workspace_id}/memberships/{owner_membership_id}",
            json={"role": "member"},
            headers=owner_headers,
        )
        assert demote_owner_response.status_code == 400
        assert "retain at least one owner" in demote_owner_response.json()["error"]["message"]

        delete_workspace_response = await client.delete(
            f"/workspaces/{workspace_id}",
            headers=owner_headers,
        )
        assert delete_workspace_response.status_code == 400
        assert (
            "leave at least one user without any workspace"
            in delete_workspace_response.json()["error"]["message"]
        )
