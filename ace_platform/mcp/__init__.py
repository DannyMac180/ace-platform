"""ACE Platform MCP Server.

This package provides the Model Context Protocol (MCP) server for ACE Platform,
enabling LLM clients like Claude to interact with playbooks and record outcomes.

Usage:
    # Run with stdio transport (for Claude Desktop)
    python -m ace_platform.mcp.server

    # Run with Streamable HTTP + legacy SSE compatibility
    python -m ace_platform.mcp.server http
"""

from ace_platform.mcp.auth import (
    MCPAuthErrorCode,
    MCPAuthResult,
    authenticate_mcp_request,
    require_playbook_access,
)
from ace_platform.mcp.tools import DEFAULT_SCOPES, MCPScope, validate_scopes


def __getattr__(name: str):
    """Lazy import for server module to avoid circular import when running as __main__."""
    if name in ("mcp", "run_server"):
        from ace_platform.mcp import server

        return getattr(server, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "mcp",
    "run_server",
    "MCPScope",
    "DEFAULT_SCOPES",
    "validate_scopes",
    "MCPAuthResult",
    "MCPAuthErrorCode",
    "authenticate_mcp_request",
    "require_playbook_access",
]
