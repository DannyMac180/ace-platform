# ruff: noqa: E402
"""Tests for workspace tenancy routes."""

import os
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
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

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
        assert "permissions" in WorkspaceResponse.model_json_schema()["properties"]


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

    async def test_workspace_permissions_expose_role_matrix_and_enforce_management_guards(
        self,
        client,
        async_session: AsyncSession,
    ):
        owner = await self._create_user(async_session, email="roles-owner@example.com")
        admin = await self._create_user(async_session, email="roles-admin@example.com")
        reviewer = await self._create_user(async_session, email="roles-reviewer@example.com")
        member = await self._create_user(async_session, email="roles-member@example.com")
        outsider = await self._create_user(async_session, email="roles-outsider@example.com")

        owner_headers = {"Authorization": f"Bearer {owner['token']}"}
        admin_headers = {"Authorization": f"Bearer {admin['token']}"}
        reviewer_headers = {"Authorization": f"Bearer {reviewer['token']}"}
        member_headers = {"Authorization": f"Bearer {member['token']}"}

        create_response = await client.post(
            "/workspaces",
            json={"name": "Roles Team", "plan": "team", "seat_limit": 6},
            headers=owner_headers,
        )
        assert create_response.status_code == 201
        workspace_id = create_response.json()["id"]

        for email, role in [
            ("roles-admin@example.com", "admin"),
            ("roles-reviewer@example.com", "reviewer"),
            ("roles-member@example.com", "member"),
        ]:
            add_response = await client.post(
                f"/workspaces/{workspace_id}/memberships",
                json={"user_email": email, "role": role},
                headers=owner_headers,
            )
            assert add_response.status_code == 201

        owner_workspace = await client.get(f"/workspaces/{workspace_id}", headers=owner_headers)
        admin_workspace = await client.get(f"/workspaces/{workspace_id}", headers=admin_headers)
        reviewer_workspace = await client.get(
            f"/workspaces/{workspace_id}",
            headers=reviewer_headers,
        )
        member_workspace = await client.get(f"/workspaces/{workspace_id}", headers=member_headers)

        assert owner_workspace.status_code == 200
        assert owner_workspace.json()["permissions"] == {
            "can_manage_settings": True,
            "can_manage_seats": True,
            "can_approve_playbooks": True,
        }
        assert admin_workspace.status_code == 200
        assert admin_workspace.json()["permissions"] == {
            "can_manage_settings": True,
            "can_manage_seats": True,
            "can_approve_playbooks": True,
        }
        assert reviewer_workspace.status_code == 200
        assert reviewer_workspace.json()["permissions"] == {
            "can_manage_settings": False,
            "can_manage_seats": False,
            "can_approve_playbooks": True,
        }
        assert member_workspace.status_code == 200
        assert member_workspace.json()["permissions"] == {
            "can_manage_settings": False,
            "can_manage_seats": False,
            "can_approve_playbooks": False,
        }

        reviewer_update = await client.patch(
            f"/workspaces/{workspace_id}",
            json={"name": "Reviewer Cannot Edit"},
            headers=reviewer_headers,
        )
        assert reviewer_update.status_code == 403
        assert (
            reviewer_update.json()["error"]["message"]
            == "Workspace owner or admin role required to manage workspace settings"
        )

        member_add = await client.post(
            f"/workspaces/{workspace_id}/memberships",
            json={"user_id": str(outsider["user"].id), "role": "member"},
            headers=member_headers,
        )
        assert member_add.status_code == 403
        assert (
            member_add.json()["error"]["message"]
            == "Workspace owner or admin role required to manage workspace seats"
        )

        reviewer_add = await client.post(
            f"/workspaces/{workspace_id}/memberships",
            json={"user_id": str(outsider["user"].id), "role": "member"},
            headers=reviewer_headers,
        )
        assert reviewer_add.status_code == 403
        assert (
            reviewer_add.json()["error"]["message"]
            == "Workspace owner or admin role required to manage workspace seats"
        )

        admin_update = await client.patch(
            f"/workspaces/{workspace_id}",
            json={"seat_limit": 7},
            headers=admin_headers,
        )
        assert admin_update.status_code == 200
        assert admin_update.json()["seat_limit"] == 7
