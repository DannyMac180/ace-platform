"""Automatic evolution triggering task.

This module provides a periodic Celery task that checks for playbooks
that should have evolution triggered based on configurable thresholds:

1. Outcome count threshold: Trigger only when there are at least N unprocessed outcomes
   (default: 5; configured via EVOLUTION_OUTCOME_THRESHOLD, clamped to a minimum of 5)

The task runs periodically via Celery beat and queues evolution jobs
for any playbooks meeting the criteria.
"""

import logging

from sqlalchemy import func, select

from ace_platform.config import get_settings
from ace_platform.core.limits import SubscriptionTier, check_spending_limit_sync
from ace_platform.db.models import (
    EvolutionJob,
    EvolutionJobStatus,
    Outcome,
    Playbook,
    PlaybookStatus,
    User,
)
from ace_platform.db.session import SyncSessionLocal
from ace_platform.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Default thresholds (can be overridden in settings)
DEFAULT_OUTCOME_THRESHOLD = 5


@celery_app.task(
    bind=True,
    name="ace_platform.workers.auto_evolution.check_auto_evolution",
    queue="default",
)
def check_auto_evolution(self) -> dict:
    """Check for playbooks that need automatic evolution.

    This task runs periodically and:
    1. Finds active playbooks with unprocessed outcomes
    2. Checks if they meet the outcome count threshold
    3. Queues evolution jobs for matching playbooks

    Returns:
        Dict with task results including playbooks checked and jobs queued.
    """
    settings = get_settings()

    # Get thresholds from settings or use defaults (clamp to a minimum of 5)
    outcome_threshold = max(
        DEFAULT_OUTCOME_THRESHOLD,
        getattr(settings, "evolution_outcome_threshold", DEFAULT_OUTCOME_THRESHOLD),
    )

    with SyncSessionLocal() as db:
        result = _check_and_trigger_evolutions(
            db,
            outcome_threshold=outcome_threshold,
        )

    return result


def _check_and_trigger_evolutions(
    db,
    outcome_threshold: int = DEFAULT_OUTCOME_THRESHOLD,
) -> dict:
    """Check playbooks and trigger evolutions as needed.

    Args:
        db: Database session.
        outcome_threshold: Number of unprocessed outcomes to trigger evolution.

    Returns:
        Dict with results.
    """
    from ace_platform.workers.evolution_task import process_evolution_job

    playbooks_checked = 0
    jobs_queued = 0
    skipped_running = 0
    skipped_spending_limit = 0

    # Get all active playbooks
    result = db.execute(select(Playbook).where(Playbook.status == PlaybookStatus.ACTIVE))
    playbooks = result.scalars().all()

    for playbook in playbooks:
        playbooks_checked += 1

        # Check if there's already a running/queued job
        existing_job = db.execute(
            select(EvolutionJob).where(
                EvolutionJob.playbook_id == playbook.id,
                EvolutionJob.status.in_(
                    [
                        EvolutionJobStatus.QUEUED,
                        EvolutionJobStatus.RUNNING,
                    ]
                ),
            )
        ).scalar_one_or_none()

        if existing_job:
            skipped_running += 1
            continue

        # Check user's spending limit and payment method
        user = db.get(User, playbook.user_id)
        if user:
            user_tier = (
                SubscriptionTier(user.subscription_tier)
                if user.subscription_tier
                else SubscriptionTier.FREE
            )

            # FREE tier users must have a payment method on file
            if user_tier == SubscriptionTier.FREE and not user.has_payment_method:
                from ace_platform.core.metrics import increment_evolution_blocked_no_card

                increment_evolution_blocked_no_card(trigger_type="auto")
                logger.debug(
                    "Skipping auto-evolution for playbook %s: user %s has no payment method",
                    playbook.id,
                    user.id,
                )
                skipped_spending_limit += 1
                continue

            within_limit, _, _ = check_spending_limit_sync(db, user.id, user_tier)
            if not within_limit:
                logger.debug(
                    "Skipping auto-evolution for playbook %s: user %s exceeded spending limit",
                    playbook.id,
                    user.id,
                )
                skipped_spending_limit += 1
                continue

        # Count unprocessed outcomes
        unprocessed_count = (
            db.scalar(
                select(func.count(Outcome.id)).where(
                    Outcome.playbook_id == playbook.id,
                    Outcome.processed_at.is_(None),
                )
            )
            or 0
        )

        if unprocessed_count == 0:
            continue

        # Check trigger conditions
        should_trigger = False
        trigger_reason = ""

        # Condition 1: Outcome count threshold
        if unprocessed_count >= outcome_threshold:
            should_trigger = True
            trigger_reason = f"outcome_count ({unprocessed_count} >= {outcome_threshold})"

        if should_trigger:
            logger.info(
                "Auto-triggering evolution for playbook %s: %s",
                playbook.id,
                trigger_reason,
            )

            # Create evolution job
            new_job = EvolutionJob(
                playbook_id=playbook.id,
                status=EvolutionJobStatus.QUEUED,
                from_version_id=playbook.current_version_id,
            )
            db.add(new_job)
            db.flush()

            # Record auto-trigger metric
            from ace_platform.core.metrics import increment_evolution_triggered

            increment_evolution_triggered(trigger_type="auto")

            # Queue the Celery task
            process_evolution_job.delay(str(new_job.id))
            jobs_queued += 1

    db.commit()

    return {
        "status": "completed",
        "playbooks_checked": playbooks_checked,
        "jobs_queued": jobs_queued,
        "skipped_running": skipped_running,
        "skipped_spending_limit": skipped_spending_limit,
        "thresholds": {
            "outcome_count": outcome_threshold,
        },
    }
