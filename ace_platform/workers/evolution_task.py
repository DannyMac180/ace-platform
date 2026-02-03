"""Celery task for processing evolution jobs.

This task handles background playbook evolution:
1. Fetches unprocessed outcomes for a playbook
2. Runs the ACE evolution service
3. Creates a new playbook version with the evolved content
4. Updates job and outcome records
"""

import re
import time
from datetime import UTC, datetime
from uuid import UUID

import sentry_sdk
from sqlalchemy import select

from ace_platform.core.evolution import EvolutionService, OutcomeData
from ace_platform.core.metrics import (
    decrement_active_jobs,
    increment_active_jobs,
    observe_evolution,
)
from ace_platform.core.sentry_context import set_job_context
from ace_platform.db.models import (
    EvolutionJob,
    EvolutionJobStatus,
    Outcome,
    Playbook,
    PlaybookVersion,
)
from ace_platform.db.session import SyncSessionLocal
from ace_platform.workers.celery_app import celery_app


@celery_app.task(
    bind=True,
    name="ace_platform.evolution.process_job",
    queue="evolution",
    max_retries=3,
    default_retry_delay=60,
)
def process_evolution_job(self, job_id: str) -> dict:
    """Process an evolution job.

    This task is queued when trigger_evolution is called. It:
    1. Updates job status to RUNNING
    2. Fetches unprocessed outcomes for the playbook
    3. Runs the evolution service
    4. Creates a new playbook version if changes were made
    5. Updates job status to COMPLETED (or FAILED on error)
    6. Marks processed outcomes

    Args:
        job_id: UUID string of the evolution job to process.

    Returns:
        Dict with job result information.
    """
    job_uuid = UUID(job_id)

    # Set Sentry context for job tracking
    set_job_context(job_id=job_id, job_type="evolution", status="starting")

    with SyncSessionLocal() as db:
        # Fetch the job
        job = db.get(EvolutionJob, job_uuid)
        if not job:
            return {"status": "error", "message": f"Job {job_id} not found"}

        # Set playbook context for better error tracking
        set_job_context(
            job_id=job_id,
            job_type="evolution",
            status="running",
            playbook_id=str(job.playbook_id),
        )

        # Check if job is still queued
        if job.status != EvolutionJobStatus.QUEUED:
            return {
                "status": "skipped",
                "message": f"Job already in status: {job.status.value}",
            }

        # Update to RUNNING
        job.status = EvolutionJobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        db.commit()

        # Track job start for metrics
        increment_active_jobs()
        start_time = time.time()

        try:
            result = _execute_evolution(db, job)

            # Record success metrics
            duration = time.time() - start_time
            token_total = 0
            model = "gpt-5.2"  # Default model
            if job.token_totals:
                token_total = job.token_totals.get("total_tokens", 0)
                model = job.token_totals.get("model", "gpt-5.2")

            observe_evolution(
                status="completed",
                playbook_id=str(job.playbook_id),
                duration_seconds=duration,
                tokens_used=token_total,
                model=model,
            )

            return result
        except Exception as e:
            # Record failure metrics
            duration = time.time() - start_time
            observe_evolution(
                status="failed",
                playbook_id=str(job.playbook_id),
                duration_seconds=duration,
            )

            # Capture exception to Sentry with context
            sentry_sdk.capture_exception(e)

            # Update job to FAILED
            job.status = EvolutionJobStatus.FAILED
            job.completed_at = datetime.now(UTC)
            job.error_message = str(e)[:1000]  # Truncate long errors
            db.commit()

            # Retry for transient errors
            if self.request.retries < self.max_retries:
                raise self.retry(exc=e)

            return {
                "status": "failed",
                "job_id": job_id,
                "error": str(e),
            }
        finally:
            # Always decrement active jobs
            decrement_active_jobs()


def _execute_evolution(db, job: EvolutionJob) -> dict:
    """Execute the evolution process for a job.

    Args:
        db: Database session.
        job: The evolution job to process.

    Returns:
        Dict with execution result.
    """
    # Fetch the playbook
    playbook = db.get(Playbook, job.playbook_id)
    if not playbook:
        raise ValueError(f"Playbook {job.playbook_id} not found")

    # Get current playbook content
    current_content = ""
    current_version_number = 0
    if playbook.current_version_id:
        current_version = db.get(PlaybookVersion, playbook.current_version_id)
        if current_version:
            current_content = current_version.content
            current_version_number = current_version.version_number

    # Fetch unprocessed outcomes
    result = db.execute(
        select(Outcome).where(
            Outcome.playbook_id == job.playbook_id,
            Outcome.processed_at.is_(None),
        )
    )
    outcomes = result.scalars().all()

    if not outcomes:
        # No outcomes to process - mark as completed
        job.status = EvolutionJobStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
        job.outcomes_processed = 0
        db.commit()

        return {
            "status": "completed",
            "job_id": str(job.id),
            "outcomes_processed": 0,
            "message": "No unprocessed outcomes found",
        }

    # Convert to OutcomeData format
    outcome_data = [
        OutcomeData(
            task_description=o.task_description,
            outcome_status=o.outcome_status.value,
            reasoning_trace=o.reasoning_trace,
            notes=o.notes,
        )
        for o in outcomes
    ]

    # Run evolution
    service = EvolutionService()
    evolution_result = service.evolve_playbook(current_content, outcome_data)

    # Create new version if content changed
    new_version = None
    if evolution_result.has_changes:
        # Count ACE-format bullets: [id] helpful=X harmful=Y :: content
        ace_bullet_pattern = r"\[[^\]]+\]\s*helpful=\d+\s*harmful=\d+\s*::"
        bullet_count = len(re.findall(ace_bullet_pattern, evolution_result.evolved_playbook))

        new_version = PlaybookVersion(
            playbook_id=job.playbook_id,
            version_number=current_version_number + 1,
            content=evolution_result.evolved_playbook,
            bullet_count=bullet_count,
            created_by_job_id=job.id,
            diff_summary=_create_diff_summary(evolution_result.operations_applied),
        )
        db.add(new_version)
        db.flush()

        # Update playbook to point to new version
        playbook.current_version_id = new_version.id
        job.to_version_id = new_version.id

    # Mark outcomes as processed
    now = datetime.now(UTC)
    for outcome in outcomes:
        outcome.processed_at = now
        outcome.evolution_job_id = job.id

    # Update job status
    job.status = EvolutionJobStatus.COMPLETED
    job.completed_at = now
    job.outcomes_processed = len(outcomes)
    job.token_totals = evolution_result.token_usage

    # Write usage records for billing/metering (best effort; never fail the job)
    try:
        _write_usage_records_for_evolution(
            db=db,
            user_id=playbook.user_id,
            playbook_id=playbook.id,
            evolution_job_id=job.id,
            token_usage=evolution_result.token_usage,
        )
    except Exception:
        # Avoid failing evolution completion due to metering issues
        sentry_sdk.capture_exception()

    db.commit()

    return {
        "status": "completed",
        "job_id": str(job.id),
        "outcomes_processed": len(outcomes),
        "new_version": new_version.version_number if new_version else None,
        "has_changes": evolution_result.has_changes,
    }


def _write_usage_records_for_evolution(
    *,
    db,
    user_id: UUID,
    playbook_id: UUID,
    evolution_job_id: UUID,
    token_usage: dict | None,
) -> None:
    """Persist per-operation usage records for an evolution job (sync session)."""
    from ace_platform.core.llm_proxy import calculate_cost
    from ace_platform.db.models import UsageRecord

    if not token_usage or not isinstance(token_usage, dict):
        return

    # Idempotency: if usage records already exist for this job, skip.
    existing = db.execute(
        select(UsageRecord.id).where(UsageRecord.evolution_job_id == evolution_job_id).limit(1)
    ).scalar_one_or_none()
    if existing:
        return

    operations = token_usage.get("operations")
    if not operations or not isinstance(operations, dict):
        return

    for operation, info in operations.items():
        if not isinstance(info, dict):
            continue

        model = info.get("model") or token_usage.get("model") or "unknown"
        prompt_tokens = int(info.get("prompt_tokens", 0) or 0)
        completion_tokens = int(info.get("completion_tokens", 0) or 0)
        total_tokens = int(info.get("total_tokens", prompt_tokens + completion_tokens) or 0)

        cost_usd = calculate_cost(str(model), prompt_tokens, completion_tokens)

        db.add(
            UsageRecord(
                user_id=user_id,
                playbook_id=playbook_id,
                evolution_job_id=evolution_job_id,
                operation=str(operation),
                model=str(model),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost_usd=cost_usd,
            )
        )


def _create_diff_summary(operations: list[dict]) -> str:
    """Create a human-readable summary of operations applied.

    Args:
        operations: List of operation dicts from evolution.

    Returns:
        Summary string.
    """
    if not operations:
        return "No changes made"

    lines = []
    for op in operations[:10]:  # Limit to first 10 operations
        op_type = op.get("type", "unknown")
        if op_type == "add":
            lines.append(f"+ Added: {op.get('text', '')[:50]}...")
        elif op_type == "remove":
            lines.append(f"- Removed: {op.get('text', '')[:50]}...")
        elif op_type == "modify":
            lines.append(f"~ Modified: {op.get('text', '')[:50]}...")
        else:
            lines.append(f"? {op_type}: {str(op)[:50]}...")

    if len(operations) > 10:
        lines.append(f"... and {len(operations) - 10} more operations")

    return "\n".join(lines) if lines else "No specific operations recorded"
