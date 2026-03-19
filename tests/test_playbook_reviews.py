"""Tests for promoted playbook review workflow helpers."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.dialects import postgresql

from ace_platform.core.playbook_reviews import apply_review_action, get_review_history
from ace_platform.db.models import (
    Playbook,
    PlaybookReviewAction,
    PlaybookReviewStatus,
    PlaybookSource,
    PlaybookStatus,
    User,
)


def test_playbook_review_status_enum_uses_lowercase_database_values():
    enum_type = Playbook.__table__.c.review_status.type
    dialect = postgresql.dialect()

    assert enum_type.enums == ["draft", "proposed", "approved", "archived"]

    bind_processor = enum_type.bind_processor(dialect)
    result_processor = enum_type.result_processor(dialect, None)

    assert bind_processor(PlaybookReviewStatus.DRAFT) == "draft"
    assert result_processor("approved") is PlaybookReviewStatus.APPROVED


def _make_user() -> User:
    return User(
        id=uuid4(),
        email="reviewer@example.com",
        hashed_password="hashed-password",
        is_active=True,
        email_verified=True,
    )


def _make_playbook(
    *,
    review_status: PlaybookReviewStatus,
    status: PlaybookStatus = PlaybookStatus.ACTIVE,
) -> Playbook:
    now = datetime.now(UTC)
    return Playbook(
        id=uuid4(),
        user_id=uuid4(),
        name="Promoted Playbook",
        description="Test playbook",
        status=status,
        review_status=review_status,
        review_status_updated_at=now,
        review_history=[],
        source=PlaybookSource.USER_CREATED,
        created_at=now,
        updated_at=now,
    )


def test_get_review_history_synthesizes_current_review_status_for_legacy_playbook():
    user = _make_user()
    playbook = _make_playbook(review_status=PlaybookReviewStatus.APPROVED)

    history = get_review_history(playbook, fallback_actor=user)

    assert history == [
        {
            "id": history[0]["id"],
            "action": PlaybookReviewAction.APPROVED.value,
            "from_review_status": None,
            "to_review_status": PlaybookReviewStatus.APPROVED.value,
            "actor_user_id": str(user.id),
            "actor_email": user.email,
            "created_at": playbook.created_at.isoformat(),
        }
    ]


def test_apply_review_action_transitions_proposed_playbook_to_approved():
    user = _make_user()
    playbook = _make_playbook(review_status=PlaybookReviewStatus.PROPOSED)

    event = apply_review_action(
        playbook,
        action=PlaybookReviewAction.APPROVED,
        actor=user,
    )

    assert playbook.review_status is PlaybookReviewStatus.APPROVED
    assert event["action"] == PlaybookReviewAction.APPROVED.value
    assert event["from_review_status"] == PlaybookReviewStatus.PROPOSED.value
    assert event["to_review_status"] == PlaybookReviewStatus.APPROVED.value
    assert len(playbook.review_history) == 2


def test_apply_review_action_allows_approved_playbook_to_return_to_draft():
    user = _make_user()
    playbook = _make_playbook(review_status=PlaybookReviewStatus.APPROVED)

    apply_review_action(
        playbook,
        action=PlaybookReviewAction.RETURNED_TO_DRAFT,
        actor=user,
    )

    assert playbook.review_status is PlaybookReviewStatus.DRAFT
    assert playbook.review_history[-1]["action"] == PlaybookReviewAction.RETURNED_TO_DRAFT.value


def test_apply_review_action_restores_archived_playbook_to_active_status():
    user = _make_user()
    playbook = _make_playbook(
        review_status=PlaybookReviewStatus.ARCHIVED,
        status=PlaybookStatus.ARCHIVED,
    )

    apply_review_action(
        playbook,
        action=PlaybookReviewAction.RETURNED_TO_DRAFT,
        actor=user,
    )

    assert playbook.review_status is PlaybookReviewStatus.DRAFT
    assert playbook.status is PlaybookStatus.ACTIVE


def test_apply_review_action_rejects_invalid_transition():
    user = _make_user()
    playbook = _make_playbook(review_status=PlaybookReviewStatus.DRAFT)

    with pytest.raises(HTTPException) as exc_info:
        apply_review_action(
            playbook,
            action=PlaybookReviewAction.APPROVED,
            actor=user,
        )

    assert exc_info.value.status_code == 400
    assert "not allowed" in str(exc_info.value.detail)
