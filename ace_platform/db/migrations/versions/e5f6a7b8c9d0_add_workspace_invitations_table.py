"""add workspace invitations table

Revision ID: e5f6a7b8c9d0
Revises: 4f0f8a7c6b21
Create Date: 2026-03-18 08:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | Sequence[str] | None = "4f0f8a7c6b21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    membership_role_enum = postgresql.ENUM(
        "OWNER",
        "MEMBER",
        "REVIEWER",
        "ADMIN",
        name="membershiprole",
        create_type=False,
    )

    op.create_table(
        "workspace_invitations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("invited_by_user_id", sa.UUID(), nullable=False),
        sa.Column("invited_email", sa.String(length=255), nullable=False),
        sa.Column("role", membership_role_enum, nullable=False),
        sa.Column("accepted_by_user_id", sa.UUID(), nullable=True),
        sa.Column("revoked_by_user_id", sa.UUID(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workspace_invitations_invited_email",
        "workspace_invitations",
        ["invited_email"],
        unique=False,
    )
    op.create_index(
        "ix_workspace_invitations_workspace_email",
        "workspace_invitations",
        ["workspace_id", "invited_email"],
        unique=False,
    )
    op.create_index(
        "ix_workspace_invitations_workspace_created_at",
        "workspace_invitations",
        ["workspace_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        "ix_workspace_invitations_workspace_created_at",
        table_name="workspace_invitations",
    )
    op.drop_index(
        "ix_workspace_invitations_workspace_email",
        table_name="workspace_invitations",
    )
    op.drop_index(
        "ix_workspace_invitations_invited_email",
        table_name="workspace_invitations",
    )
    op.drop_table("workspace_invitations")
