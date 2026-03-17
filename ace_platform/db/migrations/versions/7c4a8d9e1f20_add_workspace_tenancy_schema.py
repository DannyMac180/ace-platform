"""add workspace tenancy schema

Revision ID: 7c4a8d9e1f20
Revises: 6b9a3f2d1c7e
Create Date: 2026-03-17 11:35:00.000000

"""

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7c4a8d9e1f20"
down_revision: str | Sequence[str] | None = "6b9a3f2d1c7e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


workspace_plan_enum = postgresql.ENUM(
    "PERSONAL", "TEAM", "ENTERPRISE", name="workspaceplan", create_type=False
)
workspace_deployment_mode_enum = postgresql.ENUM(
    "CLOUD", "SELF_HOSTED", name="workspacedeploymentmode", create_type=False
)
membership_role_enum = postgresql.ENUM(
    "OWNER", "MEMBER", "REVIEWER", "ADMIN", name="membershiprole", create_type=False
)
workspace_billing_provider_enum = postgresql.ENUM(
    "STRIPE", "MANUAL", name="workspacebillingprovider", create_type=False
)
workspace_subscription_status_enum = postgresql.ENUM(
    "TRIALING",
    "ACTIVE",
    "PAST_DUE",
    "CANCELED",
    "UNPAID",
    name="workspacesubscriptionstatus",
    create_type=False,
)


def _entitlements_for_plan(plan: str) -> dict[str, bool]:
    if plan == "ENTERPRISE":
        return {
            "cloud_sync": True,
            "hosted_backups": True,
            "managed_inference": True,
            "hosted_evals": True,
            "invite_members": True,
            "shared_workspace": True,
            "approvals": True,
            "rbac": True,
            "sso": True,
            "audit_logs": True,
        }

    if plan == "TEAM":
        return {
            "cloud_sync": True,
            "hosted_backups": True,
            "managed_inference": True,
            "hosted_evals": True,
            "invite_members": True,
            "shared_workspace": True,
            "approvals": True,
            "rbac": True,
            "sso": False,
            "audit_logs": True,
        }

    return {
        "cloud_sync": True,
        "hosted_backups": True,
        "managed_inference": True,
        "hosted_evals": True,
        "invite_members": False,
        "shared_workspace": False,
        "approvals": False,
        "rbac": False,
        "sso": False,
        "audit_logs": False,
    }


def _personal_workspace_name(email: str | None) -> str:
    if not email:
        return "Personal Workspace"

    local_part = email.split("@", 1)[0].strip()
    if not local_part:
        return "Personal Workspace"

    return f"{local_part}'s Workspace"


def _workspace_plan(subscription_tier: str | None) -> str:
    if subscription_tier == "enterprise":
        return "ENTERPRISE"

    return "PERSONAL"


def _workspace_subscription_status(
    legacy_status: str | None, trial_ends_at: datetime | None
) -> str | None:
    if trial_ends_at is not None:
        normalized_trial_end = (
            trial_ends_at
            if trial_ends_at.tzinfo is not None
            else trial_ends_at.replace(tzinfo=timezone.utc)
        )
        if normalized_trial_end > datetime.now(timezone.utc):
            return "TRIALING"

    if legacy_status == "ACTIVE":
        return "ACTIVE"

    if legacy_status == "PAST_DUE":
        return "PAST_DUE"

    if legacy_status == "UNPAID":
        return "UNPAID"

    if legacy_status == "CANCELED":
        return "CANCELED"

    return None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    workspace_plan_enum.create(bind, checkfirst=True)
    workspace_deployment_mode_enum.create(bind, checkfirst=True)
    membership_role_enum.create(bind, checkfirst=True)
    workspace_billing_provider_enum.create(bind, checkfirst=True)
    workspace_subscription_status_enum.create(bind, checkfirst=True)

    op.create_table(
        "workspaces",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "plan",
            workspace_plan_enum,
            nullable=False,
            server_default="PERSONAL",
        ),
        sa.Column(
            "deployment_mode",
            workspace_deployment_mode_enum,
            nullable=False,
            server_default="CLOUD",
        ),
        sa.Column(
            "seat_limit",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("usage_limits", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.CheckConstraint("seat_limit >= 1", name="ck_workspaces_seat_limit"),
        sa.CheckConstraint(
            "(plan != 'PERSONAL') OR (seat_limit = 1)",
            name="ck_workspaces_personal_seat_limit",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workspaces_plan"), "workspaces", ["plan"], unique=False)

    op.create_table(
        "workspace_memberships",
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "role",
            membership_role_enum,
            nullable=False,
            server_default="MEMBER",
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
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("workspace_id", "user_id"),
    )
    op.create_index(
        "ix_workspace_memberships_user_role",
        "workspace_memberships",
        ["user_id", "role"],
        unique=False,
    )

    op.create_table(
        "workspace_subscriptions",
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("billing_provider", workspace_billing_provider_enum, nullable=False),
        sa.Column("status", workspace_subscription_status_enum, nullable=False),
        sa.Column("plan_code", sa.String(length=100), nullable=False),
        sa.Column("provider_customer_id", sa.String(length=255), nullable=True),
        sa.Column("provider_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("workspace_id"),
    )
    op.create_index(
        "ix_workspace_subscriptions_status",
        "workspace_subscriptions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_workspace_subscriptions_provider_customer",
        "workspace_subscriptions",
        ["billing_provider", "provider_customer_id"],
        unique=False,
    )

    op.create_table(
        "workspace_entitlements",
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("cloud_sync", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("hosted_backups", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "managed_inference",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("hosted_evals", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("invite_members", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "shared_workspace",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("approvals", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("rbac", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sso", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("audit_logs", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("workspace_id"),
    )

    users = bind.execute(
        sa.text(
            """
            SELECT
                id,
                email,
                stripe_customer_id,
                stripe_subscription_id,
                subscription_tier,
                subscription_status::text AS subscription_status,
                subscription_current_period_end,
                trial_ends_at
            FROM users
            """
        )
    ).mappings()

    workspace_rows: list[dict[str, object]] = []
    membership_rows: list[dict[str, object]] = []
    entitlement_rows: list[dict[str, object]] = []
    subscription_rows: list[dict[str, object]] = []

    for user in users:
        workspace_plan = _workspace_plan(user["subscription_tier"])
        workspace_id = uuid4()
        workspace_rows.append(
            {
                "id": workspace_id,
                "name": _personal_workspace_name(user["email"]),
                "plan": workspace_plan,
                "deployment_mode": "CLOUD",
                "seat_limit": 1,
                "usage_limits": None,
            }
        )
        membership_rows.append(
            {
                "workspace_id": workspace_id,
                "user_id": user["id"],
                "role": "OWNER",
            }
        )
        entitlement_rows.append(
            {
                "workspace_id": workspace_id,
                **_entitlements_for_plan(workspace_plan),
            }
        )

        workspace_subscription_status = _workspace_subscription_status(
            user["subscription_status"],
            user["trial_ends_at"],
        )
        has_legacy_subscription_data = any(
            [
                user["stripe_customer_id"],
                user["stripe_subscription_id"],
                user["subscription_tier"],
                workspace_subscription_status,
            ]
        )
        if has_legacy_subscription_data and workspace_subscription_status is not None:
            subscription_rows.append(
                {
                    "workspace_id": workspace_id,
                    "billing_provider": (
                        "STRIPE"
                        if user["stripe_customer_id"] or user["stripe_subscription_id"]
                        else "MANUAL"
                    ),
                    "status": workspace_subscription_status,
                    "plan_code": user["subscription_tier"] or "personal",
                    "provider_customer_id": user["stripe_customer_id"],
                    "provider_subscription_id": user["stripe_subscription_id"],
                    "current_period_end": user["subscription_current_period_end"],
                    "trial_ends_at": user["trial_ends_at"],
                }
            )

    if workspace_rows:
        bind.execute(
            sa.table(
                "workspaces",
                sa.column("id", sa.UUID()),
                sa.column("name", sa.String()),
                sa.column("plan", workspace_plan_enum),
                sa.column("deployment_mode", workspace_deployment_mode_enum),
                sa.column("seat_limit", sa.Integer()),
                sa.column("usage_limits", postgresql.JSONB(astext_type=sa.Text())),
            ).insert(),
            workspace_rows,
        )
        bind.execute(
            sa.table(
                "workspace_memberships",
                sa.column("workspace_id", sa.UUID()),
                sa.column("user_id", sa.UUID()),
                sa.column("role", membership_role_enum),
            ).insert(),
            membership_rows,
        )
        bind.execute(
            sa.table(
                "workspace_entitlements",
                sa.column("workspace_id", sa.UUID()),
                sa.column("cloud_sync", sa.Boolean()),
                sa.column("hosted_backups", sa.Boolean()),
                sa.column("managed_inference", sa.Boolean()),
                sa.column("hosted_evals", sa.Boolean()),
                sa.column("invite_members", sa.Boolean()),
                sa.column("shared_workspace", sa.Boolean()),
                sa.column("approvals", sa.Boolean()),
                sa.column("rbac", sa.Boolean()),
                sa.column("sso", sa.Boolean()),
                sa.column("audit_logs", sa.Boolean()),
            ).insert(),
            entitlement_rows,
        )

    if subscription_rows:
        bind.execute(
            sa.table(
                "workspace_subscriptions",
                sa.column("workspace_id", sa.UUID()),
                sa.column("billing_provider", workspace_billing_provider_enum),
                sa.column("status", workspace_subscription_status_enum),
                sa.column("plan_code", sa.String()),
                sa.column("provider_customer_id", sa.String()),
                sa.column("provider_subscription_id", sa.String()),
                sa.column("current_period_end", sa.DateTime(timezone=True)),
                sa.column("trial_ends_at", sa.DateTime(timezone=True)),
            ).insert(),
            subscription_rows,
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("workspace_entitlements")

    op.drop_index(
        "ix_workspace_subscriptions_provider_customer",
        table_name="workspace_subscriptions",
    )
    op.drop_index("ix_workspace_subscriptions_status", table_name="workspace_subscriptions")
    op.drop_table("workspace_subscriptions")

    op.drop_index("ix_workspace_memberships_user_role", table_name="workspace_memberships")
    op.drop_table("workspace_memberships")

    op.drop_index(op.f("ix_workspaces_plan"), table_name="workspaces")
    op.drop_table("workspaces")

    bind = op.get_bind()
    workspace_subscription_status_enum.drop(bind, checkfirst=True)
    workspace_billing_provider_enum.drop(bind, checkfirst=True)
    membership_role_enum.drop(bind, checkfirst=True)
    workspace_deployment_mode_enum.drop(bind, checkfirst=True)
    workspace_plan_enum.drop(bind, checkfirst=True)
