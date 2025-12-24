"""Tests for automatic evolution triggering task.

These tests verify:
1. Task registration and configuration
2. Beat schedule configuration
3. Trigger logic (outcome count and time thresholds)
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4


class TestAutoEvolutionTaskRegistration:
    """Tests for task registration and configuration."""

    def test_task_is_registered(self):
        """Test that auto-evolution task is registered with Celery."""
        from ace_platform.workers.celery_app import celery_app

        assert "ace_platform.workers.auto_evolution.check_auto_evolution" in celery_app.tasks

    def test_task_is_in_beat_schedule(self):
        """Test that task is configured in beat schedule."""
        from ace_platform.workers.celery_app import celery_app

        assert "check-auto-evolution" in celery_app.conf.beat_schedule
        schedule_entry = celery_app.conf.beat_schedule["check-auto-evolution"]
        assert schedule_entry["task"] == "ace_platform.workers.auto_evolution.check_auto_evolution"

    def test_beat_schedule_runs_every_5_minutes(self):
        """Test beat schedule runs every 5 minutes."""
        from celery.schedules import crontab

        from ace_platform.workers.celery_app import celery_app

        schedule_entry = celery_app.conf.beat_schedule["check-auto-evolution"]
        schedule = schedule_entry["schedule"]
        assert isinstance(schedule, crontab)
        assert schedule._orig_minute == "*/5"


class TestAutoEvolutionTaskImports:
    """Tests for task imports."""

    def test_import_from_workers_package(self):
        """Test task can be imported from workers package."""
        from ace_platform.workers import check_auto_evolution

        assert check_auto_evolution is not None

    def test_import_directly(self):
        """Test task can be imported directly from module."""
        from ace_platform.workers.auto_evolution import check_auto_evolution

        assert check_auto_evolution is not None


class TestAutoEvolutionThresholds:
    """Tests for default threshold values."""

    def test_default_outcome_threshold(self):
        """Test default outcome threshold is 5."""
        from ace_platform.workers.auto_evolution import DEFAULT_OUTCOME_THRESHOLD

        assert DEFAULT_OUTCOME_THRESHOLD == 5

    def test_default_time_threshold(self):
        """Test default time threshold is 24 hours."""
        from ace_platform.workers.auto_evolution import DEFAULT_TIME_THRESHOLD_HOURS

        assert DEFAULT_TIME_THRESHOLD_HOURS == 24


class TestCheckAndTriggerEvolutions:
    """Tests for _check_and_trigger_evolutions function."""

    def test_no_active_playbooks(self):
        """Test with no active playbooks."""
        from ace_platform.workers.auto_evolution import _check_and_trigger_evolutions

        mock_db = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = _check_and_trigger_evolutions(mock_db)

        assert result["playbooks_checked"] == 0
        assert result["jobs_queued"] == 0

    def test_playbook_with_no_outcomes(self):
        """Test playbook with no unprocessed outcomes."""
        from ace_platform.db.models import PlaybookStatus
        from ace_platform.workers.auto_evolution import _check_and_trigger_evolutions

        mock_db = MagicMock()

        # Mock playbook
        mock_playbook = MagicMock()
        mock_playbook.id = uuid4()
        mock_playbook.status = PlaybookStatus.ACTIVE
        mock_playbook.current_version_id = uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_playbook]
        mock_db.execute.return_value = mock_result

        # No existing job
        mock_db.execute.return_value.scalar_one_or_none.return_value = None

        # No unprocessed outcomes
        mock_db.scalar.return_value = 0

        result = _check_and_trigger_evolutions(mock_db)

        assert result["playbooks_checked"] == 1
        assert result["jobs_queued"] == 0

    def test_skips_playbook_with_running_job(self):
        """Test that playbooks with running jobs are skipped."""
        from ace_platform.db.models import EvolutionJobStatus, PlaybookStatus
        from ace_platform.workers.auto_evolution import _check_and_trigger_evolutions

        mock_db = MagicMock()

        # Mock playbook
        mock_playbook = MagicMock()
        mock_playbook.id = uuid4()
        mock_playbook.status = PlaybookStatus.ACTIVE

        # First call returns playbooks, second returns existing job
        mock_playbooks_result = MagicMock()
        mock_playbooks_result.scalars.return_value.all.return_value = [mock_playbook]

        mock_job_result = MagicMock()
        mock_existing_job = MagicMock()
        mock_existing_job.status = EvolutionJobStatus.RUNNING
        mock_job_result.scalar_one_or_none.return_value = mock_existing_job

        mock_db.execute.side_effect = [mock_playbooks_result, mock_job_result]

        result = _check_and_trigger_evolutions(mock_db)

        assert result["playbooks_checked"] == 1
        assert result["jobs_queued"] == 0
        assert result["skipped_running"] == 1

    @patch("ace_platform.workers.evolution_task.process_evolution_job")
    def test_triggers_on_outcome_threshold(self, mock_process_job):
        """Test evolution triggers when outcome count meets threshold."""
        from ace_platform.db.models import PlaybookStatus
        from ace_platform.workers.auto_evolution import _check_and_trigger_evolutions

        mock_db = MagicMock()

        # Mock playbook
        mock_playbook = MagicMock()
        mock_playbook.id = uuid4()
        mock_playbook.status = PlaybookStatus.ACTIVE
        mock_playbook.current_version_id = uuid4()

        mock_playbooks_result = MagicMock()
        mock_playbooks_result.scalars.return_value.all.return_value = [mock_playbook]

        # No existing job
        mock_job_result = MagicMock()
        mock_job_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [mock_playbooks_result, mock_job_result]

        # 5 unprocessed outcomes (meets threshold)
        mock_db.scalar.return_value = 5

        result = _check_and_trigger_evolutions(mock_db, outcome_threshold=5)

        assert result["jobs_queued"] == 1
        mock_process_job.delay.assert_called_once()

    @patch("ace_platform.workers.evolution_task.process_evolution_job")
    def test_triggers_on_time_threshold(self, mock_process_job):
        """Test evolution triggers when time threshold is met."""
        from ace_platform.db.models import EvolutionJobStatus, PlaybookStatus
        from ace_platform.workers.auto_evolution import _check_and_trigger_evolutions

        mock_db = MagicMock()

        # Mock playbook created 48 hours ago
        mock_playbook = MagicMock()
        mock_playbook.id = uuid4()
        mock_playbook.status = PlaybookStatus.ACTIVE
        mock_playbook.current_version_id = uuid4()
        mock_playbook.created_at = datetime.now(UTC) - timedelta(hours=48)

        mock_playbooks_result = MagicMock()
        mock_playbooks_result.scalars.return_value.all.return_value = [mock_playbook]

        # No existing running job
        mock_job_result = MagicMock()
        mock_job_result.scalar_one_or_none.return_value = None

        # Last completed job was 25 hours ago
        mock_last_evolution_result = MagicMock()
        mock_last_evolution = MagicMock()
        mock_last_evolution.status = EvolutionJobStatus.COMPLETED
        mock_last_evolution.completed_at = datetime.now(UTC) - timedelta(hours=25)
        mock_last_evolution_result.scalar_one_or_none.return_value = mock_last_evolution

        mock_db.execute.side_effect = [
            mock_playbooks_result,
            mock_job_result,
            mock_last_evolution_result,
        ]

        # 2 unprocessed outcomes (below threshold but time threshold met)
        mock_db.scalar.return_value = 2

        result = _check_and_trigger_evolutions(
            mock_db, outcome_threshold=5, time_threshold_hours=24
        )

        assert result["jobs_queued"] == 1
        mock_process_job.delay.assert_called_once()

    def test_does_not_trigger_below_thresholds(self):
        """Test no trigger when both thresholds are not met."""
        from ace_platform.db.models import EvolutionJobStatus, PlaybookStatus
        from ace_platform.workers.auto_evolution import _check_and_trigger_evolutions

        mock_db = MagicMock()

        # Mock playbook
        mock_playbook = MagicMock()
        mock_playbook.id = uuid4()
        mock_playbook.status = PlaybookStatus.ACTIVE
        mock_playbook.current_version_id = uuid4()

        mock_playbooks_result = MagicMock()
        mock_playbooks_result.scalars.return_value.all.return_value = [mock_playbook]

        # No existing running job
        mock_job_result = MagicMock()
        mock_job_result.scalar_one_or_none.return_value = None

        # Last completed job was 12 hours ago (within time threshold)
        mock_last_evolution_result = MagicMock()
        mock_last_evolution = MagicMock()
        mock_last_evolution.status = EvolutionJobStatus.COMPLETED
        mock_last_evolution.completed_at = datetime.now(UTC) - timedelta(hours=12)
        mock_last_evolution_result.scalar_one_or_none.return_value = mock_last_evolution

        mock_db.execute.side_effect = [
            mock_playbooks_result,
            mock_job_result,
            mock_last_evolution_result,
        ]

        # 3 unprocessed outcomes (below threshold of 5)
        mock_db.scalar.return_value = 3

        result = _check_and_trigger_evolutions(
            mock_db, outcome_threshold=5, time_threshold_hours=24
        )

        assert result["jobs_queued"] == 0


class TestCheckAutoEvolutionTask:
    """Tests for the main check_auto_evolution task."""

    @patch("ace_platform.workers.auto_evolution.SyncSessionLocal")
    @patch("ace_platform.workers.auto_evolution._check_and_trigger_evolutions")
    def test_task_calls_check_function(self, mock_check_fn, mock_session_class):
        """Test that task calls the check function with session."""
        from ace_platform.workers.auto_evolution import check_auto_evolution

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session_class.return_value = mock_session

        mock_check_fn.return_value = {
            "status": "completed",
            "playbooks_checked": 10,
            "jobs_queued": 2,
        }

        result = check_auto_evolution()

        mock_check_fn.assert_called_once()
        assert result["status"] == "completed"
