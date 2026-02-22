"""add acquisition tracking

Revision ID: 6b9a3f2d1c7e
Revises: 6422a448ddd6
Create Date: 2026-02-22 17:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "6b9a3f2d1c7e"
down_revision: str | Sequence[str] | None = "6422a448ddd6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


acquisition_event_type = sa.Enum(
    "LANDING_VIEW",
    "REGISTER_START",
    "REGISTER_SUBMIT",
    "REGISTER_STEP_TRANSITION",
    "REGISTER_SUCCESS",
    "TRIAL_CHECKOUT_INTENT",
    "TRIAL_STARTED",
    "FIRST_PLAYBOOK_CREATED",
    "EXPERIMENT_EXPOSURE",
    "HERO_VIDEO_LOADED",
    "HERO_VIDEO_PLAYED",
    "OAUTH_ERROR",
    "OAUTH_FALLBACK_USED",
    name="acquisitioneventtype",
)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("signup_source", sa.String(length=50), nullable=True))
    op.add_column("users", sa.Column("signup_channel", sa.String(length=50), nullable=True))
    op.add_column("users", sa.Column("signup_campaign", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("signup_anonymous_id", sa.String(length=128), nullable=True))
    op.add_column("users", sa.Column("signup_variant", sa.String(length=100), nullable=True))
    op.add_column(
        "users",
        sa.Column("signup_attribution", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index("ix_users_signup_source", "users", ["signup_source"], unique=False)
    op.create_index("ix_users_signup_anonymous_id", "users", ["signup_anonymous_id"], unique=False)
    op.create_index("ix_users_signup_variant", "users", ["signup_variant"], unique=False)

    op.create_table(
        "acquisition_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("event_type", acquisition_event_type, nullable=False),
        sa.Column("event_id", sa.String(length=128), nullable=True),
        sa.Column("anonymous_id", sa.String(length=128), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("channel", sa.String(length=50), nullable=True),
        sa.Column("campaign", sa.String(length=255), nullable=True),
        sa.Column("experiment_variant", sa.String(length=100), nullable=True),
        sa.Column("event_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id"),
    )

    op.create_index(
        "ix_acquisition_events_user_id", "acquisition_events", ["user_id"], unique=False
    )
    op.create_index(
        "ix_acquisition_events_event_type", "acquisition_events", ["event_type"], unique=False
    )
    op.create_index(
        "ix_acquisition_events_anonymous_id", "acquisition_events", ["anonymous_id"], unique=False
    )
    op.create_index("ix_acquisition_events_source", "acquisition_events", ["source"], unique=False)
    op.create_index(
        "ix_acquisition_events_experiment_variant",
        "acquisition_events",
        ["experiment_variant"],
        unique=False,
    )
    op.create_index(
        "ix_acquisition_events_created_at",
        "acquisition_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_acquisition_events_event_created",
        "acquisition_events",
        ["event_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_acquisition_events_source_created",
        "acquisition_events",
        ["source", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_acquisition_events_anon_created",
        "acquisition_events",
        ["anonymous_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_acquisition_events_user_created",
        "acquisition_events",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_acquisition_events_user_created", table_name="acquisition_events")
    op.drop_index("ix_acquisition_events_anon_created", table_name="acquisition_events")
    op.drop_index("ix_acquisition_events_source_created", table_name="acquisition_events")
    op.drop_index("ix_acquisition_events_event_created", table_name="acquisition_events")
    op.drop_index("ix_acquisition_events_created_at", table_name="acquisition_events")
    op.drop_index("ix_acquisition_events_experiment_variant", table_name="acquisition_events")
    op.drop_index("ix_acquisition_events_source", table_name="acquisition_events")
    op.drop_index("ix_acquisition_events_anonymous_id", table_name="acquisition_events")
    op.drop_index("ix_acquisition_events_event_type", table_name="acquisition_events")
    op.drop_index("ix_acquisition_events_user_id", table_name="acquisition_events")
    op.drop_table("acquisition_events")

    op.drop_index("ix_users_signup_variant", table_name="users")
    op.drop_index("ix_users_signup_anonymous_id", table_name="users")
    op.drop_index("ix_users_signup_source", table_name="users")
    op.drop_column("users", "signup_attribution")
    op.drop_column("users", "signup_variant")
    op.drop_column("users", "signup_anonymous_id")
    op.drop_column("users", "signup_campaign")
    op.drop_column("users", "signup_channel")
    op.drop_column("users", "signup_source")

    op.execute("DROP TYPE IF EXISTS acquisitioneventtype")
