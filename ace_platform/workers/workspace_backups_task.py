"""Celery task for hosted personal workspace backups."""

import asyncio
import logging

from ace_platform.core.workspace_backups import backup_hosted_personal_workspaces
from ace_platform.db.session import async_session_factory
from ace_platform.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="ace_platform.workers.workspace_backups_task.backup_hosted_personal_workspaces",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def backup_hosted_personal_workspaces_task(self) -> dict:
    """Run the scheduled hosted-personal workspace backup sweep."""

    async def _run() -> dict:
        async with async_session_factory() as db:
            return await backup_hosted_personal_workspaces(db)

    result = asyncio.run(_run())
    logger.info(
        "Hosted personal workspace backup sweep completed",
        extra=result,
    )
    return {
        "status": "success",
        **result,
    }
