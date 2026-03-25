"""Integration tests for promoted playbook review workflow routes."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ace_platform.api.auth import require_paid_access
from ace_platform.api.deps import get_db
from ace_platform.core.playbooks import (
    list_shared_workspace_playbooks,
    reuse_shared_workspace_playbook,
)
from ace_platform.core.workspaces import get_default_workspace_inference_config
from ace_platform.db.models import (
    Base,
    Playbook,
    PlaybookReviewAction,
    PlaybookReviewStatus,
    PlaybookSource,
    PlaybookStatus,
    SubscriptionStatus,
    User,
    Workspace,
    WorkspaceDeploymentMode,
    WorkspaceEntitlement,
    WorkspaceMembership,
    WorkspacePlan,
    WorkspaceRole,
)

TEST_DATABASE_URL_ASYNC = os.environ.get(
    "TEST_DATABASE_URL_ASYNC",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/ace_platform_test",
)


async def _create_user(async_session: AsyncSession, email: str) -> User:
    user = User(
        email=email,
        hashed_password="secret",
        subscription_status=SubscriptionStatus.ACTIVE,
        subscription_tier="starter",
        email_verified=True,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


async def _create_team_workspace(
    async_session: AsyncSession,
    *,
    owner: User,
    teammate: User,
    teammate_role: WorkspaceRole,
) -> Workspace:
    workspace = Workspace(
        name="Review Team",
        plan=WorkspacePlan.TEAM,
        deployment_mode=WorkspaceDeploymentMode.CLOUD,
        seat_limit=5,
        inference_config=get_default_workspace_inference_config(
            plan=WorkspacePlan.TEAM,
            deployment_mode=WorkspaceDeploymentMode.CLOUD,
        ),
        entitlements=WorkspaceEntitlement(
            **WorkspaceEntitlement.defaults_for_plan(WorkspacePlan.TEAM)
        ),
        memberships=[
            WorkspaceMembership(user_id=owner.id, role=WorkspaceRole.OWNER),
            WorkspaceMembership(user_id=teammate.id, role=teammate_role),
        ],
    )
    async_session.add(workspace)
    await async_session.commit()
    await async_session.refresh(workspace)
    return workspace


@pytest.fixture(scope="function")
async def async_engine():
    schema_name = f"playbook_review_{uuid4().hex}"
    engine = create_async_engine(
        TEST_DATABASE_URL_ASYNC,
        echo=False,
        connect_args={"server_settings": {"search_path": schema_name}},
    )
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA "{schema_name}"'))
        await conn.execute(text(f'SET search_path TO "{schema_name}"'))
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
    await engine.dispose()


@pytest.fixture
async def async_session(async_engine):
    session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_maker() as session:
        yield session


@pytest.fixture
async def test_user(async_session: AsyncSession):
    user = User(
        email="reviewer@example.com",
        hashed_password="secret",
        subscription_status=SubscriptionStatus.ACTIVE,
        subscription_tier="starter",
        email_verified=True,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def app(async_engine, test_user: User, monkeypatch: pytest.MonkeyPatch):
    from ace_platform.api.routes.playbooks import router

    app = FastAPI()
    app.include_router(router)
    session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_db():
        async with session_maker() as session:
            yield session

    async def override_paid_access():
        return test_user

    async def noop_refresh_embedding(*_args, **_kwargs):
        return None

    monkeypatch.setattr(
        "ace_platform.api.routes.playbooks.refresh_playbook_embedding",
        noop_refresh_embedding,
    )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_paid_access] = override_paid_access
    yield app
    app.dependency_overrides.clear()


@pytest.fixture
async def client(app: FastAPI):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.mark.asyncio
async def test_review_actions_persist_history(async_session: AsyncSession, test_user: User, client):
    playbook = Playbook(
        user_id=test_user.id,
        name="Team Registry Draft",
        description="Needs approval",
        status=PlaybookStatus.ACTIVE,
        review_status=PlaybookReviewStatus.DRAFT,
        review_status_updated_at=datetime.now(UTC),
        review_history=[
            {
                "id": str(uuid4()),
                "action": PlaybookReviewAction.CREATED.value,
                "from_review_status": None,
                "to_review_status": PlaybookReviewStatus.DRAFT.value,
                "actor_user_id": str(test_user.id),
                "actor_email": test_user.email,
                "created_at": datetime.now(UTC).isoformat(),
            }
        ],
        source=PlaybookSource.USER_CREATED,
    )
    async_session.add(playbook)
    await async_session.commit()
    await async_session.refresh(playbook)

    review_response = await client.post(
        f"/playbooks/{playbook.id}/review-actions",
        json={"action": "proposed"},
    )

    assert review_response.status_code == 200
    assert review_response.json()["review_status"] == "proposed"

    activity_response = await client.get(f"/playbooks/{playbook.id}/activity")

    assert activity_response.status_code == 200
    payload = activity_response.json()
    assert payload["total"] == 2
    assert payload["items"][0]["action"] == "proposed"
    assert payload["items"][0]["to_review_status"] == "proposed"
    assert payload["items"][0]["actor_email"] == test_user.email


@pytest.mark.asyncio
async def test_create_playbook_persists_draft_review_status(
    async_session: AsyncSession,
    test_user: User,
    client,
):
    response = await client.post(
        "/playbooks",
        json={"name": "Draft From Route", "description": "Create-path regression test"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == "Draft From Route"
    assert payload["review_status"] == "draft"

    persisted = await async_session.get(Playbook, payload["id"])
    assert persisted is not None
    assert persisted.review_status is PlaybookReviewStatus.DRAFT


@pytest.mark.asyncio
async def test_list_playbooks_filters_by_review_status(
    async_session: AsyncSession,
    test_user: User,
    client,
):
    async_session.add_all(
        [
            Playbook(
                user_id=test_user.id,
                name="Approved Playbook",
                description=None,
                status=PlaybookStatus.ACTIVE,
                review_status=PlaybookReviewStatus.APPROVED,
                review_status_updated_at=datetime.now(UTC),
                review_history=[],
                source=PlaybookSource.USER_CREATED,
            ),
            Playbook(
                user_id=test_user.id,
                name="Draft Playbook",
                description=None,
                status=PlaybookStatus.ACTIVE,
                review_status=PlaybookReviewStatus.DRAFT,
                review_status_updated_at=datetime.now(UTC),
                review_history=[],
                source=PlaybookSource.USER_CREATED,
            ),
        ]
    )
    await async_session.commit()

    response = await client.get("/playbooks?review_status_filter=approved")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["name"] == "Approved Playbook"
    assert payload["items"][0]["review_status"] == "approved"


@pytest.mark.asyncio
async def test_shared_workspace_registry_lists_only_approved_playbooks(async_session: AsyncSession):
    owner = await _create_user(async_session, "shared-owner@example.com")
    teammate = await _create_user(async_session, "shared-teammate@example.com")
    workspace = await _create_team_workspace(
        async_session,
        owner=owner,
        teammate=teammate,
        teammate_role=WorkspaceRole.MEMBER,
    )

    async_session.add_all(
        [
            Playbook(
                user_id=owner.id,
                name="Approved Team Playbook",
                description="Visible in registry",
                status=PlaybookStatus.ACTIVE,
                review_status=PlaybookReviewStatus.APPROVED,
                review_status_updated_at=datetime.now(UTC),
                review_history=[],
                source=PlaybookSource.USER_CREATED,
            ),
            Playbook(
                user_id=owner.id,
                name="Draft Team Playbook",
                description="Hidden from registry",
                status=PlaybookStatus.ACTIVE,
                review_status=PlaybookReviewStatus.DRAFT,
                review_status_updated_at=datetime.now(UTC),
                review_history=[],
                source=PlaybookSource.USER_CREATED,
            ),
        ]
    )
    await async_session.commit()

    playbooks, total = await list_shared_workspace_playbooks(
        async_session,
        workspace,
        current_user_id=teammate.id,
        page=1,
        page_size=20,
    )

    assert total == 1
    assert [playbook.name for playbook in playbooks] == ["Approved Team Playbook"]


@pytest.mark.asyncio
async def test_reuse_shared_workspace_playbook_rejects_unapproved_entries(
    async_session: AsyncSession,
):
    owner = await _create_user(async_session, "reuse-owner@example.com")
    teammate = await _create_user(async_session, "reuse-teammate@example.com")
    workspace = await _create_team_workspace(
        async_session,
        owner=owner,
        teammate=teammate,
        teammate_role=WorkspaceRole.MEMBER,
    )
    draft_playbook = Playbook(
        user_id=owner.id,
        name="Draft Team Playbook",
        description="Should not be reusable",
        status=PlaybookStatus.ACTIVE,
        review_status=PlaybookReviewStatus.DRAFT,
        review_status_updated_at=datetime.now(UTC),
        review_history=[],
        source=PlaybookSource.USER_CREATED,
    )
    async_session.add(draft_playbook)
    await async_session.commit()
    await async_session.refresh(draft_playbook)

    with pytest.raises(LookupError, match="Shared playbook not found"):
        await reuse_shared_workspace_playbook(
            async_session,
            workspace,
            current_user=teammate,
            source_playbook_id=draft_playbook.id,
        )


@pytest.mark.asyncio
async def test_reviewer_can_approve_teammate_playbook(
    async_session: AsyncSession,
    test_user: User,
    client,
):
    owner = await _create_user(async_session, "teammate-owner@example.com")
    await _create_team_workspace(
        async_session,
        owner=owner,
        teammate=test_user,
        teammate_role=WorkspaceRole.REVIEWER,
    )

    playbook = Playbook(
        user_id=owner.id,
        name="Teammate Playbook",
        description="Needs approval",
        status=PlaybookStatus.ACTIVE,
        review_status=PlaybookReviewStatus.PROPOSED,
        review_status_updated_at=datetime.now(UTC),
        review_history=[
            {
                "id": str(uuid4()),
                "action": PlaybookReviewAction.PROPOSED.value,
                "from_review_status": PlaybookReviewStatus.DRAFT.value,
                "to_review_status": PlaybookReviewStatus.PROPOSED.value,
                "actor_user_id": str(owner.id),
                "actor_email": owner.email,
                "created_at": datetime.now(UTC).isoformat(),
            }
        ],
        source=PlaybookSource.USER_CREATED,
    )
    async_session.add(playbook)
    await async_session.commit()
    await async_session.refresh(playbook)

    review_response = await client.post(
        f"/playbooks/{playbook.id}/review-actions",
        json={"action": "approved"},
    )

    assert review_response.status_code == 200
    assert review_response.json()["review_status"] == "approved"

    activity_response = await client.get(f"/playbooks/{playbook.id}/activity")

    assert activity_response.status_code == 200
    payload = activity_response.json()
    assert payload["items"][0]["action"] == "approved"
    assert payload["items"][0]["actor_email"] == test_user.email


@pytest.mark.asyncio
async def test_member_cannot_run_teammate_review_actions(
    async_session: AsyncSession,
    test_user: User,
    client,
):
    owner = await _create_user(async_session, "unauthorized-owner@example.com")
    await _create_team_workspace(
        async_session,
        owner=owner,
        teammate=test_user,
        teammate_role=WorkspaceRole.MEMBER,
    )

    playbook = Playbook(
        user_id=owner.id,
        name="Protected Team Playbook",
        description="Only approvers can review",
        status=PlaybookStatus.ACTIVE,
        review_status=PlaybookReviewStatus.PROPOSED,
        review_status_updated_at=datetime.now(UTC),
        review_history=[],
        source=PlaybookSource.USER_CREATED,
    )
    async_session.add(playbook)
    await async_session.commit()
    await async_session.refresh(playbook)

    review_response = await client.post(
        f"/playbooks/{playbook.id}/review-actions",
        json={"action": "approved"},
    )
    assert review_response.status_code == 403
    assert "permission" in review_response.json()["detail"].lower()

    activity_response = await client.get(f"/playbooks/{playbook.id}/activity")
    assert activity_response.status_code == 403
    assert "permission" in activity_response.json()["detail"].lower()
