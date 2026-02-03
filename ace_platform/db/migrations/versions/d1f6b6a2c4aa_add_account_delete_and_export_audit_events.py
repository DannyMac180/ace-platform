"""Add account deletion and data export audit events

Revision ID: d1f6b6a2c4aa
Revises: 98784145c9db
Create Date: 2026-02-03

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1f6b6a2c4aa"
down_revision: str | Sequence[str] | None = "98784145c9db"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE auditeventtype ADD VALUE 'ACCOUNT_DELETED'")
    op.execute("ALTER TYPE auditeventtype ADD VALUE 'DATA_EXPORTED'")


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres enum values cannot be removed safely in a downgrade.
    pass
