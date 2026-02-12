"""Shared Sentry initialization helpers.

This module centralizes release derivation, sampling normalization, and startup
logging for Sentry across API, worker, and MCP processes.
"""

import os
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from typing import Any

import sentry_sdk

from ace_platform.config import Settings, get_settings
from ace_platform.core.logging import get_logger

logger = get_logger(__name__)


def _normalize_process_name(process_name: str) -> str:
    """Normalize process/surface name for environment variable lookup."""

    return process_name.strip().replace("-", "_").upper()


def _resolve_process_override(raw: Any, label: str, default: float) -> float:
    """Resolve an explicit raw process override value, with bounds logging."""

    if raw is None:
        return default
    return _coerce_sample_rate(raw, label, default=default)


def _resolve_sample_rate_for_process(
    process_name: str,
    base_env_name: str,
    default: float,
) -> float:
    """Resolve process-specific sample rate from env override + global fallback."""

    normalized = _normalize_process_name(process_name)
    process_env = os.getenv(f"{base_env_name}_{normalized}")
    if process_env is not None:
        return _resolve_process_override(
            process_env,
            f"{base_env_name}_{normalized}",
            default=default,
        )

    if base_env_name in os.environ:
        return _resolve_process_override(
            os.getenv(base_env_name),
            base_env_name,
            default=default,
        )

    return default


def _coerce_sample_rate(value: Any, label: str, default: float) -> float:
    """Convert a value to a bounded Sentry sample rate.

    Args:
        value: Raw sample rate value.
        label: Field name for log messages.
        default: Fallback value when conversion fails.

    Returns:
        Clamped float in the closed interval [0.0, 1.0].
    """

    if value is None:
        return default

    try:
        rate = float(value)
    except (TypeError, ValueError):
        logger.warning("Invalid Sentry %s rate %r; using default %s", label, value, default)
        return default

    if rate < 0.0:
        logger.warning("Sentry %s rate %s below 0.0; clamped to 0.0", label, rate)
        return 0.0
    if rate > 1.0:
        logger.warning("Sentry %s rate %s above 1.0; clamped to 1.0", label, rate)
        return 1.0
    return rate


def _default_app_version() -> str:
    """Return the package version for release labeling.

    Falls back to a local sentinel when package metadata is unavailable.
    """

    try:
        return package_version("ace-platform")
    except PackageNotFoundError:
        return "unknown"


def resolve_sentry_release(settings: Settings, process_name: str | None = None) -> str:
    """Resolve Sentry release metadata.

    Preference order:
      1. explicit ``SENTRY_RELEASE`` setting
      2. ``SENTRY_RELEASE_<PROCESS>`` environment variable
      3. ``SENTRY_RELEASE`` global environment variable
      4. CI/runtime hints such as ``GITHUB_SHA``
      5. package version fallback
    """

    configured = settings.sentry_release
    if configured:
        return configured

    if process_name:
        normalized = _normalize_process_name(process_name)
        process_specific_release = os.getenv(f"SENTRY_RELEASE_{normalized}")
        if process_specific_release:
            return process_specific_release

    env_release = os.getenv("SENTRY_RELEASE")
    if env_release:
        return env_release

    for env_key in ("CI_COMMIT_SHA", "GITHUB_SHA", "GIT_COMMIT", "FLY_COMMIT_SHA"):
        value = os.getenv(env_key)
        if value:
            return f"ace-platform@{value}"

    return f"ace-platform@{_default_app_version()}"


def init_sentry_for_process(
    *,
    process_name: str,
    settings: Settings,
    integrations: list[Any] | None = None,
    traces_sample_rate: float | None = None,
    profiles_sample_rate: float | None = None,
    traces_sampler: Callable[[dict], float] | None = None,
    enable_tracing: bool = True,
    send_default_pii: bool = False,
) -> None:
    """Initialize Sentry for a process with normalized settings.

    Args:
        process_name: Human-readable surface name in startup logs.
        settings: Loaded configuration.
        integrations: Optional Sentry integrations.
        traces_sample_rate: Optional explicit traces sample override.
        profiles_sample_rate: Optional explicit profile sample override.
        traces_sampler: Optional traces sampler function.
        enable_tracing: Whether tracing is enabled.
        send_default_pii: Whether Sentry's default PII capture is enabled.

    Returns:
        None
    """
    if not settings.sentry_dsn:
        logger.debug("Sentry DSN not configured, error reporting disabled for %s", process_name)
        return

    release = resolve_sentry_release(settings, process_name=process_name)

    effective_traces_rate = settings.sentry_traces_sample_rate
    if traces_sample_rate is None:
        effective_traces_rate = _resolve_sample_rate_for_process(
            process_name,
            base_env_name="SENTRY_TRACES_SAMPLE_RATE",
            default=settings.sentry_traces_sample_rate,
        )
    else:
        effective_traces_rate = traces_sample_rate

    effective_profiles_rate = settings.sentry_profiles_sample_rate
    if profiles_sample_rate is None:
        effective_profiles_rate = _resolve_sample_rate_for_process(
            process_name,
            base_env_name="SENTRY_PROFILES_SAMPLE_RATE",
            default=settings.sentry_profiles_sample_rate,
        )
    else:
        effective_profiles_rate = profiles_sample_rate

    effective_traces_rate = _coerce_sample_rate(
        effective_traces_rate,
        f"SENTRY_TRACES_SAMPLE_RATE_{_normalize_process_name(process_name)}",
        default=settings.sentry_traces_sample_rate,
    )
    effective_profiles_rate = _coerce_sample_rate(
        effective_profiles_rate,
        f"SENTRY_PROFILES_SAMPLE_RATE_{_normalize_process_name(process_name)}",
        default=settings.sentry_profiles_sample_rate,
    )

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=release,
        integrations=integrations,
        traces_sample_rate=effective_traces_rate,
        profiles_sample_rate=effective_profiles_rate,
        traces_sampler=traces_sampler,
        enable_tracing=enable_tracing,
        send_default_pii=send_default_pii,
        max_breadcrumbs=50,
        max_request_body_size="small",
        transport_queue_size=max(1, settings.sentry_transport_queue_size),
        # Keep startup/surges predictable if transport health degrades.
        send_client_reports=False,
    )

    logger.info(
        "Sentry initialized",
        extra={
            "sentry_process": process_name,
            "sentry_environment": settings.environment,
            "sentry_release": release,
            "sentry_traces_sample_rate": effective_traces_rate,
            "sentry_profiles_sample_rate": effective_profiles_rate,
            "sentry_send_client_reports": False,
        },
    )


def get_effective_release_settings(
    settings: Settings | None = None,
    *,
    process_name: str | None = None,
) -> dict[str, Any]:
    """Return derived Sentry settings for debug, tests, and scripts."""

    local_settings = settings or get_settings()
    return {
        "environment": local_settings.environment,
        "release": resolve_sentry_release(local_settings, process_name=process_name),
        "traces_sample_rate": _resolve_sample_rate_for_process(
            process_name=process_name or "api",
            base_env_name="SENTRY_TRACES_SAMPLE_RATE",
            default=local_settings.sentry_traces_sample_rate,
        )
        if process_name
        else local_settings.sentry_traces_sample_rate,
        "profiles_sample_rate": _resolve_sample_rate_for_process(
            process_name=process_name or "api",
            base_env_name="SENTRY_PROFILES_SAMPLE_RATE",
            default=local_settings.sentry_profiles_sample_rate,
        )
        if process_name
        else local_settings.sentry_profiles_sample_rate,
    }
