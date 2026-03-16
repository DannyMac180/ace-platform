"""Shared dataclasses for the Symphony runtime."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(timezone.utc)


@dataclass(slots=True, frozen=True)
class BlockerRef:
    """Normalized blocker reference."""

    id: str | None = None
    identifier: str | None = None
    state: str | None = None

    def normalized_state(self) -> str | None:
        if self.state is None:
            return None
        return self.state.strip().lower()

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "identifier": self.identifier, "state": self.state}


@dataclass(slots=True, frozen=True)
class Issue:
    """Normalized issue record used by the orchestrator."""

    id: str
    identifier: str
    title: str
    state: str
    description: str | None = None
    priority: int | None = None
    branch_name: str | None = None
    url: str | None = None
    labels: tuple[str, ...] = ()
    blocked_by: tuple[BlockerRef, ...] = ()
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def normalized_state(self) -> str:
        return self.state.strip().lower()

    def to_template_context(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "identifier": self.identifier,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "state": self.state,
            "branch_name": self.branch_name,
            "url": self.url,
            "labels": list(self.labels),
            "blocked_by": [blocker.to_dict() for blocker in self.blocked_by],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass(slots=True, frozen=True)
class WorkflowDefinition:
    """Loaded workflow file contents."""

    config: dict[str, Any]
    prompt_template: str


@dataclass(slots=True, frozen=True)
class Workspace:
    """Resolved workspace directory for an issue."""

    path: Path
    workspace_key: str
    created_now: bool


@dataclass(slots=True)
class AgentEvent:
    """Structured event emitted by the Codex runner."""

    event: str
    timestamp: datetime
    message: str | None = None
    session_id: str | None = None
    thread_id: str | None = None
    turn_id: str | None = None
    codex_app_server_pid: int | None = None
    usage: dict[str, int] | None = None
    rate_limits: Any = None
    payload: Any = None


@dataclass(slots=True)
class AgentRunResult:
    """Final result for one Codex turn."""

    success: bool
    status: str
    error: str | None = None
    session_id: str | None = None
    thread_id: str | None = None
    turn_id: str | None = None


@dataclass(slots=True)
class CodexTotals:
    """Aggregate token/runtime accounting."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    seconds_running: float = 0.0


@dataclass(slots=True)
class RetryEntry:
    """Retry state tracked by the orchestrator."""

    issue_id: str
    identifier: str
    attempt: int
    due_at_ms: int
    timer_handle: asyncio.TimerHandle | None = None
    error: str | None = None


@dataclass(slots=True)
class RunningEntry:
    """Live runtime state for one running issue."""

    issue: Issue
    workspace_path: Path
    started_at: datetime
    task: asyncio.Task[Any]
    retry_attempt: int | None = None
    session_id: str | None = None
    thread_id: str | None = None
    turn_id: str | None = None
    codex_app_server_pid: int | None = None
    last_codex_event: str | None = None
    last_codex_timestamp: datetime | None = None
    last_codex_message: str | None = None
    codex_input_tokens: int = 0
    codex_output_tokens: int = 0
    codex_total_tokens: int = 0
    last_reported_input_tokens: int = 0
    last_reported_output_tokens: int = 0
    last_reported_total_tokens: int = 0
    turn_count: int = 0
    cancel_reason: str | None = None
    last_error: str | None = None


@dataclass(slots=True)
class RuntimeState:
    """Single-authority mutable orchestrator state."""

    poll_interval_ms: int
    max_concurrent_agents: int
    running: dict[str, RunningEntry] = field(default_factory=dict)
    claimed: set[str] = field(default_factory=set)
    retry_attempts: dict[str, RetryEntry] = field(default_factory=dict)
    completed: set[str] = field(default_factory=set)
    codex_totals: CodexTotals = field(default_factory=CodexTotals)
    codex_rate_limits: Any = None


StatusCallback = Callable[[AgentEvent], None]
