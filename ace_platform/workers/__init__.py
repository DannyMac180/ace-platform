"""ACE Platform background workers.

This package contains Celery workers for background task processing:
- celery_app: Main Celery application configuration
- evolution_task: Playbook evolution processing task

Usage:
    # Start worker for all queues
    celery -A ace_platform.workers.celery_app worker -l info

    # Start worker for evolution queue only
    celery -A ace_platform.workers.celery_app worker -l info -Q evolution
"""

from ace_platform.workers.celery_app import celery_app
from ace_platform.workers.evolution_task import process_evolution_job

__all__ = ["celery_app", "process_evolution_job"]
