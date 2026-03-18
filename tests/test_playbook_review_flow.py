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
from ace_platform.db.models import (
    Base,
    Playbook,
    PlaybookReviewAction,
    PlaybookReviewStatus,
    PlaybookSource,
    PlaybookStatus,
    SubscriptionStatus,
    User,
)

TEST_DATABASE_URL_ASYNC = os.environ.get(
    "TEST_DATABASE_URL_ASYNC",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/ace_platform_test",
)


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
