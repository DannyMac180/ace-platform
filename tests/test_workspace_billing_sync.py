"""Integration tests for workspace billing state synchronization."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from ace_platform.core.subscription_service import FREE_PLAN_CODE
from ace_platform.core.webhooks import WebhookEventType, handle_webhook_event
from ace_platform.core.workspaces import bootstrap_workspace_for_user
from ace_platform.db.models import (
    Base,
    User,
    Workspace,
    WorkspacePlan,
    WorkspaceSubscriptionStatus,
)

TEST_DATABASE_URL_ASYNC = os.environ.get(
    "TEST_DATABASE_URL_ASYNC",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/ace_platform_test",
)


@pytest.fixture(scope="function")
async def async_engine():
    engine = create_async_engine(TEST_DATABASE_URL_ASYNC, echo=False)

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    yield engine

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


async def _create_user(async_session: AsyncSession, *, email: str, stripe_customer_id: str) -> User:
    user = User(
        email=email,
        hashed_password="placeholder",
        is_active=True,
        email_verified=True,
        stripe_customer_id=stripe_customer_id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


async def _load_workspace(async_session: AsyncSession, workspace_id) -> Workspace:
    return (
        await async_session.execute(
            select(Workspace)
            .where(Workspace.id == workspace_id)
            .options(
                selectinload(Workspace.subscription),
                selectinload(Workspace.entitlements),
            )
        )
    ).scalar_one()


@pytest.mark.asyncio
async def test_subscription_updated_without_metadata_persists_workspace_subscription(
    async_session: AsyncSession,
):
    user = await _create_user(
        async_session,
        email="workspace-sync@example.com",
        stripe_customer_id="cus_workspace_sync",
    )
    workspace, _ = await bootstrap_workspace_for_user(async_session, user)
    await async_session.commit()

    event = MagicMock()
    event.id = "evt_workspace_sync"
    event.type = WebhookEventType.SUBSCRIPTION_UPDATED
    event.data.object = MagicMock(
        id="sub_workspace_sync",
        customer="cus_workspace_sync",
        status="active",
        current_period_end=int((datetime.now(UTC) + timedelta(days=30)).timestamp()),
        items=MagicMock(data=[]),
    )

    result = await handle_webhook_event(async_session, event)
    refreshed_workspace = await _load_workspace(async_session, workspace.id)

    assert result.success is True
    assert refreshed_workspace.plan == WorkspacePlan.PERSONAL
    assert refreshed_workspace.subscription is not None
    assert refreshed_workspace.subscription.status == WorkspaceSubscriptionStatus.ACTIVE
    assert refreshed_workspace.subscription.plan_code == FREE_PLAN_CODE
    assert refreshed_workspace.subscription.provider_customer_id == "cus_workspace_sync"
    assert refreshed_workspace.subscription.provider_subscription_id == "sub_workspace_sync"


@pytest.mark.asyncio
async def test_enterprise_subscription_lifecycle_updates_workspace_plan(
    async_session: AsyncSession,
):
    user = await _create_user(
        async_session,
        email="workspace-enterprise@example.com",
        stripe_customer_id="cus_workspace_enterprise",
    )
    workspace, _ = await bootstrap_workspace_for_user(async_session, user)
    await async_session.commit()

    upgrade_event = MagicMock()
    upgrade_event.id = "evt_workspace_enterprise_upgrade"
    upgrade_event.type = WebhookEventType.SUBSCRIPTION_UPDATED
    upgrade_event.data.object = MagicMock(
        id="sub_workspace_enterprise",
        customer="cus_workspace_enterprise",
        status="active",
        current_period_end=int((datetime.now(UTC) + timedelta(days=30)).timestamp()),
        metadata={"tier": "enterprise", "plan_code": "enterprise"},
        items=MagicMock(data=[]),
    )

    upgrade_result = await handle_webhook_event(async_session, upgrade_event)
    upgraded_workspace = await _load_workspace(async_session, workspace.id)

    assert upgrade_result.success is True
    assert upgraded_workspace.plan == WorkspacePlan.ENTERPRISE
    assert upgraded_workspace.subscription is not None
    assert upgraded_workspace.subscription.plan_code == "enterprise"
    assert upgraded_workspace.subscription.status == WorkspaceSubscriptionStatus.ACTIVE
    assert upgraded_workspace.entitlements is not None
    assert upgraded_workspace.entitlements.sso is True

    cancel_event = MagicMock()
    cancel_event.id = "evt_workspace_enterprise_cancel"
    cancel_event.type = WebhookEventType.SUBSCRIPTION_DELETED
    cancel_event.data.object = MagicMock(
        id="sub_workspace_enterprise",
        customer="cus_workspace_enterprise",
        metadata={"tier": "enterprise", "plan_code": "enterprise"},
        items=MagicMock(data=[]),
    )

    cancel_result = await handle_webhook_event(async_session, cancel_event)
    canceled_workspace = await _load_workspace(async_session, workspace.id)

    assert cancel_result.success is True
    assert canceled_workspace.plan == WorkspacePlan.PERSONAL
    assert canceled_workspace.subscription is not None
    assert canceled_workspace.subscription.plan_code == FREE_PLAN_CODE
    assert canceled_workspace.subscription.status == WorkspaceSubscriptionStatus.CANCELED
    assert canceled_workspace.subscription.provider_subscription_id is None
    assert canceled_workspace.entitlements is not None
    assert canceled_workspace.entitlements.sso is False
