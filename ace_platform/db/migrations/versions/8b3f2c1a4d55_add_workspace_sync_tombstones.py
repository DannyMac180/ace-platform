"""add workspace sync tombstones

Revision ID: 8b3f2c1a4d55
Revises: 7c4a8d9e1f20
Create Date: 2026-03-17 20:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8b3f2c1a4d55"
down_revision: str | Sequence[str] | None = "7c4a8d9e1f20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "workspace_sync_tombstones",
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column(
            "deleted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("workspace_id", "entity_type", "entity_id"),
    )
    op.create_index(
        "ix_workspace_sync_tombstones_deleted_at",
        "workspace_sync_tombstones",
        ["deleted_at"],
        unique=False,
    )
    op.create_index(
        "ix_workspace_sync_tombstones_workspace_deleted_at",
        "workspace_sync_tombstones",
        ["workspace_id", "deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        "ix_workspace_sync_tombstones_workspace_deleted_at",
        table_name="workspace_sync_tombstones",
    )
    op.drop_index(
        "ix_workspace_sync_tombstones_deleted_at",
        table_name="workspace_sync_tombstones",
    )
    op.drop_table("workspace_sync_tombstones")
