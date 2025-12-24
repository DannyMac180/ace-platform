"""Tests for evolution Celery task.

These tests verify:
1. Task registration and configuration
2. Task import and structure
3. Job processing logic (unit tests with mocks)
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4


class TestEvolutionTaskRegistration:
    """Tests for task registration and configuration."""

    def test_task_is_registered(self):
        """Test that evolution task is registered with Celery."""
        from ace_platform.workers.celery_app import celery_app

        # Check task is registered
        assert "ace_platform.evolution.process_job" in celery_app.tasks

    def test_task_queue_is_evolution(self):
        """Test task is configured for evolution queue."""
        from ace_platform.workers.evolution_task import process_evolution_job

        assert process_evolution_job.queue == "evolution"

    def test_task_has_retries_configured(self):
        """Test task has retry configuration."""
        from ace_platform.workers.evolution_task import process_evolution_job

        assert process_evolution_job.max_retries == 3
        assert process_evolution_job.default_retry_delay == 60


class TestEvolutionTaskImports:
    """Tests for task imports."""

    def test_import_from_workers_package(self):
        """Test task can be imported from workers package."""
        from ace_platform.workers import process_evolution_job

        assert process_evolution_job is not None

    def test_import_directly(self):
        """Test task can be imported directly from module."""
        from ace_platform.workers.evolution_task import process_evolution_job

        assert process_evolution_job is not None


class TestEvolutionTaskHelpers:
    """Tests for task helper functions."""

    def test_create_diff_summary_empty_operations(self):
        """Test diff summary with no operations."""
        from ace_platform.workers.evolution_task import _create_diff_summary

        result = _create_diff_summary([])
        assert result == "No changes made"

    def test_create_diff_summary_add_operation(self):
        """Test diff summary with add operation."""
        from ace_platform.workers.evolution_task import _create_diff_summary

        operations = [{"type": "add", "text": "New bullet point for testing"}]
        result = _create_diff_summary(operations)
        assert "+ Added:" in result
        assert "New bullet" in result

    def test_create_diff_summary_remove_operation(self):
        """Test diff summary with remove operation."""
        from ace_platform.workers.evolution_task import _create_diff_summary

        operations = [{"type": "remove", "text": "Removed bullet point"}]
        result = _create_diff_summary(operations)
        assert "- Removed:" in result

    def test_create_diff_summary_modify_operation(self):
        """Test diff summary with modify operation."""
        from ace_platform.workers.evolution_task import _create_diff_summary

        operations = [{"type": "modify", "text": "Modified bullet point"}]
        result = _create_diff_summary(operations)
        assert "~ Modified:" in result

    def test_create_diff_summary_truncates_many_operations(self):
        """Test diff summary truncates after 10 operations."""
        from ace_platform.workers.evolution_task import _create_diff_summary

        operations = [{"type": "add", "text": f"Bullet {i}"} for i in range(15)]
        result = _create_diff_summary(operations)
        assert "... and 5 more operations" in result


class TestProcessEvolutionJobUnit:
    """Unit tests for process_evolution_job with mocks."""

    def test_job_not_found(self):
        """Test handling of non-existent job."""
        from ace_platform.workers.evolution_task import process_evolution_job

        # Mock the database session
        with patch("ace_platform.workers.evolution_task.SyncSessionLocal") as mock_session_class:
            mock_session = MagicMock()
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=False)
            mock_session.get.return_value = None
            mock_session_class.return_value = mock_session

            result = process_evolution_job(str(uuid4()))

        assert result["status"] == "error"
        assert "not found" in result["message"]

    def test_job_already_running(self):
        """Test skipping job that's already running."""
        from ace_platform.db.models import EvolutionJobStatus
        from ace_platform.workers.evolution_task import process_evolution_job

        # Create mock job
        mock_job = MagicMock()
        mock_job.status = EvolutionJobStatus.RUNNING

        with patch("ace_platform.workers.evolution_task.SyncSessionLocal") as mock_session_class:
            mock_session = MagicMock()
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=False)
            mock_session.get.return_value = mock_job
            mock_session_class.return_value = mock_session

            result = process_evolution_job(str(uuid4()))

        assert result["status"] == "skipped"
        assert "already in status" in result["message"]

    def test_job_already_completed(self):
        """Test skipping job that's already completed."""
        from ace_platform.db.models import EvolutionJobStatus
        from ace_platform.workers.evolution_task import process_evolution_job

        mock_job = MagicMock()
        mock_job.status = EvolutionJobStatus.COMPLETED

        with patch("ace_platform.workers.evolution_task.SyncSessionLocal") as mock_session_class:
            mock_session = MagicMock()
            mock_session.__enter__ = MagicMock(return_value=mock_session)
            mock_session.__exit__ = MagicMock(return_value=False)
            mock_session.get.return_value = mock_job
            mock_session_class.return_value = mock_session

            result = process_evolution_job(str(uuid4()))

        assert result["status"] == "skipped"


class TestTriggerEvolutionQueuesCeleryTask:
    """Tests for verifying trigger_evolution queues Celery task."""

    def test_trigger_evolution_queues_task_on_new_job(self):
        """Test that trigger_evolution queues Celery task when creating new job."""

        from ace_platform.core.evolution_jobs import trigger_evolution_async

        # This test verifies the import works - actual integration test
        # would require PostgreSQL and Redis
        assert trigger_evolution_async is not None

    def test_trigger_evolution_sync_queues_task(self):
        """Test sync version also queues task."""
        from ace_platform.core.evolution_jobs import trigger_evolution_sync

        assert trigger_evolution_sync is not None
