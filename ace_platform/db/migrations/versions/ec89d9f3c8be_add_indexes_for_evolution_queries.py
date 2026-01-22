"""add_indexes_for_evolution_queries

Revision ID: ec89d9f3c8be
Revises: 9ba7f675a412
Create Date: 2026-01-22 15:30:14.229537

Add indexes to optimize evolution statistics queries:
- idx_evolution_job_started_at: For date range filtering
- idx_evolution_job_playbook_started: For playbook + date queries

These indexes significantly improve performance of the /evolutions/* API endpoints
which aggregate evolution job data by date ranges and playbooks.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ec89d9f3c8be"
down_revision: str | Sequence[str] | None = "9ba7f675a412"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema - add indexes for evolution queries."""
    # Index for filtering by started_at (used in all evolution stats queries)
    op.create_index(
        "idx_evolution_job_started_at",
        "evolution_jobs",
        ["started_at"],
        unique=False,
    )

    # Composite index for playbook + started_at queries (used in aggregations)
    op.create_index(
        "idx_evolution_job_playbook_started",
        "evolution_jobs",
        ["playbook_id", "started_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema - remove indexes."""
    op.drop_index("idx_evolution_job_playbook_started", table_name="evolution_jobs")
    op.drop_index("idx_evolution_job_started_at", table_name="evolution_jobs")
