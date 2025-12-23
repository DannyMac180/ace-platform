"""ACE Platform MCP Server.

This package provides the Model Context Protocol (MCP) server for ACE Platform,
enabling LLM clients like Claude to interact with playbooks and record outcomes.

Usage:
    # Run with stdio transport (for Claude Desktop)
    python -m ace_platform.mcp.server

    # Run with SSE transport (for web clients)
    python -m ace_platform.mcp.server sse
"""

from ace_platform.mcp.server import mcp, run_server
from ace_platform.mcp.tools import DEFAULT_SCOPES, MCPScope, validate_scopes

__all__ = [
    "mcp",
    "run_server",
    "MCPScope",
    "DEFAULT_SCOPES",
    "validate_scopes",
]
