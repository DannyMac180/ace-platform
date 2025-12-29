"""Prometheus metrics for ACE Platform observability.

This module provides application-level metrics for monitoring:
- Outcome recording (counts by status)
- Evolution jobs (triggered, succeeded, failed)
- Evolution duration (histogram)
- Token usage by model

Metrics are exposed in Prometheus format at /metrics endpoint.

Usage:
    from ace_platform.core.metrics import (
        OUTCOMES_TOTAL,
        EVOLUTIONS_TRIGGERED,
        EVOLUTION_DURATION,
        increment_outcome,
        observe_evolution,
    )

    # Record an outcome
    increment_outcome(status="success", playbook_id="abc-123")

    # Observe evolution completion
    observe_evolution(
        status="completed",
        playbook_id="abc-123",
        duration_seconds=45.2,
        tokens_used=1500,
        model="gpt-4o",
    )
"""

import logging
from typing import Literal

from prometheus_client import REGISTRY, Counter, Gauge, Histogram, Info

logger = logging.getLogger(__name__)


# =============================================================================
# Application Info
# =============================================================================

APP_INFO = Info(
    "ace_platform",
    "ACE Platform application information",
)
APP_INFO.info({"version": "1.0.0", "component": "api"})


# =============================================================================
# Outcome Metrics
# =============================================================================

OUTCOMES_TOTAL = Counter(
    "ace_outcomes_total",
    "Total number of outcomes recorded",
    ["status", "playbook_id"],
)

OUTCOMES_BY_STATUS = Counter(
    "ace_outcomes_by_status_total",
    "Total outcomes by status (without playbook dimension)",
    ["status"],
)


# =============================================================================
# Evolution Metrics
# =============================================================================

EVOLUTIONS_TRIGGERED = Counter(
    "ace_evolutions_triggered_total",
    "Total number of evolution jobs triggered",
    ["trigger_type"],  # "manual" or "auto"
)

EVOLUTIONS_COMPLETED = Counter(
    "ace_evolutions_completed_total",
    "Total number of evolution jobs completed",
    ["status", "playbook_id"],  # status: "completed", "failed"
)

EVOLUTIONS_BY_STATUS = Counter(
    "ace_evolutions_by_status_total",
    "Total evolutions by status (without playbook dimension)",
    ["status"],
)

EVOLUTION_DURATION = Histogram(
    "ace_evolution_duration_seconds",
    "Evolution job duration in seconds",
    ["status"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800],  # 1s to 30min
)

EVOLUTION_TOKENS = Histogram(
    "ace_evolution_tokens_used",
    "Tokens used per evolution job",
    ["model"],
    buckets=[100, 500, 1000, 2000, 5000, 10000, 20000, 50000],
)


# =============================================================================
# Token Usage Metrics
# =============================================================================

TOKENS_USED = Counter(
    "ace_tokens_used_total",
    "Total tokens used",
    ["model", "token_type"],  # token_type: "prompt", "completion"
)

TOKENS_COST_USD = Counter(
    "ace_tokens_cost_usd_total",
    "Total cost in USD for token usage",
    ["model"],
)


# =============================================================================
# Active Jobs Gauge
# =============================================================================

ACTIVE_EVOLUTION_JOBS = Gauge(
    "ace_evolution_jobs_active",
    "Number of currently running evolution jobs",
)


# =============================================================================
# Helper Functions
# =============================================================================


OutcomeStatus = Literal["success", "failure", "partial"]
EvolutionStatus = Literal["completed", "failed"]
TriggerType = Literal["manual", "auto"]


def increment_outcome(
    status: OutcomeStatus,
    playbook_id: str | None = None,
) -> None:
    """Record an outcome metric.

    Args:
        status: Outcome status (success, failure, partial)
        playbook_id: Optional playbook ID for dimension
    """
    try:
        # Always increment the status-only counter
        OUTCOMES_BY_STATUS.labels(status=status).inc()

        # Increment playbook-specific counter if provided
        if playbook_id:
            OUTCOMES_TOTAL.labels(status=status, playbook_id=playbook_id).inc()
    except Exception as e:
        logger.warning(f"Failed to record outcome metric: {e}")


def increment_evolution_triggered(trigger_type: TriggerType = "manual") -> None:
    """Record an evolution trigger metric.

    Args:
        trigger_type: How the evolution was triggered (manual or auto)
    """
    try:
        EVOLUTIONS_TRIGGERED.labels(trigger_type=trigger_type).inc()
    except Exception as e:
        logger.warning(f"Failed to record evolution trigger metric: {e}")


def observe_evolution(
    status: EvolutionStatus,
    playbook_id: str | None = None,
    duration_seconds: float | None = None,
    tokens_used: int | None = None,
    model: str | None = None,
) -> None:
    """Record evolution completion metrics.

    Args:
        status: Final status (completed or failed)
        playbook_id: Optional playbook ID for dimension
        duration_seconds: Job duration in seconds
        tokens_used: Total tokens consumed
        model: LLM model used
    """
    try:
        # Status counter
        EVOLUTIONS_BY_STATUS.labels(status=status).inc()

        if playbook_id:
            EVOLUTIONS_COMPLETED.labels(status=status, playbook_id=playbook_id).inc()

        # Duration histogram
        if duration_seconds is not None:
            EVOLUTION_DURATION.labels(status=status).observe(duration_seconds)

        # Token histogram
        if tokens_used is not None and model:
            EVOLUTION_TOKENS.labels(model=model).observe(tokens_used)
    except Exception as e:
        logger.warning(f"Failed to record evolution metric: {e}")


def record_token_usage(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
) -> None:
    """Record token usage metrics.

    Args:
        model: LLM model name
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        cost_usd: Cost in USD
    """
    try:
        TOKENS_USED.labels(model=model, token_type="prompt").inc(prompt_tokens)
        TOKENS_USED.labels(model=model, token_type="completion").inc(completion_tokens)
        TOKENS_COST_USD.labels(model=model).inc(cost_usd)
    except Exception as e:
        logger.warning(f"Failed to record token usage metric: {e}")


def set_active_jobs(count: int) -> None:
    """Set the current number of active evolution jobs.

    Args:
        count: Number of active jobs
    """
    try:
        ACTIVE_EVOLUTION_JOBS.set(count)
    except Exception as e:
        logger.warning(f"Failed to set active jobs gauge: {e}")


def increment_active_jobs() -> None:
    """Increment the active jobs counter."""
    try:
        ACTIVE_EVOLUTION_JOBS.inc()
    except Exception as e:
        logger.warning(f"Failed to increment active jobs: {e}")


def decrement_active_jobs() -> None:
    """Decrement the active jobs counter."""
    try:
        ACTIVE_EVOLUTION_JOBS.dec()
    except Exception as e:
        logger.warning(f"Failed to decrement active jobs: {e}")


def get_metrics_registry():
    """Get the default Prometheus registry.

    Returns:
        The default REGISTRY from prometheus_client
    """
    return REGISTRY
