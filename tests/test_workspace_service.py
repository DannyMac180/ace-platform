"""Tests for workspace service helpers."""

import os

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from ace_platform.core.security import hash_password
from ace_platform.core.workspaces import (
    accept_workspace_invitation,
    add_workspace_member,
    bootstrap_workspace_for_user,
    create_workspace,
    create_workspace_invitation,
    delete_workspace,
    list_user_workspaces,
    normalize_workspace_inference_config,
    remove_workspace_membership,
    update_workspace,
)
from ace_platform.db.models import (
    Base,
    User,
    Workspace,
    WorkspaceDeploymentMode,
    WorkspaceInferenceMode,
    WorkspaceInferenceProvider,
    WorkspaceInvitation,
    WorkspacePlan,
    WorkspaceRole,
)

RUN_INTEGRATION_TESTS = os.environ.get("RUN_WORKSPACE_INTEGRATION_TESTS") == "1"
TEST_DATABASE_URL_ASYNC = os.environ.get(
    "TEST_DATABASE_URL_ASYNC",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/ace_platform_test",
)


@pytest.mark.skipif(
    not RUN_INTEGRATION_TESTS,
    reason="Set RUN_WORKSPACE_INTEGRATION_TESTS=1 to run workspace integration tests",
)
class TestWorkspaceService:
    """Integration tests for workspace service invariants."""

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
        )
        async_session.add(user)
        await async_session.commit()
        await async_session.refresh(user)
        return user

    async def test_bootstrap_creates_personal_workspace(self, async_session: AsyncSession):
        user = await self._create_user(async_session, "bootstrap-service@example.com")

        workspace, created = await bootstrap_workspace_for_user(async_session, user)
        await async_session.commit()

        assert created is True
        assert workspace.plan == WorkspacePlan.PERSONAL
        assert workspace.deployment_mode == WorkspaceDeploymentMode.CLOUD
        assert workspace.seat_limit == 1
        assert workspace.inference_config == {
            "mode": WorkspaceInferenceMode.MANAGED_PROVIDER.value,
            "provider": WorkspaceInferenceProvider.OPENAI.value,
        }

        workspaces = await list_user_workspaces(async_session, user.id)
        assert len(workspaces) == 1
        assert workspaces[0].memberships[0].role == WorkspaceRole.OWNER

    async def test_bootstrap_is_idempotent(self, async_session: AsyncSession):
        user = await self._create_user(async_session, "bootstrap-idempotent@example.com")

        first_workspace, first_created = await bootstrap_workspace_for_user(async_session, user)
        second_workspace, second_created = await bootstrap_workspace_for_user(async_session, user)
        await async_session.commit()

        assert first_created is True
        assert second_created is False
        assert first_workspace.id == second_workspace.id

    async def test_add_workspace_member_enforces_seat_limit(self, async_session: AsyncSession):
        owner = await self._create_user(async_session, "seat-owner@example.com")
        teammate = await self._create_user(async_session, "seat-teammate@example.com")

        workspace = await create_workspace(
            async_session,
            owner_user=owner,
            name="Personal Seat Limit",
            plan=WorkspacePlan.PERSONAL,
            deployment_mode=WorkspaceDeploymentMode.CLOUD,
            seat_limit=1,
        )
        await async_session.commit()

        with pytest.raises(ValueError, match="seat limit"):
            await add_workspace_member(
                async_session,
                workspace=workspace,
                user=teammate,
                role=WorkspaceRole.MEMBER,
            )

    async def test_add_workspace_member_counts_pending_invitations(
        self, async_session: AsyncSession
    ):
        owner = await self._create_user(async_session, "invite-seat-owner@example.com")
        teammate = await self._create_user(async_session, "invite-seat-teammate@example.com")

        workspace = await create_workspace(
            async_session,
            owner_user=owner,
            name="Reserved Seat Limit",
            plan=WorkspacePlan.TEAM,
            deployment_mode=WorkspaceDeploymentMode.CLOUD,
            seat_limit=2,
        )
        await async_session.refresh(workspace, ["entitlements"])
        await create_workspace_invitation(
            async_session,
            workspace=workspace,
            invited_by_user=owner,
            invited_email="reserved-seat@example.com",
            role=WorkspaceRole.MEMBER,
        )
        await async_session.commit()

        with pytest.raises(ValueError, match="seat limit"):
            await add_workspace_member(
                async_session,
                workspace=workspace,
                user=teammate,
                role=WorkspaceRole.MEMBER,
            )

    async def test_accept_workspace_invitation_uses_reserved_seat(
        self,
        async_session: AsyncSession,
    ):
        owner = await self._create_user(async_session, "accept-seat-owner@example.com")
        invited_user = await self._create_user(async_session, "accept-seat-user@example.com")

        workspace = await create_workspace(
            async_session,
            owner_user=owner,
            name="Accept Reserved Seat",
            plan=WorkspacePlan.TEAM,
            deployment_mode=WorkspaceDeploymentMode.CLOUD,
            seat_limit=2,
        )
        await async_session.refresh(workspace, ["entitlements"])
        invitation = await create_workspace_invitation(
            async_session,
            workspace=workspace,
            invited_by_user=owner,
            invited_email=invited_user.email,
            role=WorkspaceRole.MEMBER,
        )

        membership = await accept_workspace_invitation(
            async_session,
            invitation=invitation,
            user=invited_user,
        )
        await async_session.commit()

        assert membership.user_id == invited_user.id
        assert membership.workspace_id == workspace.id
        assert invitation.accepted_by_user_id == invited_user.id

    async def test_workspace_invitation_unique_index_blocks_duplicate_active_invites(
        self,
        async_session: AsyncSession,
    ):
        owner = await self._create_user(async_session, "invite-unique-owner@example.com")

        workspace = await create_workspace(
            async_session,
            owner_user=owner,
            name="Invitation Uniqueness",
            plan=WorkspacePlan.TEAM,
            deployment_mode=WorkspaceDeploymentMode.CLOUD,
            seat_limit=3,
        )

        async_session.add_all(
            [
                WorkspaceInvitation(
                    workspace_id=workspace.id,
                    invited_by_user_id=owner.id,
                    invited_email="duplicate-active@example.com",
                    role=WorkspaceRole.MEMBER,
                ),
                WorkspaceInvitation(
                    workspace_id=workspace.id,
                    invited_by_user_id=owner.id,
                    invited_email="duplicate-active@example.com",
                    role=WorkspaceRole.MEMBER,
                ),
            ]
        )

        with pytest.raises(IntegrityError):
            await async_session.commit()
        await async_session.rollback()

    async def test_update_workspace_falls_back_to_byo_when_managed_becomes_unsupported(
        self,
        async_session: AsyncSession,
    ):
        owner = await self._create_user(async_session, "inference-owner@example.com")

        workspace = await create_workspace(
            async_session,
            owner_user=owner,
            name="Inference Workspace",
            plan=WorkspacePlan.PERSONAL,
            deployment_mode=WorkspaceDeploymentMode.CLOUD,
            seat_limit=1,
        )
        await async_session.commit()

        await update_workspace(
            async_session,
            workspace,
            deployment_mode=WorkspaceDeploymentMode.SELF_HOSTED,
        )
        await async_session.commit()

        assert workspace.inference_config == {
            "mode": WorkspaceInferenceMode.BYO_PROVIDER.value,
            "provider": WorkspaceInferenceProvider.OPENAI.value,
        }

    async def test_remove_membership_rejects_last_workspace(self, async_session: AsyncSession):
        owner = await self._create_user(async_session, "remove-owner@example.com")

        await create_workspace(
            async_session,
            owner_user=owner,
            name="Single Membership",
            plan=WorkspacePlan.TEAM,
            deployment_mode=WorkspaceDeploymentMode.CLOUD,
            seat_limit=2,
        )
        await async_session.commit()

        memberships = (await list_user_workspaces(async_session, owner.id))[0].memberships
        with pytest.raises(ValueError, match="retain at least one owner"):
            await remove_workspace_membership(async_session, memberships[0])

    async def test_delete_workspace_rejects_stranding_member(self, async_session: AsyncSession):
        owner = await self._create_user(async_session, "delete-owner@example.com")
        member = await self._create_user(async_session, "delete-member@example.com")

        workspace = await create_workspace(
            async_session,
            owner_user=owner,
            name="Delete Guard",
            plan=WorkspacePlan.TEAM,
            deployment_mode=WorkspaceDeploymentMode.CLOUD,
            seat_limit=2,
        )
        await add_workspace_member(
            async_session,
            workspace=workspace,
            user=member,
            role=WorkspaceRole.MEMBER,
        )
        await async_session.commit()

        refreshed_workspace = (
            await async_session.execute(select(Workspace).where(Workspace.id == workspace.id))
        ).scalar_one()
        with pytest.raises(ValueError, match="without any workspace"):
            await delete_workspace(async_session, refreshed_workspace)


def test_normalize_workspace_inference_config_rejects_unsupported_managed_mode():
    with pytest.raises(ValueError, match="ACE-managed inference is not supported"):
        normalize_workspace_inference_config(
            plan=WorkspacePlan.ENTERPRISE,
            deployment_mode=WorkspaceDeploymentMode.SELF_HOSTED,
            inference_config={
                "mode": WorkspaceInferenceMode.MANAGED_PROVIDER.value,
                "provider": WorkspaceInferenceProvider.OPENAI.value,
            },
        )
