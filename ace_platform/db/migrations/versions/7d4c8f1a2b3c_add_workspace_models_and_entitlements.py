"""add_workspace_models_and_entitlements

Revision ID: 7d4c8f1a2b3c
Revises: 6b9a3f2d1c7e
Create Date: 2026-03-17

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7d4c8f1a2b3c"
down_revision: str | Sequence[str] | None = "6b9a3f2d1c7e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


workspaceplan_enum = sa.Enum("PERSONAL", "TEAM", "ENTERPRISE", name="workspaceplan")
deploymentmode_enum = sa.Enum("LOCAL", "CLOUD", "SELF_HOSTED", name="deploymentmode")
membershiprole_enum = sa.Enum("OWNER", "MEMBER", "REVIEWER", "ADMIN", name="membershiprole")
billingprovider_enum = sa.Enum("STRIPE", "MANUAL", name="billingprovider")
workspacesubscriptionstatus_enum = sa.Enum(
    "TRIALING",
    "ACTIVE",
    "PAST_DUE",
    "CANCELED",
    "UNPAID",
    name="workspacesubscriptionstatus",
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    workspaceplan_enum.create(bind, checkfirst=True)
    deploymentmode_enum.create(bind, checkfirst=True)
    membershiprole_enum.create(bind, checkfirst=True)
    billingprovider_enum.create(bind, checkfirst=True)
    workspacesubscriptionstatus_enum.create(bind, checkfirst=True)

    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("plan", workspaceplan_enum, nullable=False),
        sa.Column("deployment_mode", deploymentmode_enum, nullable=False),
        sa.Column("seat_limit", sa.Integer(), nullable=False),
        sa.Column("entitlement_overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("usage_limit_overrides", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workspaces_plan"), "workspaces", ["plan"], unique=False)
    op.create_index(
        op.f("ix_workspaces_deployment_mode"),
        "workspaces",
        ["deployment_mode"],
        unique=False,
    )

    op.create_table(
        "workspace_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", membershiprole_enum, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            name="uq_workspace_memberships_workspace_user",
        ),
    )
    op.create_index(
        op.f("ix_workspace_memberships_user_id"),
        "workspace_memberships",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workspace_memberships_workspace_id"),
        "workspace_memberships",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_workspace_memberships_workspace_role",
        "workspace_memberships",
        ["workspace_id", "role"],
        unique=False,
    )

    op.create_table(
        "workspace_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("billing_provider", billingprovider_enum, nullable=False),
        sa.Column("status", workspacesubscriptionstatus_enum, nullable=False),
        sa.Column("plan_code", sa.String(length=100), nullable=False),
        sa.Column("external_customer_id", sa.String(length=255), nullable=True),
        sa.Column("external_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()

    op.drop_table("workspace_subscriptions")
    op.drop_index("ix_workspace_memberships_workspace_role", table_name="workspace_memberships")
    op.drop_index(op.f("ix_workspace_memberships_workspace_id"), table_name="workspace_memberships")
    op.drop_index(op.f("ix_workspace_memberships_user_id"), table_name="workspace_memberships")
    op.drop_table("workspace_memberships")
    op.drop_index(op.f("ix_workspaces_deployment_mode"), table_name="workspaces")
    op.drop_index(op.f("ix_workspaces_plan"), table_name="workspaces")
    op.drop_table("workspaces")

    workspacesubscriptionstatus_enum.drop(bind, checkfirst=True)
    billingprovider_enum.drop(bind, checkfirst=True)
    membershiprole_enum.drop(bind, checkfirst=True)
    deploymentmode_enum.drop(bind, checkfirst=True)
    workspaceplan_enum.drop(bind, checkfirst=True)
