"""ACE Platform background workers.

This package contains Celery workers for background task processing:
- celery_app: Main Celery application configuration
- evolution_task: Playbook evolution processing task
- auto_evolution: Automatic evolution triggering periodic task

Usage:
    # Start worker for all queues
    celery -A ace_platform.workers.celery_app worker -l info

    # Start worker for evolution queue only
    celery -A ace_platform.workers.celery_app worker -l info -Q evolution

    # Start beat scheduler for periodic tasks
    celery -A ace_platform.workers.celery_app beat -l info
"""

from ace_platform.workers.auto_evolution import check_auto_evolution
from ace_platform.workers.celery_app import celery_app
from ace_platform.workers.evolution_task import process_evolution_job

__all__ = ["celery_app", "process_evolution_job", "check_auto_evolution"]
