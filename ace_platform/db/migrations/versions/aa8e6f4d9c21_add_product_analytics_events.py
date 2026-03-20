"""add product analytics events

Revision ID: aa8e6f4d9c21
Revises: 20747cd81fef
Create Date: 2026-03-20 18:55:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "aa8e6f4d9c21"
down_revision: str | Sequence[str] | None = "20747cd81fef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    for value in (
        "CLI_INIT_COMPLETED",
        "CLI_SEED_COMPLETED",
        "CLI_BENCHMARK_COMPLETED",
        "UPGRADE_COMPLETED",
        "RETENTION_ACTIVE",
    ):
        op.execute(f"ALTER TYPE acquisitioneventtype ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    """Downgrade schema.

    PostgreSQL enum values are intentionally left in place because removing them
    requires a type rebuild and data rewrite.
    """
