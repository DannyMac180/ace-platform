"""Tests for shared Sentry bootstrap helpers."""

import os
from unittest.mock import patch

import pytest

from ace_platform.config import Settings
from ace_platform.core import sentry_bootstrap


def make_settings(**overrides: str | int | float | bool) -> Settings:
    """Create a minimal settings object for bootstrap tests."""
    base: dict[str, str | int | float | bool] = {
        "database_url": "postgresql://postgres:postgres@localhost:5432/ace_platform",
        "database_url_async": "postgresql+asyncpg://postgres:postgres@localhost:5432/ace_platform",
        "redis_url": "redis://localhost:6379/0",
        "openai_api_key": "test-key",
        "sentry_dsn": "https://examplePublicKey@o0.ingest.sentry.io/0",
        "sentry_traces_sample_rate": 0.1,
        "sentry_profiles_sample_rate": 0.2,
        "session_secret_key": "test-session-secret",
        "environment": "development",
    }
    base.update(overrides)
    return Settings(**base)


def test_resolve_release_prefers_process_override():
    settings = make_settings(sentry_release="")
    with patch.dict(
        os.environ,
        {
            "SENTRY_RELEASE_API": "api-release",
            "SENTRY_RELEASE": "global-release",
        },
        clear=False,
    ):
        assert (
            sentry_bootstrap.resolve_sentry_release(settings, process_name="api") == "api-release"
        )


def test_process_release_override_beats_setting_value():
    settings = make_settings(sentry_release="setting-release")
    with patch.dict(os.environ, {"SENTRY_RELEASE_API": "api-release"}, clear=False):
        assert (
            sentry_bootstrap.resolve_sentry_release(settings, process_name="api") == "api-release"
        )


def test_resolve_release_prefers_settings_value():
    settings = make_settings(sentry_release="setting-release")
    assert (
        sentry_bootstrap.resolve_sentry_release(settings, process_name="api") == "setting-release"
    )


def test_resolve_release_falls_back_to_git_env():
    settings = make_settings(sentry_release="", environment="development")
    with patch.dict(os.environ, {"GITHUB_SHA": "abc123"}, clear=False):
        assert (
            sentry_bootstrap.resolve_sentry_release(settings, process_name="worker")
            == "ace-platform@abc123"
        )


def test_process_sample_rate_uses_specific_override():
    settings = make_settings(sentry_release="")
    with patch.dict(
        os.environ,
        {
            "SENTRY_TRACES_SAMPLE_RATE_API": "0.25",
            "SENTRY_TRACES_SAMPLE_RATE": "0.05",
        },
        clear=False,
    ):
        with patch("ace_platform.core.sentry_bootstrap.sentry_sdk.init") as sdk_init:
            sentry_bootstrap.init_sentry_for_process(process_name="api", settings=settings)
            assert sdk_init.call_count == 1
            kwargs = sdk_init.call_args.kwargs
            assert kwargs["traces_sample_rate"] == 0.25
            assert kwargs["profiles_sample_rate"] == 0.2


def test_effective_traces_sample_rate_uses_process_override():
    settings = make_settings(sentry_release="")
    with patch.dict(
        os.environ,
        {
            "SENTRY_TRACES_SAMPLE_RATE_API": "0.25",
            "SENTRY_TRACES_SAMPLE_RATE": "0.05",
        },
        clear=False,
    ):
        assert (
            sentry_bootstrap.get_effective_traces_sample_rate(settings, process_name="api") == 0.25
        )


def test_process_sample_rate_uses_explicit_argument():
    settings = make_settings(sentry_release="")
    with patch.dict(os.environ, {"SENTRY_TRACES_SAMPLE_RATE_API": "0.25"}, clear=False):
        with patch("ace_platform.core.sentry_bootstrap.sentry_sdk.init") as sdk_init:
            sentry_bootstrap.init_sentry_for_process(
                process_name="api",
                settings=settings,
                traces_sample_rate=0.9,
                profiles_sample_rate=0.9,
            )
            kwargs = sdk_init.call_args.kwargs
            assert kwargs["traces_sample_rate"] == 0.9
            assert kwargs["profiles_sample_rate"] == 0.9


def test_init_skips_when_dsn_missing():
    settings = make_settings(sentry_release="", sentry_dsn="")
    with patch("ace_platform.core.sentry_bootstrap.sentry_sdk.init") as sdk_init:
        sentry_bootstrap.init_sentry_for_process(process_name="api", settings=settings)
        sdk_init.assert_not_called()


def test_init_uses_fast_fail_transport():
    """Verify that init passes the custom fast-fail transport class."""
    settings = make_settings(sentry_release="")
    with patch("ace_platform.core.sentry_bootstrap.sentry_sdk.init") as sdk_init:
        sentry_bootstrap.init_sentry_for_process(process_name="api", settings=settings)
        kwargs = sdk_init.call_args.kwargs
        assert kwargs["transport"] is sentry_bootstrap._FastFailTransport
        assert kwargs["shutdown_timeout"] == 2


def test_fast_fail_transport_uses_short_timeouts():
    """Verify that _FastFailTransport configures aggressive timeouts."""
    import urllib3

    from ace_platform.core.sentry_bootstrap import _FastFailTransport

    transport = _FastFailTransport.__new__(_FastFailTransport)
    # Provide the minimal state that _get_pool_options needs from the parent.
    # HttpTransport.__init__ is complex, so we monkey-patch the super call.
    with patch.object(
        _FastFailTransport.__bases__[0],
        "_get_pool_options",
        return_value={
            "num_pools": 2,
            "cert_reqs": "CERT_REQUIRED",
            "timeout": urllib3.Timeout(total=30),
        },
    ):
        options = transport._get_pool_options()
        timeout = options["timeout"]
        assert timeout.connect_timeout == 2.0
        assert timeout.read_timeout == 3.0


def test_before_send_filter_drops_anyio_disconnect_errors():
    event = {"message": "test event"}
    if not sentry_bootstrap._SSE_DISCONNECT_EXCEPTION_TYPES:
        pytest.skip("anyio disconnect exception types unavailable")

    exc_type = sentry_bootstrap._SSE_DISCONNECT_EXCEPTION_TYPES[0]
    exc = exc_type()
    hint = {"exc_info": (exc_type, exc, None)}

    assert sentry_bootstrap._before_send_filter(event, hint) is None


def test_before_send_filter_keeps_same_named_non_anyio_exception():
    class ClosedResourceError(Exception):
        pass

    event = {"message": "test event"}
    exc = ClosedResourceError()
    hint = {"exc_info": (ClosedResourceError, exc, None)}

    assert sentry_bootstrap._before_send_filter(event, hint) == event
