"""add_workspace_models_and_entitlements

Revision ID: 7d4c8f1a2b3c
Revises: 6b9a3f2d1c7e
Create Date: 2026-03-17

This revision originally introduced the workspace tenancy tables. After the PR
was synced with ``main``, those tables were already provided by the
``7c4a8d9e1f20``/``c4d5e6f7a8b9`` migration chain. Keeping this revision as a
no-op preserves the branch history without attempting to recreate the same
schema during ``alembic upgrade head``.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "7d4c8f1a2b3c"
down_revision: str | Sequence[str] | None = "6b9a3f2d1c7e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Preserve the historical branch point without changing schema."""


def downgrade() -> None:
    """This compatibility revision intentionally has no downgrade work."""
