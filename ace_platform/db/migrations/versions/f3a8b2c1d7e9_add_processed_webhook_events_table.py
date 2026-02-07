"""Add processed webhook events table for idempotency

Revision ID: f3a8b2c1d7e9
Revises: d1f6b6a2c4aa
Create Date: 2026-02-07

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a8b2c1d7e9"
down_revision: str | Sequence[str] | None = "d1f6b6a2c4aa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create processed_webhook_events table."""
    op.create_table(
        "processed_webhook_events",
        sa.Column("stripe_event_id", sa.String(255), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Drop processed_webhook_events table."""
    op.drop_table("processed_webhook_events")
