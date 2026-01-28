"""Add audit_logs table

Revision ID: 98784145c9db
Revises: 3ec01c856a41
Create Date: 2026-01-28 09:32:22.249766

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "98784145c9db"
down_revision: str | Sequence[str] | None = "3ec01c856a41"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create enum types first
    auditeventtype = sa.Enum(
        "LOGIN_SUCCESS",
        "LOGIN_FAILURE",
        "LOGOUT",
        "OAUTH_LOGIN_SUCCESS",
        "OAUTH_LOGIN_FAILURE",
        "PASSWORD_CHANGE",
        "PASSWORD_RESET_REQUEST",
        "PASSWORD_RESET_COMPLETE",
        "EMAIL_VERIFICATION_SENT",
        "EMAIL_VERIFIED",
        "API_KEY_CREATED",
        "API_KEY_REVOKED",
        "ACCOUNT_CREATED",
        "ACCOUNT_LOCKED",
        "ACCOUNT_UNLOCKED",
        "PERMISSION_DENIED",
        "SUBSCRIPTION_CREATED",
        "SUBSCRIPTION_UPDATED",
        "SUBSCRIPTION_CANCELED",
        "PAYMENT_METHOD_ADDED",
        "PAYMENT_METHOD_REMOVED",
        "OAUTH_ACCOUNT_LINKED",
        "OAUTH_ACCOUNT_UNLINKED",
        name="auditeventtype",
    )
    auditseverity = sa.Enum("INFO", "WARNING", "CRITICAL", name="auditseverity")

    # Create the audit_logs table
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("event_type", auditeventtype, nullable=False),
        sa.Column("severity", auditseverity, nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes
    op.create_index(op.f("ix_audit_logs_created_at"), "audit_logs", ["created_at"], unique=False)
    op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"], unique=False)
    op.create_index(
        "ix_audit_logs_severity_created", "audit_logs", ["severity", "created_at"], unique=False
    )
    op.create_index(
        "ix_audit_logs_user_created", "audit_logs", ["user_id", "created_at"], unique=False
    )
    op.create_index(op.f("ix_audit_logs_user_id"), "audit_logs", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index(op.f("ix_audit_logs_user_id"), table_name="audit_logs")
    op.drop_index("ix_audit_logs_user_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_severity_created", table_name="audit_logs")
    op.drop_index("ix_audit_logs_event_type", table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_created_at"), table_name="audit_logs")

    # Drop table
    op.drop_table("audit_logs")

    # Drop enum types
    sa.Enum(name="auditseverity").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="auditeventtype").drop(op.get_bind(), checkfirst=True)
