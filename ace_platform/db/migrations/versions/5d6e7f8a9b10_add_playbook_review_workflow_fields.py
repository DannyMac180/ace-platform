"""Add playbook review workflow fields.

Revision ID: 5d6e7f8a9b10
Revises: 4f0f8a7c6b21
Create Date: 2026-03-18 09:05:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "5d6e7f8a9b10"
down_revision: str | Sequence[str] | None = "4f0f8a7c6b21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


review_status_enum = postgresql.ENUM(
    "draft",
    "proposed",
    "approved",
    "archived",
    name="playbookreviewstatus",
)


def upgrade() -> None:
    """Upgrade schema."""

    bind = op.get_bind()
    review_status_enum.create(bind, checkfirst=True)

    op.add_column(
        "playbooks",
        sa.Column(
            "review_status",
            review_status_enum,
            nullable=False,
            server_default=sa.text("'draft'"),
        ),
    )
    op.add_column(
        "playbooks",
        sa.Column(
            "review_status_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "playbooks",
        sa.Column(
            "review_history",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )

    op.execute(
        """
        UPDATE playbooks
        SET review_status = CASE
            WHEN lower(status::text) = 'archived' THEN 'archived'::playbookreviewstatus
            ELSE 'approved'::playbookreviewstatus
        END,
            review_status_updated_at = COALESCE(updated_at, created_at, now()),
            review_history = '[]'::jsonb
        """
    )

    op.alter_column(
        "playbooks",
        "review_status",
        server_default=sa.text("'draft'"),
    )
    op.alter_column(
        "playbooks",
        "review_status_updated_at",
        nullable=False,
        server_default=sa.text("now()"),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column("playbooks", "review_history")
    op.drop_column("playbooks", "review_status_updated_at")
    op.drop_column("playbooks", "review_status")
    review_status_enum.drop(op.get_bind(), checkfirst=True)
