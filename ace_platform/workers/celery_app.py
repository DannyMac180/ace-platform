"""Celery application configuration for ACE Platform.

This module sets up the Celery application with Redis as the broker
and result backend. It configures task autodiscovery and provides
the main entry point for running Celery workers.

Usage:
    # Start worker
    celery -A ace_platform.workers.celery_app worker -l info

    # Start beat scheduler (for periodic tasks)
    celery -A ace_platform.workers.celery_app beat -l info
"""

from celery import Celery

from ace_platform.config import get_settings

settings = get_settings()

# Create Celery application
celery_app = Celery(
    "ace_platform",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task execution settings
    task_acks_late=True,  # Acknowledge after task completes (reliability)
    task_reject_on_worker_lost=True,  # Requeue if worker dies
    worker_prefetch_multiplier=1,  # One task at a time per worker
    # Result backend settings
    result_expires=86400,  # Results expire after 24 hours
    result_extended=True,  # Store task args/kwargs with results
    # Task routing
    task_default_queue="default",
    task_queues={
        "default": {},
        "evolution": {},  # Dedicated queue for evolution tasks
    },
    # Retry settings
    task_default_retry_delay=60,  # 1 minute delay between retries
    task_max_retries=3,
    # Concurrency settings (can be overridden via CLI)
    worker_concurrency=4,
    # Task time limits
    task_soft_time_limit=300,  # 5 minute soft limit (raises SoftTimeLimitExceeded)
    task_time_limit=360,  # 6 minute hard limit (kills task)
    # Logging
    worker_hijack_root_logger=False,  # Don't override app logging
)

# Autodiscover tasks from worker modules
celery_app.autodiscover_tasks(
    [
        "ace_platform.workers",
    ]
)


@celery_app.task(bind=True, name="ace_platform.health_check")
def health_check(self):
    """Simple health check task to verify Celery is working.

    Returns:
        dict: Status information including task ID.
    """
    return {
        "status": "healthy",
        "task_id": self.request.id,
        "worker": self.request.hostname,
    }
