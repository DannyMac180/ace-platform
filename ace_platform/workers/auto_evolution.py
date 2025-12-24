"""Automatic evolution triggering task.

This module provides a periodic Celery task that checks for playbooks
that should have evolution triggered based on configurable thresholds:

1. Outcome count threshold: Trigger after N unprocessed outcomes (default: 5)
2. Time threshold: Trigger after T hours since last evolution with at least 1 outcome

The task runs periodically via Celery beat and queues evolution jobs
for any playbooks meeting the criteria.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from ace_platform.config import get_settings
from ace_platform.db.models import (
    EvolutionJob,
    EvolutionJobStatus,
    Outcome,
    Playbook,
    PlaybookStatus,
)
from ace_platform.db.session import SyncSessionLocal
from ace_platform.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Default thresholds (can be overridden in settings)
DEFAULT_OUTCOME_THRESHOLD = 5
DEFAULT_TIME_THRESHOLD_HOURS = 24


@celery_app.task(
    bind=True,
    name="ace_platform.workers.auto_evolution.check_auto_evolution",
    queue="default",
)
def check_auto_evolution(self) -> dict:
    """Check for playbooks that need automatic evolution.

    This task runs periodically and:
    1. Finds active playbooks with unprocessed outcomes
    2. Checks if they meet trigger criteria (count or time threshold)
    3. Queues evolution jobs for matching playbooks

    Returns:
        Dict with task results including playbooks checked and jobs queued.
    """
    settings = get_settings()

    # Get thresholds from settings or use defaults
    outcome_threshold = getattr(settings, "evolution_outcome_threshold", DEFAULT_OUTCOME_THRESHOLD)
    time_threshold_hours = getattr(
        settings, "evolution_time_threshold_hours", DEFAULT_TIME_THRESHOLD_HOURS
    )

    with SyncSessionLocal() as db:
        result = _check_and_trigger_evolutions(
            db,
            outcome_threshold=outcome_threshold,
            time_threshold_hours=time_threshold_hours,
        )

    return result


def _check_and_trigger_evolutions(
    db,
    outcome_threshold: int = DEFAULT_OUTCOME_THRESHOLD,
    time_threshold_hours: int = DEFAULT_TIME_THRESHOLD_HOURS,
) -> dict:
    """Check playbooks and trigger evolutions as needed.

    Args:
        db: Database session.
        outcome_threshold: Number of unprocessed outcomes to trigger evolution.
        time_threshold_hours: Hours since last evolution to trigger with any outcomes.

    Returns:
        Dict with results.
    """
    from ace_platform.workers.evolution_task import process_evolution_job

    playbooks_checked = 0
    jobs_queued = 0
    skipped_running = 0

    # Get all active playbooks
    result = db.execute(select(Playbook).where(Playbook.status == PlaybookStatus.ACTIVE))
    playbooks = result.scalars().all()

    time_threshold = datetime.now(UTC) - timedelta(hours=time_threshold_hours)

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

        # Condition 2: Time threshold with at least 1 outcome
        if not should_trigger and unprocessed_count >= 1:
            # Get last completed evolution job
            last_evolution = db.execute(
                select(EvolutionJob)
                .where(
                    EvolutionJob.playbook_id == playbook.id,
                    EvolutionJob.status == EvolutionJobStatus.COMPLETED,
                )
                .order_by(EvolutionJob.completed_at.desc())
                .limit(1)
            ).scalar_one_or_none()

            if last_evolution is None:
                # Never evolved - check if playbook is old enough
                if playbook.created_at < time_threshold:
                    should_trigger = True
                    trigger_reason = (
                        f"time_threshold (no prior evolution, {unprocessed_count} outcomes)"
                    )
            elif last_evolution.completed_at < time_threshold:
                should_trigger = True
                trigger_reason = f"time_threshold ({time_threshold_hours}h since last evolution, {unprocessed_count} outcomes)"

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

            # Queue the Celery task
            process_evolution_job.delay(str(new_job.id))
            jobs_queued += 1

    db.commit()

    return {
        "status": "completed",
        "playbooks_checked": playbooks_checked,
        "jobs_queued": jobs_queued,
        "skipped_running": skipped_running,
        "thresholds": {
            "outcome_count": outcome_threshold,
            "time_hours": time_threshold_hours,
        },
    }
