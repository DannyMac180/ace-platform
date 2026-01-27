"""Add payment method tracking fields

Revision ID: a1b2c3d4e5f6
Revises: ec89d9f3c8be
Create Date: 2026-01-27 14:00:00.000000

Add fields to track whether a user has a payment method on file:
- has_payment_method: Boolean flag (default False)
- stripe_default_payment_method_id: Stripe payment method ID

These fields enable requiring a valid card before FREE tier users
can trigger evolutions, while still allowing them to explore the platform.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "ec89d9f3c8be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add payment method tracking fields to users table."""
    op.add_column(
        "users",
        sa.Column("has_payment_method", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "users",
        sa.Column("stripe_default_payment_method_id", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    """Remove payment method tracking fields from users table."""
    op.drop_column("users", "stripe_default_payment_method_id")
    op.drop_column("users", "has_payment_method")
