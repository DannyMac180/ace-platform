"""Focused tests for auth route response shaping."""

import os
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from ace_platform.api.deps import get_db
from ace_platform.api.routes.auth import get_current_user
from ace_platform.core.security import hash_password
from ace_platform.db.models import Base, SubscriptionStatus, User

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


@pytest.mark.asyncio
async def test_get_current_user_includes_rollout_metadata():
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(),
        email="rollout@example.com",
        hashed_password="hashed-password",
        is_active=True,
        is_admin=False,
        email_verified=True,
        subscription_tier="starter",
        subscription_status=SubscriptionStatus.ACTIVE,
        has_used_trial=False,
        has_payment_method=False,
        onboarding_state={
            "status": "minimized",
            "last_seen_at": now,
            "minimized_at": now,
        },
        created_at=now,
        updated_at=now,
    )

    with (
        patch(
            "ace_platform.api.routes.auth.get_available_plans",
            return_value={"starter": True, "enterprise": False},
        ),
        patch(
            "ace_platform.api.routes.auth.get_user_capabilities",
            return_value={"managed_inference": True, "shared_workspace": False},
        ),
    ):
        response = await get_current_user(user)

    assert response.email == "rollout@example.com"
    assert response.available_plans == {"starter": True, "enterprise": False}
    assert response.capabilities == {
        "managed_inference": True,
        "shared_workspace": False,
    }
    assert response.quick_start_onboarding is not None
    assert response.quick_start_onboarding.state.status == "minimized"
    assert response.quick_start_onboarding.state.minimized_at == now
    assert response.quick_start_onboarding.config.video_embed_url.startswith(
        "https://www.youtube-nocookie.com/embed/"
    )


class TestHostedAuthRouteFlow:
    """Integration test for hosted `/v1` auth flow."""

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
    async def app(self, async_session_maker):
        from ace_platform.api.main import create_app
        from ace_platform.core.rate_limit import rate_limit_login

        async def _get_test_db():
            async with async_session_maker() as session:
                try:
                    yield session
                    await session.commit()
                except Exception:
                    await session.rollback()
                    raise

        async def _no_rate_limit():
            pass

        app = create_app()
        app.dependency_overrides[get_db] = _get_test_db
        app.dependency_overrides[rate_limit_login] = _no_rate_limit
        yield app
        app.dependency_overrides.clear()

    @pytest.fixture
    async def client(self, app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client

    @pytest.fixture
    async def seeded_user(self, async_session_maker):
        async with async_session_maker() as session:
            user = User(
                email="hosted-flow@example.com",
                hashed_password=hash_password("password123"),
                is_active=True,
                email_verified=True,
            )
            session.add(user)
            await session.commit()
            yield user

    @pytest.mark.asyncio
    async def test_hosted_v1_login_refresh_me_and_logout(self, client, seeded_user):
        login_response = await client.post(
            "/v1/auth/login",
            json={"email": "hosted-flow@example.com", "password": "password123"},
        )

        assert login_response.status_code == 200
        login_payload = login_response.json()
        assert login_payload["access_token"]
        assert login_payload["refresh_token"]

        me_response = await client.get(
            "/v1/me",
            headers={"Authorization": f"Bearer {login_payload['access_token']}"},
        )
        assert me_response.status_code == 200
        assert me_response.json()["email"] == "hosted-flow@example.com"

        refresh_response = await client.post(
            "/v1/auth/refresh",
            json={"refresh_token": login_payload["refresh_token"]},
        )
        assert refresh_response.status_code == 200
        refresh_payload = refresh_response.json()
        assert refresh_payload["access_token"]
        assert refresh_payload["refresh_token"]

        logout_response = await client.post(
            "/v1/auth/logout",
            headers={"Authorization": f"Bearer {refresh_payload['access_token']}"},
        )
        assert logout_response.status_code == 200
        assert logout_response.json() == {"message": "Logged out"}
