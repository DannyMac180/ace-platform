"""Celery task for processing evolution jobs.

This task handles background playbook evolution:
1. Fetches unprocessed outcomes for a playbook
2. Runs the ACE evolution service
3. Creates a new playbook version with the evolved content
4. Updates job and outcome records
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from ace_platform.core.evolution import EvolutionService, OutcomeData
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

    with SyncSessionLocal() as db:
        # Fetch the job
        job = db.get(EvolutionJob, job_uuid)
        if not job:
            return {"status": "error", "message": f"Job {job_id} not found"}

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

        try:
            result = _execute_evolution(db, job)
            return result
        except Exception as e:
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
        # Count bullets
        bullet_count = evolution_result.evolved_playbook.count("\n- ")
        bullet_count += evolution_result.evolved_playbook.count("\n* ")
        if evolution_result.evolved_playbook.startswith(
            "- "
        ) or evolution_result.evolved_playbook.startswith("* "):
            bullet_count += 1

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

    db.commit()

    return {
        "status": "completed",
        "job_id": str(job.id),
        "outcomes_processed": len(outcomes),
        "new_version": new_version.version_number if new_version else None,
        "has_changes": evolution_result.has_changes,
    }


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
