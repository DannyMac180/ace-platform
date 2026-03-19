"""merge playbook review and workspace invitation heads

Revision ID: 6f7a8b9c0d1e
Revises: 5d6e7f8a9b10, e5f6a7b8c9d0
Create Date: 2026-03-19 11:20:00.000000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "6f7a8b9c0d1e"
down_revision: str | Sequence[str] | None = ("5d6e7f8a9b10", "e5f6a7b8c9d0")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
