"""ACE Platform background workers.

This package contains Celery workers for background task processing:
- evolution_worker: Handles playbook evolution tasks

Usage:
    # Start worker for all queues
    celery -A ace_platform.workers.celery_app worker -l info

    # Start worker for evolution queue only
    celery -A ace_platform.workers.celery_app worker -l info -Q evolution
"""

from ace_platform.workers.celery_app import celery_app

__all__ = ["celery_app"]
