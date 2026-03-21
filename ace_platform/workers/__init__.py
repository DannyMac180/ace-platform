"""ACE Platform background workers.

This package contains Celery workers for background task processing:
- celery_app: Main Celery application configuration
- evolution_task: Playbook evolution processing task
- auto_evolution: Automatic evolution triggering periodic task
- workspace_backups_task: Hosted personal backup sweeps

Usage:
    # Start worker for all queues
    ace-platform-worker

    # Start worker for evolution queue only
    ace-platform-worker -Q evolution

    # Start beat scheduler for periodic tasks
    ace-platform-beat
"""

from ace_platform.workers.admin_alerts_task import send_daily_spend_summary
from ace_platform.workers.auto_evolution import check_auto_evolution
from ace_platform.workers.celery_app import celery_app
from ace_platform.workers.evolution_task import process_evolution_job
from ace_platform.workers.workspace_backups_task import backup_hosted_personal_workspaces_task

__all__ = [
    "celery_app",
    "process_evolution_job",
    "check_auto_evolution",
    "send_daily_spend_summary",
    "backup_hosted_personal_workspaces_task",
]
