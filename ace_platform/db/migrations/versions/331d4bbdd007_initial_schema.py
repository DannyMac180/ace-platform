"""Initial schema

Revision ID: 331d4bbdd007
Revises:
Create Date: 2025-12-22 12:57:43.442976

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "331d4bbdd007"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create tables in dependency order, deferring circular FKs

    # 1. Users table (no dependencies)
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # 2. API keys (depends on users)
    op.create_table(
        "api_keys",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("key_prefix", sa.String(length=8), nullable=False),
        sa.Column("hashed_key", sa.String(length=255), nullable=False),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_api_keys_user_id"), "api_keys", ["user_id"], unique=False)

    # 3. Playbooks (depends on users, deferred FK to playbook_versions)
    op.create_table(
        "playbooks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("current_version_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.Enum("ACTIVE", "ARCHIVED", name="playbookstatus"), nullable=False),
        sa.Column(
            "source",
            sa.Enum("STARTER", "USER_CREATED", "IMPORTED", name="playbooksource"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_playbooks_user_id"), "playbooks", ["user_id"], unique=False)

    # 4. Evolution jobs (depends on playbooks, deferred FKs to playbook_versions)
    op.create_table(
        "evolution_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("playbook_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("QUEUED", "RUNNING", "COMPLETED", "FAILED", name="evolutionjobstatus"),
            nullable=False,
        ),
        sa.Column("from_version_id", sa.UUID(), nullable=True),
        sa.Column("to_version_id", sa.UUID(), nullable=True),
        sa.Column("outcomes_processed", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("token_totals", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ace_core_version", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["playbook_id"], ["playbooks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_evolution_jobs_playbook_id"), "evolution_jobs", ["playbook_id"], unique=False
    )
    op.create_index(
        "ix_evolution_jobs_active_per_playbook",
        "evolution_jobs",
        ["playbook_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING')"),
    )

    # 5. Playbook versions (depends on playbooks and evolution_jobs)
    op.create_table(
        "playbook_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("playbook_id", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("bullet_count", sa.Integer(), nullable=False),
        sa.Column("created_by_job_id", sa.UUID(), nullable=True),
        sa.Column("diff_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_job_id"], ["evolution_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["playbook_id"], ["playbooks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("playbook_id", "version_number", name="uq_playbook_version"),
    )
    op.create_index(
        op.f("ix_playbook_versions_playbook_id"), "playbook_versions", ["playbook_id"], unique=False
    )
    op.create_index(
        "ix_playbook_versions_playbook_version",
        "playbook_versions",
        ["playbook_id", "version_number"],
        unique=False,
    )

    # 6. Outcomes (depends on playbooks and evolution_jobs)
    op.create_table(
        "outcomes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("playbook_id", sa.UUID(), nullable=False),
        sa.Column("task_description", sa.Text(), nullable=False),
        sa.Column(
            "outcome_status",
            sa.Enum("SUCCESS", "FAILURE", "PARTIAL", name="outcomestatus"),
            nullable=False,
        ),
        sa.Column("reasoning_trace", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("reflection_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evolution_job_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["evolution_job_id"], ["evolution_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["playbook_id"], ["playbooks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_outcomes_playbook_id"), "outcomes", ["playbook_id"], unique=False)
    op.create_index(
        "ix_outcomes_playbook_unprocessed",
        "outcomes",
        ["playbook_id", "processed_at"],
        unique=False,
    )

    # 7. Usage records (depends on users, playbooks, evolution_jobs)
    op.create_table(
        "usage_records",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("playbook_id", sa.UUID(), nullable=True),
        sa.Column("evolution_job_id", sa.UUID(), nullable=True),
        sa.Column("operation", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column("request_id", sa.String(length=100), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["evolution_job_id"], ["evolution_jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["playbook_id"], ["playbooks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_usage_records_user_created", "usage_records", ["user_id", "created_at"], unique=False
    )
    op.create_index(op.f("ix_usage_records_user_id"), "usage_records", ["user_id"], unique=False)

    # 8. Add deferred foreign keys for circular references
    op.create_foreign_key(
        "fk_playbooks_current_version",
        "playbooks",
        "playbook_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_evolution_jobs_from_version",
        "evolution_jobs",
        "playbook_versions",
        ["from_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_evolution_jobs_to_version",
        "evolution_jobs",
        "playbook_versions",
        ["to_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop deferred foreign keys first
    op.drop_constraint("fk_evolution_jobs_to_version", "evolution_jobs", type_="foreignkey")
    op.drop_constraint("fk_evolution_jobs_from_version", "evolution_jobs", type_="foreignkey")
    op.drop_constraint("fk_playbooks_current_version", "playbooks", type_="foreignkey")

    # Drop tables in reverse order
    op.drop_index(op.f("ix_usage_records_user_id"), table_name="usage_records")
    op.drop_index("ix_usage_records_user_created", table_name="usage_records")
    op.drop_table("usage_records")

    op.drop_index("ix_outcomes_playbook_unprocessed", table_name="outcomes")
    op.drop_index(op.f("ix_outcomes_playbook_id"), table_name="outcomes")
    op.drop_table("outcomes")

    op.drop_index("ix_playbook_versions_playbook_version", table_name="playbook_versions")
    op.drop_index(op.f("ix_playbook_versions_playbook_id"), table_name="playbook_versions")
    op.drop_table("playbook_versions")

    op.drop_index(
        "ix_evolution_jobs_active_per_playbook",
        table_name="evolution_jobs",
        postgresql_where=sa.text("status IN ('QUEUED', 'RUNNING')"),
    )
    op.drop_index(op.f("ix_evolution_jobs_playbook_id"), table_name="evolution_jobs")
    op.drop_table("evolution_jobs")

    op.drop_index(op.f("ix_playbooks_user_id"), table_name="playbooks")
    op.drop_table("playbooks")

    op.drop_index(op.f("ix_api_keys_user_id"), table_name="api_keys")
    op.drop_table("api_keys")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")

    # Drop enum types
    sa.Enum(name="outcomestatus").drop(op.get_bind())
    sa.Enum(name="playbooksource").drop(op.get_bind())
    sa.Enum(name="playbookstatus").drop(op.get_bind())
    sa.Enum(name="evolutionjobstatus").drop(op.get_bind())
