"""Tests for MCP server Sentry initialization."""

import importlib
from unittest.mock import patch

from ace_platform.config import Settings, get_settings


def _mcp_test_settings() -> Settings:
    return Settings(
        database_url="postgresql://postgres:postgres@localhost:5432/ace_platform",
        database_url_async="postgresql+asyncpg://postgres:postgres@localhost:5432/ace_platform",
        redis_url="redis://localhost:6379/0",
        openai_api_key="test-key",
        sentry_dsn="https://example@sentry.io/1",
        sentry_release="test-release",
        environment="development",
        session_secret_key="test-session-secret",
    )


def test_mcp_server_initializes_sentry_with_process_context():
    settings = _mcp_test_settings()
    with patch("ace_platform.config.get_settings", return_value=settings):
        with patch("ace_platform.core.sentry_bootstrap.init_sentry_for_process") as init_call:
            get_settings.cache_clear()
            module = importlib.reload(importlib.import_module("ace_platform.mcp.server"))

            init_call.assert_called_once()
            assert init_call.call_args.kwargs["process_name"] == "mcp"

            called_settings = init_call.call_args.kwargs["settings"]
            assert called_settings.sentry_dsn == "https://example@sentry.io/1"
            assert called_settings.sentry_release == "test-release"
            assert module is not None
