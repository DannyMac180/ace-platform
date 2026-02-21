"""Tests for MCP server Sentry initialization."""

from unittest.mock import patch

from ace_platform.config import Settings


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


def test_mcp_run_server_initializes_sentry_with_process_context_stdio():
    """Verify run_server(stdio) initializes Sentry and starts stdio transport."""
    settings = _mcp_test_settings()
    with (
        patch("ace_platform.mcp.server.settings", settings),
        patch("ace_platform.mcp.server.init_sentry_for_process") as init_call,
        patch("ace_platform.mcp.server.mcp") as mock_mcp,
    ):
        from ace_platform.mcp.server import run_server

        run_server(transport="stdio")

        init_call.assert_called_once()
        assert init_call.call_args.kwargs["process_name"] == "mcp"

        called_settings = init_call.call_args.kwargs["settings"]
        assert called_settings.sentry_dsn == "https://example@sentry.io/1"
        assert called_settings.sentry_release == "test-release"

        mock_mcp.run.assert_called_once_with(transport="stdio")


def test_mcp_run_server_initializes_sentry_with_process_context_sse():
    """Verify run_server(sse) initializes Sentry and starts SSE transport."""
    settings = _mcp_test_settings()
    with (
        patch("ace_platform.mcp.server.settings", settings),
        patch("ace_platform.mcp.server.init_sentry_for_process") as init_call,
        patch("ace_platform.mcp.server.mcp") as mock_mcp,
    ):
        from ace_platform.mcp.server import run_server

        run_server(transport="sse")

        init_call.assert_called_once()
        mock_mcp.run.assert_called_once_with(transport="sse")


def test_mcp_run_server_initializes_sentry_with_process_context_http():
    """Verify run_server(http) initializes Sentry and starts ASGI HTTP app."""
    settings = _mcp_test_settings()
    sentinel_app = object()
    with (
        patch("ace_platform.mcp.server.settings", settings),
        patch("ace_platform.mcp.server.init_sentry_for_process") as init_call,
        patch(
            "ace_platform.mcp.server.create_mcp_asgi_app", return_value=sentinel_app
        ) as build_app,
        patch("uvicorn.run") as uvicorn_run,
        patch("ace_platform.mcp.server.mcp") as mock_mcp,
    ):
        from ace_platform.mcp.server import run_server

        run_server(transport="http")

        init_call.assert_called_once()
        build_app.assert_called_once_with(include_legacy_sse=True)
        uvicorn_run.assert_called_once_with(
            sentinel_app,
            host=settings.mcp_server_host,
            port=settings.mcp_server_port,
        )
        mock_mcp.run.assert_not_called()
