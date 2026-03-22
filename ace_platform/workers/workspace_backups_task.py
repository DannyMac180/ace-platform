"""Compatibility shim for the hosted workspace backup task."""

import logging

from ace_platform.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
MOVED_MESSAGE = (
    "Hosted personal workspace backups moved to ace-private. "
    "Run the canonical worker task from the private repo instead of this public shim."
)


@celery_app.task(
    bind=True,
    name="ace_platform.workers.workspace_backups_task.backup_hosted_personal_workspaces",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def backup_hosted_personal_workspaces_task(self) -> dict:
    """Return a compatibility redirect for the hosted/private task."""

    del self
    logger.info(
        "Hosted personal workspace backup task called from public repo shim",
        extra={"redirect_message": MOVED_MESSAGE},
    )
    return {
        "status": "moved",
        "message": MOVED_MESSAGE,
    }
