"""add_subscription_fields_to_user

Revision ID: c7bacc87916a
Revises: 331d4bbdd007
Create Date: 2025-12-24 14:15:20.980904

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7bacc87916a"
down_revision: str | Sequence[str] | None = "331d4bbdd007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create the enum type first
    subscriptionstatus_enum = sa.Enum(
        "NONE", "ACTIVE", "PAST_DUE", "CANCELED", "UNPAID", name="subscriptionstatus"
    )
    subscriptionstatus_enum.create(op.get_bind(), checkfirst=True)

    # Add columns
    op.add_column(
        "users", sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True)
    )
    op.add_column("users", sa.Column("subscription_tier", sa.String(length=50), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "subscription_status",
            subscriptionstatus_enum,
            nullable=False,
            server_default="NONE",
        ),
    )
    op.add_column(
        "users",
        sa.Column("subscription_current_period_end", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop columns first
    op.drop_column("users", "subscription_current_period_end")
    op.drop_column("users", "subscription_status")
    op.drop_column("users", "subscription_tier")
    op.drop_column("users", "stripe_subscription_id")

    # Drop the enum type
    subscriptionstatus_enum = sa.Enum(name="subscriptionstatus")
    subscriptionstatus_enum.drop(op.get_bind(), checkfirst=True)
