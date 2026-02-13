"""add is_admin to users

Revision ID: 6422a448ddd6
Revises: 2f4c8f93d6ab
Create Date: 2026-02-13 16:41:53.328912

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6422a448ddd6"
down_revision: str | Sequence[str] | None = "2f4c8f93d6ab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "is_admin")
