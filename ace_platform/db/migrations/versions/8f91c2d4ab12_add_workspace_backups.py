"""add workspace backups

Revision ID: 8f91c2d4ab12
Revises: 7c4a8d9e1f20
Create Date: 2026-03-17 20:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8f91c2d4ab12"
down_revision: str | Sequence[str] | None = "7c4a8d9e1f20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "workspace_backups",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=True),
        sa.Column("trigger_source", sa.String(length=50), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("backup_size_bytes", sa.Integer(), nullable=False),
        sa.Column("restored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workspace_backups_owner_user_id",
        "workspace_backups",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_workspace_backups_workspace_created",
        "workspace_backups",
        ["workspace_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workspace_backups_workspace_id"),
        "workspace_backups",
        ["workspace_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f("ix_workspace_backups_workspace_id"), table_name="workspace_backups")
    op.drop_index("ix_workspace_backups_workspace_created", table_name="workspace_backups")
    op.drop_index("ix_workspace_backups_owner_user_id", table_name="workspace_backups")
    op.drop_table("workspace_backups")
