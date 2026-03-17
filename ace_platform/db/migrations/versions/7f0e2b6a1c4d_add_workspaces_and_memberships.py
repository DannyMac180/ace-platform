"""Add workspaces and memberships with existing-user backfill

Revision ID: 7f0e2b6a1c4d
Revises: 6b9a3f2d1c7e
Create Date: 2026-03-17

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7f0e2b6a1c4d"
down_revision: str | Sequence[str] | None = "6b9a3f2d1c7e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

workspaceplan_enum = postgresql.ENUM(
    "personal",
    "team",
    "enterprise",
    name="workspaceplan",
    create_type=False,
)
workspacedeploymentmode_enum = postgresql.ENUM(
    "cloud",
    "self_hosted",
    name="workspacedeploymentmode",
    create_type=False,
)
workspacerole_enum = postgresql.ENUM(
    "owner",
    "member",
    "reviewer",
    "admin",
    name="workspacerole",
    create_type=False,
)


def _personal_workspace_name(email: str | None) -> str:
    """Build a stable personal-workspace name from an email address."""
    if not email:
        return "Personal Workspace"

    local_part = email.split("@", 1)[0]
    cleaned = local_part.replace(".", " ").replace("_", " ").replace("-", " ").strip()
    pretty_name = " ".join(part.capitalize() for part in cleaned.split())
    if pretty_name:
        return f"{pretty_name}'s Workspace"[:255]
    return "Personal Workspace"


def upgrade() -> None:
    """Create workspace tables and backfill personal workspaces for existing users."""
    bind = op.get_bind()

    workspaceplan_enum.create(bind, checkfirst=True)
    workspacedeploymentmode_enum.create(bind, checkfirst=True)
    workspacerole_enum.create(bind, checkfirst=True)

    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("plan", workspaceplan_enum, nullable=False, server_default="personal"),
        sa.Column(
            "deployment_mode",
            workspacedeploymentmode_enum,
            nullable=False,
            server_default="cloud",
        ),
        sa.Column("seat_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_workspaces_plan", "workspaces", ["plan"], unique=False)
    op.create_index(
        "ix_workspaces_deployment_mode",
        "workspaces",
        ["deployment_mode"],
        unique=False,
    )

    op.create_table(
        "workspace_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", workspacerole_enum, nullable=False, server_default="member"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            name="uq_workspace_memberships_workspace_user",
        ),
    )
    op.create_index(
        "ix_workspace_memberships_workspace_user",
        "workspace_memberships",
        ["workspace_id", "user_id"],
        unique=False,
    )
    op.create_index(
        "ix_workspace_memberships_user_workspace",
        "workspace_memberships",
        ["user_id", "workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_workspace_memberships_workspace_id",
        "workspace_memberships",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_workspace_memberships_user_id",
        "workspace_memberships",
        ["user_id"],
        unique=False,
    )

    workspace_table = sa.table(
        "workspaces",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String(length=255)),
        sa.column("plan", workspaceplan_enum),
        sa.column("deployment_mode", workspacedeploymentmode_enum),
        sa.column("seat_limit", sa.Integer()),
    )
    membership_table = sa.table(
        "workspace_memberships",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("workspace_id", postgresql.UUID(as_uuid=True)),
        sa.column("user_id", postgresql.UUID(as_uuid=True)),
        sa.column("role", workspacerole_enum),
    )

    existing_users = bind.execute(sa.text("SELECT id, email FROM users")).mappings().all()
    for user in existing_users:
        workspace_id = uuid4()
        bind.execute(
            workspace_table.insert().values(
                id=workspace_id,
                name=_personal_workspace_name(user["email"]),
                plan="personal",
                deployment_mode="cloud",
                seat_limit=1,
            )
        )
        bind.execute(
            membership_table.insert().values(
                id=uuid4(),
                workspace_id=workspace_id,
                user_id=user["id"],
                role="owner",
            )
        )


def downgrade() -> None:
    """Drop workspace tables and enums."""
    op.drop_index("ix_workspace_memberships_user_id", table_name="workspace_memberships")
    op.drop_index("ix_workspace_memberships_workspace_id", table_name="workspace_memberships")
    op.drop_index(
        "ix_workspace_memberships_user_workspace",
        table_name="workspace_memberships",
    )
    op.drop_index(
        "ix_workspace_memberships_workspace_user",
        table_name="workspace_memberships",
    )
    op.drop_table("workspace_memberships")

    op.drop_index("ix_workspaces_deployment_mode", table_name="workspaces")
    op.drop_index("ix_workspaces_plan", table_name="workspaces")
    op.drop_table("workspaces")

    workspacerole_enum.drop(op.get_bind(), checkfirst=True)
    workspacedeploymentmode_enum.drop(op.get_bind(), checkfirst=True)
    workspaceplan_enum.drop(op.get_bind(), checkfirst=True)
