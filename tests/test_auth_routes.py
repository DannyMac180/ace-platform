"""Focused tests for auth route response shaping."""

from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest

from ace_platform.api.routes.auth import get_current_user
from ace_platform.db.models import SubscriptionStatus, User


@pytest.mark.asyncio
async def test_get_current_user_includes_rollout_metadata():
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid4(),
        email="rollout@example.com",
        hashed_password="hashed-password",
        is_active=True,
        is_admin=False,
        email_verified=True,
        subscription_tier="starter",
        subscription_status=SubscriptionStatus.ACTIVE,
        has_used_trial=False,
        has_payment_method=False,
        created_at=now,
        updated_at=now,
    )

    with (
        patch(
            "ace_platform.api.routes.auth.get_available_plans",
            return_value={"starter": True, "enterprise": False},
        ),
        patch(
            "ace_platform.api.routes.auth.get_user_capabilities",
            return_value={"managed_inference": True, "shared_workspace": False},
        ),
    ):
        response = await get_current_user(user)

    assert response.email == "rollout@example.com"
    assert response.available_plans == {"starter": True, "enterprise": False}
    assert response.capabilities == {
        "managed_inference": True,
        "shared_workspace": False,
    }
