"""Tests for Celery application configuration.

These tests verify:
1. Celery app is properly configured
2. Redis broker/backend settings
3. Task configuration
4. Health check task works
"""


class TestCeleryAppConfiguration:
    """Tests for Celery app configuration."""

    def test_celery_app_exists(self):
        """Test that celery_app is importable."""
        from ace_platform.workers import celery_app

        assert celery_app is not None

    def test_celery_app_name(self):
        """Test Celery app has correct name."""
        from ace_platform.workers import celery_app

        assert celery_app.main == "ace_platform"

    def test_broker_url_configured(self):
        """Test broker URL is set from settings."""
        from ace_platform.workers import celery_app

        assert celery_app.conf.broker_url is not None
        assert "redis" in celery_app.conf.broker_url

    def test_result_backend_configured(self):
        """Test result backend is set from settings."""
        from ace_platform.workers import celery_app

        assert celery_app.conf.result_backend is not None
        assert "redis" in celery_app.conf.result_backend

    def test_task_serializer_is_json(self):
        """Test tasks use JSON serialization."""
        from ace_platform.workers import celery_app

        assert celery_app.conf.task_serializer == "json"
        assert celery_app.conf.result_serializer == "json"
        assert "json" in celery_app.conf.accept_content

    def test_timezone_is_utc(self):
        """Test timezone is set to UTC."""
        from ace_platform.workers import celery_app

        assert celery_app.conf.timezone == "UTC"
        assert celery_app.conf.enable_utc is True

    def test_task_acks_late_enabled(self):
        """Test task acknowledgment is set to late (reliability)."""
        from ace_platform.workers import celery_app

        assert celery_app.conf.task_acks_late is True

    def test_task_queues_configured(self):
        """Test task queues are defined."""
        from ace_platform.workers import celery_app

        queues = celery_app.conf.task_queues
        assert "default" in queues
        assert "evolution" in queues

    def test_result_expires_set(self):
        """Test result expiration is configured."""
        from ace_platform.workers import celery_app

        assert celery_app.conf.result_expires == 86400  # 24 hours

    def test_time_limits_configured(self):
        """Test task time limits are set."""
        from ace_platform.workers import celery_app

        assert celery_app.conf.task_soft_time_limit == 300  # 5 minutes
        assert celery_app.conf.task_time_limit == 360  # 6 minutes


class TestHealthCheckTask:
    """Tests for health check task."""

    def test_health_check_task_registered(self):
        """Test health check task is registered."""
        from ace_platform.workers.celery_app import health_check

        assert health_check is not None
        assert health_check.name == "ace_platform.health_check"

    def test_health_check_returns_dict(self):
        """Test health check task returns expected structure."""
        from ace_platform.workers.celery_app import health_check

        # Call task synchronously (not through Celery)
        # This tests the task function logic
        result = health_check()

        assert isinstance(result, dict)
        assert result["status"] == "healthy"
        # task_id and worker will be None when called directly
        assert "task_id" in result
        assert "worker" in result


class TestCeleryAppImports:
    """Tests for Celery app module imports."""

    def test_import_from_workers_package(self):
        """Test celery_app is exported from workers package."""
        from ace_platform.workers import celery_app

        assert celery_app is not None

    def test_import_celery_app_directly(self):
        """Test celery_app can be imported directly."""
        from ace_platform.workers.celery_app import celery_app

        assert celery_app is not None

    def test_import_health_check_task(self):
        """Test health_check task can be imported."""
        from ace_platform.workers.celery_app import health_check

        assert health_check is not None
