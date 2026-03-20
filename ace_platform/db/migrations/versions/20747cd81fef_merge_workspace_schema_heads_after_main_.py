"""merge workspace schema heads after main sync

Revision ID: 20747cd81fef
Revises: 6f7a8b9c0d1e, 7d4c8f1a2b3c
Create Date: 2026-03-20 10:18:43.589997

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "20747cd81fef"
down_revision: str | Sequence[str] | None = ("6f7a8b9c0d1e", "7d4c8f1a2b3c")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
