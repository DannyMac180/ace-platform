"""Tests for Prometheus metrics collection.

These tests verify:
1. Metric registry and counters
2. Helper functions for recording metrics
3. Metrics endpoint
"""

import pytest
from prometheus_client import REGISTRY

from ace_platform.core.metrics import (
    ACTIVE_EVOLUTION_JOBS,
    EVOLUTIONS_BY_STATUS,
    EVOLUTIONS_TRIGGERED,
    OUTCOMES_BY_STATUS,
    TOKENS_COST_USD,
    TOKENS_USED,
    decrement_active_jobs,
    get_metrics_registry,
    increment_active_jobs,
    increment_evolution_triggered,
    increment_outcome,
    observe_evolution,
    record_token_usage,
    set_active_jobs,
)


class TestMetricRegistry:
    """Tests for metric registry setup."""

    def test_registry_exists(self):
        """Test that the default registry is accessible."""
        registry = get_metrics_registry()
        assert registry is REGISTRY

    def test_counters_registered(self):
        """Test that key counters are registered."""
        # Check some metrics are in the registry
        # Note: Counter names don't include _total suffix in registry
        metric_names = [m.name for m in REGISTRY.collect()]
        assert "ace_outcomes_by_status" in str(metric_names)
        assert "ace_evolutions_triggered" in str(metric_names)


class TestOutcomeMetrics:
    """Tests for outcome metrics recording."""

    def test_increment_outcome_success(self):
        """Test recording a successful outcome."""
        # Get baseline count
        before = OUTCOMES_BY_STATUS.labels(status="success")._value.get()

        increment_outcome(status="success", playbook_id="test-123")

        after = OUTCOMES_BY_STATUS.labels(status="success")._value.get()
        assert after == before + 1

    def test_increment_outcome_failure(self):
        """Test recording a failed outcome."""
        before = OUTCOMES_BY_STATUS.labels(status="failure")._value.get()

        increment_outcome(status="failure")

        after = OUTCOMES_BY_STATUS.labels(status="failure")._value.get()
        assert after == before + 1

    def test_increment_outcome_partial(self):
        """Test recording a partial outcome."""
        before = OUTCOMES_BY_STATUS.labels(status="partial")._value.get()

        increment_outcome(status="partial")

        after = OUTCOMES_BY_STATUS.labels(status="partial")._value.get()
        assert after == before + 1


class TestEvolutionMetrics:
    """Tests for evolution metrics recording."""

    def test_increment_evolution_triggered_manual(self):
        """Test recording a manual evolution trigger."""
        before = EVOLUTIONS_TRIGGERED.labels(trigger_type="manual")._value.get()

        increment_evolution_triggered(trigger_type="manual")

        after = EVOLUTIONS_TRIGGERED.labels(trigger_type="manual")._value.get()
        assert after == before + 1

    def test_increment_evolution_triggered_auto(self):
        """Test recording an auto evolution trigger."""
        before = EVOLUTIONS_TRIGGERED.labels(trigger_type="auto")._value.get()

        increment_evolution_triggered(trigger_type="auto")

        after = EVOLUTIONS_TRIGGERED.labels(trigger_type="auto")._value.get()
        assert after == before + 1

    def test_observe_evolution_completed(self):
        """Test recording a completed evolution."""
        before = EVOLUTIONS_BY_STATUS.labels(status="completed")._value.get()

        observe_evolution(
            status="completed",
            playbook_id="test-playbook",
            duration_seconds=45.5,
            tokens_used=1500,
            model="gpt-4o",
        )

        after = EVOLUTIONS_BY_STATUS.labels(status="completed")._value.get()
        assert after == before + 1

    def test_observe_evolution_failed(self):
        """Test recording a failed evolution."""
        before = EVOLUTIONS_BY_STATUS.labels(status="failed")._value.get()

        observe_evolution(
            status="failed",
            playbook_id="test-playbook",
            duration_seconds=10.2,
        )

        after = EVOLUTIONS_BY_STATUS.labels(status="failed")._value.get()
        assert after == before + 1


class TestTokenMetrics:
    """Tests for token usage metrics."""

    def test_record_token_usage(self):
        """Test recording token usage."""
        model = "gpt-4o-test"
        before_prompt = TOKENS_USED.labels(model=model, token_type="prompt")._value.get()
        before_completion = TOKENS_USED.labels(model=model, token_type="completion")._value.get()
        before_cost = TOKENS_COST_USD.labels(model=model)._value.get()

        record_token_usage(
            model=model,
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.005,
        )

        after_prompt = TOKENS_USED.labels(model=model, token_type="prompt")._value.get()
        after_completion = TOKENS_USED.labels(model=model, token_type="completion")._value.get()
        after_cost = TOKENS_COST_USD.labels(model=model)._value.get()

        assert after_prompt == before_prompt + 100
        assert after_completion == before_completion + 50
        assert after_cost == pytest.approx(before_cost + 0.005, rel=1e-6)


class TestActiveJobsGauge:
    """Tests for active jobs gauge."""

    def test_set_active_jobs(self):
        """Test setting active jobs count."""
        set_active_jobs(5)
        assert ACTIVE_EVOLUTION_JOBS._value.get() == 5

        set_active_jobs(0)
        assert ACTIVE_EVOLUTION_JOBS._value.get() == 0

    def test_increment_active_jobs(self):
        """Test incrementing active jobs."""
        set_active_jobs(0)
        increment_active_jobs()
        assert ACTIVE_EVOLUTION_JOBS._value.get() == 1

        increment_active_jobs()
        assert ACTIVE_EVOLUTION_JOBS._value.get() == 2

    def test_decrement_active_jobs(self):
        """Test decrementing active jobs."""
        set_active_jobs(5)
        decrement_active_jobs()
        assert ACTIVE_EVOLUTION_JOBS._value.get() == 4


class TestMetricsEndpoint:
    """Tests for the /metrics endpoint."""

    @pytest.fixture
    def app(self):
        """Create test FastAPI app."""
        from ace_platform.api.main import create_app

        return create_app()

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        from fastapi.testclient import TestClient

        return TestClient(app)

    def test_metrics_endpoint_exists(self, client):
        """Test that metrics endpoint returns 200."""
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_content_type(self, client):
        """Test that metrics returns correct content type."""
        response = client.get("/metrics")
        content_type = response.headers.get("content-type", "")
        assert "text/plain" in content_type or "text/plain; version=0.0.4" in content_type

    def test_metrics_contains_ace_metrics(self, client):
        """Test that response contains ACE Platform metrics."""
        response = client.get("/metrics")
        content = response.text

        # Check for our custom metrics
        assert "ace_outcomes" in content or "ace_evolutions" in content
        assert "ace_platform_info" in content

    def test_metrics_not_in_openapi(self, client):
        """Test that metrics endpoint is not in OpenAPI schema."""
        openapi = client.app.openapi()
        paths = openapi.get("paths", {})
        assert "/metrics" not in paths


class TestMetricGracefulFailure:
    """Tests for graceful failure handling."""

    def test_increment_outcome_handles_errors(self):
        """Test that increment_outcome doesn't raise on errors."""
        # Should not raise even with unusual input
        increment_outcome(status="success", playbook_id=None)
        # Test passes if no exception raised

    def test_observe_evolution_handles_errors(self):
        """Test that observe_evolution doesn't raise on errors."""
        # Should not raise even with partial data
        observe_evolution(status="completed")
        observe_evolution(status="failed", duration_seconds=None)
        # Test passes if no exception raised

    def test_record_token_usage_handles_errors(self):
        """Test that record_token_usage doesn't raise on errors."""
        # Should handle edge cases gracefully
        record_token_usage(
            model="test-model",
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=0.0,
        )
        # Test passes if no exception raised
