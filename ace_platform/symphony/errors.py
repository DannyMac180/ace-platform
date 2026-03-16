"""Error types used by the Symphony runtime."""

from __future__ import annotations


class SymphonyError(Exception):
    """Base Symphony exception with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class WorkflowError(SymphonyError):
    """Raised when a workflow file cannot be loaded or rendered."""


class ConfigError(SymphonyError):
    """Raised when effective workflow configuration is invalid."""


class TrackerError(SymphonyError):
    """Raised when the issue tracker client cannot fulfill a request."""


class WorkspaceError(SymphonyError):
    """Raised when workspace setup or cleanup fails."""


class HookError(WorkspaceError):
    """Raised when a required hook fails."""


class AgentRunnerError(SymphonyError):
    """Raised when the Codex app-server runner fails."""
