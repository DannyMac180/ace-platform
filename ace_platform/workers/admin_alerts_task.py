"""Celery tasks for admin alerting.

This module provides periodic tasks for:
- Daily spend summary emails to admin
"""

import logging

from ace_platform.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="ace_platform.workers.admin_alerts_task.send_daily_spend_summary",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def send_daily_spend_summary(self):
    """Send daily spend summary to admin.

    This task runs daily and sends a summary of:
    - Total platform spend for the day
    - Top 5 users by spend this month
    - Users who exceeded the configured threshold percentage of their tier limit

    The task uses sync database access to work with Celery.
    """
    import asyncio

    from ace_platform.core.admin_alerts import is_admin_alerts_enabled
    from ace_platform.core.admin_alerts import send_daily_spend_summary as send_summary
    from ace_platform.db.session import async_session_factory

    # Check if alerts are enabled
    if not is_admin_alerts_enabled():
        logger.info("Admin alerts not enabled, skipping daily summary task")
        return {"status": "skipped", "reason": "Admin alerts not configured"}

    async def _run():
        async with async_session_factory() as db:
            result = await send_summary(db)
            return result

    try:
        result = asyncio.run(_run())

        if result.success:
            logger.info(
                "Daily spend summary task completed",
                extra={
                    "email_sent": result.email_sent,
                    "slack_sent": result.slack_sent,
                },
            )
            return {
                "status": "success",
                "email_sent": result.email_sent,
                "slack_sent": result.slack_sent,
            }
        else:
            logger.warning(f"Daily spend summary task failed: {result.error}")
            return {
                "status": "failed",
                "error": result.error,
            }

    except Exception as e:
        logger.error(f"Daily spend summary task error: {e}", exc_info=True)
        raise  # Let Celery handle retry
