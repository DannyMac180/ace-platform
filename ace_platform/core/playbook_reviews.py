"""Helpers for promoted playbook review workflows."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, status

from ace_platform.db.models import (
    Playbook,
    PlaybookReviewAction,
    PlaybookReviewStatus,
    PlaybookStatus,
    User,
)


def build_review_event(
    *,
    actor: User | None,
    action: PlaybookReviewAction,
    from_status: PlaybookReviewStatus | None,
    to_status: PlaybookReviewStatus,
    created_at: datetime | None = None,
) -> dict[str, str | None]:
    """Build one persisted review history event."""

    occurred_at = created_at or datetime.now(UTC)
    return {
        "id": str(uuid4()),
        "action": action.value,
        "from_review_status": from_status.value if from_status is not None else None,
        "to_review_status": to_status.value,
        "actor_user_id": str(actor.id)
        if actor is not None and getattr(actor, "id", None)
        else None,
        "actor_email": getattr(actor, "email", None) if actor is not None else None,
        "created_at": occurred_at.isoformat(),
    }


def get_review_history(playbook: Playbook, *, fallback_actor: User | None = None) -> list[dict]:
    """Return stored review history or a synthesized event for the current state."""

    if playbook.review_history:
        return list(playbook.review_history)

    fallback_action = {
        PlaybookReviewStatus.DRAFT: PlaybookReviewAction.CREATED,
        PlaybookReviewStatus.PROPOSED: PlaybookReviewAction.PROPOSED,
        PlaybookReviewStatus.APPROVED: PlaybookReviewAction.APPROVED,
        PlaybookReviewStatus.ARCHIVED: PlaybookReviewAction.ARCHIVED,
    }[playbook.review_status]

    return [
        build_review_event(
            actor=fallback_actor,
            action=fallback_action,
            from_status=None,
            to_status=playbook.review_status,
            created_at=playbook.created_at,
        )
    ]


def apply_review_action(
    playbook: Playbook,
    *,
    action: PlaybookReviewAction,
    actor: User,
) -> dict[str, str | None]:
    """Apply one review action to a playbook and return the appended event."""

    transitions: dict[
        PlaybookReviewStatus,
        dict[PlaybookReviewAction, PlaybookReviewStatus],
    ] = {
        PlaybookReviewStatus.DRAFT: {
            PlaybookReviewAction.PROPOSED: PlaybookReviewStatus.PROPOSED,
            PlaybookReviewAction.ARCHIVED: PlaybookReviewStatus.ARCHIVED,
        },
        PlaybookReviewStatus.PROPOSED: {
            PlaybookReviewAction.APPROVED: PlaybookReviewStatus.APPROVED,
            PlaybookReviewAction.RETURNED_TO_DRAFT: PlaybookReviewStatus.DRAFT,
            PlaybookReviewAction.ARCHIVED: PlaybookReviewStatus.ARCHIVED,
        },
        PlaybookReviewStatus.APPROVED: {
            PlaybookReviewAction.RETURNED_TO_DRAFT: PlaybookReviewStatus.DRAFT,
            PlaybookReviewAction.ARCHIVED: PlaybookReviewStatus.ARCHIVED,
        },
        PlaybookReviewStatus.ARCHIVED: {
            PlaybookReviewAction.RETURNED_TO_DRAFT: PlaybookReviewStatus.DRAFT,
        },
    }

    next_status = transitions.get(playbook.review_status, {}).get(action)
    if next_status is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Action '{action.value}' is not allowed when review status "
                f"is '{playbook.review_status.value}'."
            ),
        )

    previous_status = playbook.review_status
    playbook.review_status = next_status
    playbook.review_status_updated_at = datetime.now(UTC)

    if next_status is PlaybookReviewStatus.ARCHIVED:
        playbook.status = PlaybookStatus.ARCHIVED
    elif (
        previous_status is PlaybookReviewStatus.ARCHIVED
        and playbook.status is PlaybookStatus.ARCHIVED
    ):
        playbook.status = PlaybookStatus.ACTIVE

    history = get_review_history(playbook, fallback_actor=actor)
    if not playbook.review_history:
        playbook.review_history = history

    event = build_review_event(
        actor=actor,
        action=action,
        from_status=previous_status,
        to_status=next_status,
    )
    playbook.review_history.append(event)
    return event
