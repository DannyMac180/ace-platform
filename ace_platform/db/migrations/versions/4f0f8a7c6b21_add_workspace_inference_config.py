"""Add workspace inference configuration.

Revision ID: 4f0f8a7c6b21
Revises: c4d5e6f7a8b9
Create Date: 2026-03-17 20:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "4f0f8a7c6b21"
down_revision: str | Sequence[str] | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "workspaces",
        sa.Column("inference_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.execute(
        """
        UPDATE workspaces
        SET inference_config = CASE
            WHEN deployment_mode = 'cloud' THEN
                '{"mode":"managed_provider","provider":"openai"}'::jsonb
            ELSE
                '{"mode":"byo_provider","provider":"openai"}'::jsonb
        END
        WHERE inference_config IS NULL
        """
    )
    op.alter_column("workspaces", "inference_config", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column("workspaces", "inference_config")
