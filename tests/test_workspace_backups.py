# ruff: noqa: E402
"""Integration tests for hosted personal workspace backups."""

import os
from decimal import Decimal
from uuid import uuid4

TEST_DATABASE_URL_SYNC = "postgresql://postgres:postgres@localhost:5432/ace_platform_test"
TEST_DATABASE_URL_ASYNC = "postgresql+asyncpg://postgres:postgres@localhost:5432/ace_platform_test"

os.environ["DATABASE_URL"] = TEST_DATABASE_URL_SYNC
os.environ["DATABASE_URL_ASYNC"] = TEST_DATABASE_URL_ASYNC

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from ace_platform.core.security import hash_password
from ace_platform.core.workspace_backups import (
    WORKSPACE_BACKUP_RETENTION_COUNT,
    backup_hosted_personal_workspaces,
    create_workspace_backup_snapshot,
    get_restoreable_personal_workspace,
    list_workspace_backups,
    restore_workspace_backup,
)
from ace_platform.core.workspaces import create_workspace
from ace_platform.db.models import (
    ApiKey,
    Base,
    MembershipRole,
    OAuthProvider,
    Playbook,
    PlaybookSource,
    PlaybookStatus,
    PlaybookVersion,
    SubscriptionStatus,
    UsageRecord,
    User,
    UserOAuthAccount,
    Workspace,
    WorkspaceDeploymentMode,
    WorkspacePlan,
)


class TestWorkspaceBackups:
    @pytest.fixture(scope="function")
    async def async_engine(self):
        schema_name = f"workspace_backup_test_{uuid4().hex}"
        admin_engine = create_async_engine(
            TEST_DATABASE_URL_ASYNC,
            echo=False,
            poolclass=NullPool,
        )

        async with admin_engine.begin() as conn:
            await conn.execute(text(f"CREATE SCHEMA {schema_name}"))

        await admin_engine.dispose()

        engine = create_async_engine(
            TEST_DATABASE_URL_ASYNC,
            echo=False,
            poolclass=NullPool,
            connect_args={"server_settings": {"search_path": schema_name}},
        )

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        yield engine

        await engine.dispose()

        cleanup_engine = create_async_engine(
            TEST_DATABASE_URL_ASYNC,
            echo=False,
            poolclass=NullPool,
        )

        async with cleanup_engine.begin() as conn:
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))

        await cleanup_engine.dispose()

    @pytest.fixture
    async def async_session(self, async_engine):
        session_maker = async_sessionmaker(
            bind=async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with session_maker() as session:
            yield session

    async def _create_user(self, async_session: AsyncSession, email: str) -> User:
        user = User(
            email=email,
            hashed_password=hash_password("password123"),
            is_active=True,
            email_verified=True,
            subscription_tier="starter",
            subscription_status=SubscriptionStatus.ACTIVE,
            has_payment_method=True,
            stripe_default_payment_method_id="pm_test",
        )
        async_session.add(user)
        await async_session.flush()
        return user

    async def _create_workspace_with_content(
        self,
        async_session: AsyncSession,
        *,
        email: str = "backup-owner@example.com",
    ) -> tuple[User, Workspace]:
        user = await self._create_user(async_session, email)
        workspace = await create_workspace(
            async_session,
            owner_user=user,
            name="Backup Workspace",
            plan=WorkspacePlan.PERSONAL,
            deployment_mode=WorkspaceDeploymentMode.CLOUD,
            seat_limit=1,
        )
        await async_session.flush()

        playbook = Playbook(
            user_id=user.id,
            name="Workspace Playbook",
            description="restorable",
            status=PlaybookStatus.ACTIVE,
            source=PlaybookSource.USER_CREATED,
        )
        async_session.add(playbook)
        await async_session.flush()

        version = PlaybookVersion(
            playbook_id=playbook.id,
            version_number=1,
            content="restore me",
            bullet_count=1,
        )
        async_session.add(version)
        await async_session.flush()
        playbook.current_version_id = version.id

        async_session.add(
            UsageRecord(
                user_id=user.id,
                playbook_id=playbook.id,
                operation="evolution_generation",
                model="gpt-5.2",
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
                cost_usd=Decimal("0.42"),
                request_id=str(uuid4()),
            )
        )
        async_session.add(
            ApiKey(
                user_id=user.id,
                name="Backup key",
                key_prefix="ace_test",
                hashed_key="hashed-key",
                scopes=["read", "write"],
            )
        )
        async_session.add(
            UserOAuthAccount(
                user_id=user.id,
                provider=OAuthProvider.GITHUB,
                provider_user_id="github-123",
                provider_email=user.email,
                access_token="token",
                refresh_token="refresh",
            )
        )
        await async_session.commit()
        return user, workspace

    @pytest.mark.asyncio
    async def test_backup_sweep_creates_backups_for_eligible_hosted_personal_workspaces(
        self,
        async_session: AsyncSession,
    ) -> None:
        _, workspace = await self._create_workspace_with_content(async_session)

        summary = await backup_hosted_personal_workspaces(async_session)
        await async_session.commit()

        backups = await list_workspace_backups(async_session, workspace.id)

        assert summary == {"workspace_count": 1, "backups_created": 1}
        assert len(backups) == 1
        assert backups[0].trigger_source == "scheduled"

    @pytest.mark.asyncio
    async def test_create_workspace_backup_snapshot_enforces_retention(
        self,
        async_session: AsyncSession,
    ) -> None:
        _, workspace = await self._create_workspace_with_content(
            async_session,
            email="retention-owner@example.com",
        )

        for _ in range(WORKSPACE_BACKUP_RETENTION_COUNT + 2):
            loaded_workspace = await get_restoreable_personal_workspace(async_session, workspace.id)
            assert loaded_workspace is not None
            await create_workspace_backup_snapshot(
                async_session,
                loaded_workspace,
                trigger_source="scheduled",
            )
            await async_session.commit()

        backups = await list_workspace_backups(async_session, workspace.id, limit=50)

        assert len(backups) == WORKSPACE_BACKUP_RETENTION_COUNT

    @pytest.mark.asyncio
    async def test_restore_workspace_backup_restores_deleted_personal_data(
        self,
        async_session: AsyncSession,
    ) -> None:
        user, workspace = await self._create_workspace_with_content(
            async_session,
            email="restore-owner@example.com",
        )
        loaded_workspace = await get_restoreable_personal_workspace(async_session, workspace.id)
        assert loaded_workspace is not None

        backup = await create_workspace_backup_snapshot(
            async_session,
            loaded_workspace,
            trigger_source="admin_manual",
        )
        await async_session.commit()

        workspace_result = await async_session.execute(
            select(Workspace).where(Workspace.id == workspace.id)
        )
        workspace_row = workspace_result.scalar_one()
        workspace_row.name = "Lost Workspace"

        playbooks_result = await async_session.execute(
            select(Playbook).where(Playbook.user_id == user.id)
        )
        for playbook in playbooks_result.scalars().all():
            await async_session.delete(playbook)

        usage_result = await async_session.execute(
            select(UsageRecord).where(UsageRecord.user_id == user.id)
        )
        for usage_record in usage_result.scalars().all():
            await async_session.delete(usage_record)

        user.subscription_tier = None
        loaded_workspace.entitlements.hosted_backups = False
        await async_session.commit()

        await async_session.delete(workspace_row)
        await async_session.delete(user)
        await async_session.commit()

        result = await restore_workspace_backup(async_session, backup)
        await async_session.commit()

        restored_workspace = await get_restoreable_personal_workspace(async_session, workspace.id)
        restored_user = await async_session.get(User, user.id)
        restored_playbooks = (
            (await async_session.execute(select(Playbook).where(Playbook.user_id == user.id)))
            .scalars()
            .all()
        )
        restored_usage = (
            (await async_session.execute(select(UsageRecord).where(UsageRecord.user_id == user.id)))
            .scalars()
            .all()
        )
        restored_api_keys = (
            (await async_session.execute(select(ApiKey).where(ApiKey.user_id == user.id)))
            .scalars()
            .all()
        )
        restored_oauth_accounts = (
            (
                await async_session.execute(
                    select(UserOAuthAccount).where(UserOAuthAccount.user_id == user.id)
                )
            )
            .scalars()
            .all()
        )

        assert result["workspace_id"] == str(workspace.id)
        assert result["backup_id"] == str(backup.id)
        assert result["restored_playbooks"] == 1
        assert result["restored_usage_records"] == 1
        assert result["restored_api_keys"] == 1
        assert result["restored_oauth_accounts"] == 1
        assert restored_user is not None
        assert restored_user.hashed_password is not None
        assert restored_user.subscription_tier == "starter"
        assert restored_user.stripe_default_payment_method_id == "pm_test"
        assert restored_workspace is not None
        assert restored_workspace.name == "Backup Workspace"
        assert restored_workspace.entitlements is not None
        assert restored_workspace.entitlements.hosted_backups is True
        assert restored_playbooks[0].name == "Workspace Playbook"
        assert len(restored_usage) == 1
        assert restored_usage[0].playbook_id == restored_playbooks[0].id
        assert len(restored_api_keys) == 1
        assert restored_api_keys[0].hashed_key == "hashed-key"
        assert len(restored_oauth_accounts) == 1
        assert restored_oauth_accounts[0].provider == OAuthProvider.GITHUB
        assert restored_workspace.memberships[0].role == MembershipRole.OWNER
