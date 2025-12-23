"""MCP Tool utilities and scope definitions.

This module defines the available scopes for API keys and utility
functions for MCP tools.
"""

from enum import Enum


class MCPScope(str, Enum):
    """Available scopes for MCP API keys.

    Scopes control what operations an API key can perform.
    Use wildcard suffix (e.g., 'playbooks:*') to grant all permissions
    for a category.
    """

    # Playbook scopes
    PLAYBOOKS_READ = "playbooks:read"
    PLAYBOOKS_WRITE = "playbooks:write"

    # Outcome scopes
    OUTCOMES_READ = "outcomes:read"
    OUTCOMES_WRITE = "outcomes:write"

    # Evolution scopes
    EVOLUTION_READ = "evolution:read"
    EVOLUTION_WRITE = "evolution:write"

    # Wildcard (all permissions)
    ALL = "*"


# Mapping of scope to description for documentation
SCOPE_DESCRIPTIONS = {
    MCPScope.PLAYBOOKS_READ: "Read playbook content and metadata",
    MCPScope.PLAYBOOKS_WRITE: "Create and update playbooks",
    MCPScope.OUTCOMES_READ: "Read task outcomes",
    MCPScope.OUTCOMES_WRITE: "Record task outcomes",
    MCPScope.EVOLUTION_READ: "Read evolution job status",
    MCPScope.EVOLUTION_WRITE: "Trigger playbook evolution",
    MCPScope.ALL: "Full access to all operations",
}


# Default scopes for new API keys
DEFAULT_SCOPES = [
    MCPScope.PLAYBOOKS_READ.value,
    MCPScope.OUTCOMES_WRITE.value,
]


def validate_scopes(scopes: list[str]) -> list[str]:
    """Validate and normalize scope strings.

    Args:
        scopes: List of scope strings to validate.

    Returns:
        Normalized list of valid scopes.

    Raises:
        ValueError: If any scope is invalid.
    """
    valid_scope_values = {s.value for s in MCPScope}
    normalized = []

    for scope in scopes:
        scope = scope.strip().lower()

        # Check for wildcard patterns
        if scope == "*" or scope in valid_scope_values:
            normalized.append(scope)
        elif scope.endswith(":*"):
            # Validate prefix (e.g., "playbooks:*")
            prefix = scope[:-2]
            if any(s.value.startswith(f"{prefix}:") for s in MCPScope):
                normalized.append(scope)
            else:
                raise ValueError(f"Invalid scope prefix: {prefix}")
        else:
            raise ValueError(f"Invalid scope: {scope}")

    return normalized
