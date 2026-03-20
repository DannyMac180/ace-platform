"""merge workspace schema heads

Revision ID: c4d5e6f7a8b9
Revises: 8b3f2c1a4d55, 8f91c2d4ab12
Create Date: 2026-03-17 20:45:00.000000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: str | Sequence[str] | None = ("8b3f2c1a4d55", "8f91c2d4ab12")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Merge concurrent workspace schema heads."""


def downgrade() -> None:
    """Unmerge concurrent workspace schema heads."""
