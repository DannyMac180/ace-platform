"""Typed workflow configuration for Symphony."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ace_platform.symphony.errors import ConfigError
from ace_platform.symphony.models import WorkflowDefinition

DEFAULT_LINEAR_ENDPOINT = "https://api.linear.app/graphql"
DEFAULT_ACTIVE_STATES = ("Todo", "In Progress")
DEFAULT_TERMINAL_STATES = ("Closed", "Cancelled", "Canceled", "Duplicate", "Done")


def _as_string_list(value: Any, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if not isinstance(value, list):
        return default
    return tuple(str(item) for item in value if str(item).strip())


def _coerce_int(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _resolve_env_token(value: Any, *, path_like: bool = False) -> Any:
    if not isinstance(value, str):
        return value

    if value.startswith("$") and len(value) > 1:
        resolved = os.environ.get(value[1:], "")
        if not resolved:
            return None
        value = resolved

    if path_like and isinstance(value, str):
        expanded = os.path.expanduser(value)
        expanded = os.path.expandvars(expanded)
        return expanded

    return value


def _normalize_state_limits(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, int] = {}
    for state_name, raw_limit in value.items():
        limit = _coerce_int(raw_limit, 0)
        if limit > 0:
            normalized[str(state_name).strip().lower()] = limit
    return normalized


def _coerce_turn_sandbox_policy(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and value:
        return value
    return {"type": "workspaceWrite"}


@dataclass(slots=True, frozen=True)
class TrackerConfig:
    kind: str | None
    endpoint: str
    api_key: str | None
    project_slug: str | None
    active_states: tuple[str, ...]
    terminal_states: tuple[str, ...]

    @property
    def normalized_active_states(self) -> set[str]:
        return {state.strip().lower() for state in self.active_states}

    @property
    def normalized_terminal_states(self) -> set[str]:
        return {state.strip().lower() for state in self.terminal_states}


@dataclass(slots=True, frozen=True)
class PollingConfig:
    interval_ms: int = 30_000


@dataclass(slots=True, frozen=True)
class WorkspaceConfig:
    root: Path


@dataclass(slots=True, frozen=True)
class HookConfig:
    after_create: str | None = None
    before_run: str | None = None
    after_run: str | None = None
    before_remove: str | None = None
    timeout_ms: int = 60_000


@dataclass(slots=True, frozen=True)
class AgentConfig:
    max_concurrent_agents: int = 10
    max_turns: int = 20
    max_retry_backoff_ms: int = 300_000
    max_concurrent_agents_by_state: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class CodexConfig:
    command: str = "codex app-server"
    approval_policy: Any = "never"
    thread_sandbox: Any = "workspace-write"
    turn_sandbox_policy: dict[str, Any] = field(default_factory=lambda: {"type": "workspaceWrite"})
    turn_timeout_ms: int = 3_600_000
    read_timeout_ms: int = 5_000
    stall_timeout_ms: int = 300_000


@dataclass(slots=True, frozen=True)
class SymphonyConfig:
    tracker: TrackerConfig
    polling: PollingConfig
    workspace: WorkspaceConfig
    hooks: HookConfig
    agent: AgentConfig
    codex: CodexConfig
    workflow_path: Path


def config_from_workflow(workflow: WorkflowDefinition, workflow_path: Path) -> SymphonyConfig:
    """Build typed runtime config from a workflow definition."""

    root = workflow.config
    tracker = root.get("tracker") if isinstance(root.get("tracker"), dict) else {}
    polling = root.get("polling") if isinstance(root.get("polling"), dict) else {}
    workspace = root.get("workspace") if isinstance(root.get("workspace"), dict) else {}
    hooks = root.get("hooks") if isinstance(root.get("hooks"), dict) else {}
    agent = root.get("agent") if isinstance(root.get("agent"), dict) else {}
    codex = root.get("codex") if isinstance(root.get("codex"), dict) else {}

    tracker_kind = str(tracker.get("kind")).strip() if tracker.get("kind") else None
    tracker_api_key = _resolve_env_token(tracker.get("api_key")) or os.environ.get(
        "LINEAR_API_KEY", ""
    )
    tracker_api_key = tracker_api_key or None
    workspace_root = _resolve_env_token(workspace.get("root"), path_like=True)
    if workspace_root is None:
        workspace_root = str(Path(tempfile.gettempdir()) / "symphony_workspaces")

    hook_timeout_ms = _coerce_int(hooks.get("timeout_ms"), 60_000)
    if hook_timeout_ms <= 0:
        hook_timeout_ms = 60_000

    return SymphonyConfig(
        tracker=TrackerConfig(
            kind=tracker_kind,
            endpoint=str(tracker.get("endpoint") or DEFAULT_LINEAR_ENDPOINT),
            api_key=str(tracker_api_key) if tracker_api_key else None,
            project_slug=str(tracker.get("project_slug")).strip()
            if tracker.get("project_slug")
            else None,
            active_states=_as_string_list(tracker.get("active_states"), DEFAULT_ACTIVE_STATES),
            terminal_states=_as_string_list(
                tracker.get("terminal_states"),
                DEFAULT_TERMINAL_STATES,
            ),
        ),
        polling=PollingConfig(interval_ms=max(_coerce_int(polling.get("interval_ms"), 30_000), 1)),
        workspace=WorkspaceConfig(root=Path(str(workspace_root))),
        hooks=HookConfig(
            after_create=str(hooks.get("after_create")) if hooks.get("after_create") else None,
            before_run=str(hooks.get("before_run")) if hooks.get("before_run") else None,
            after_run=str(hooks.get("after_run")) if hooks.get("after_run") else None,
            before_remove=str(hooks.get("before_remove")) if hooks.get("before_remove") else None,
            timeout_ms=hook_timeout_ms,
        ),
        agent=AgentConfig(
            max_concurrent_agents=max(_coerce_int(agent.get("max_concurrent_agents"), 10), 1),
            max_turns=max(_coerce_int(agent.get("max_turns"), 20), 1),
            max_retry_backoff_ms=max(_coerce_int(agent.get("max_retry_backoff_ms"), 300_000), 1),
            max_concurrent_agents_by_state=_normalize_state_limits(
                agent.get("max_concurrent_agents_by_state")
            ),
        ),
        codex=CodexConfig(
            command=str(codex.get("command") or "codex app-server").strip(),
            approval_policy=codex.get("approval_policy", "never"),
            thread_sandbox=codex.get("thread_sandbox", "workspace-write"),
            turn_sandbox_policy=_coerce_turn_sandbox_policy(codex.get("turn_sandbox_policy")),
            turn_timeout_ms=max(_coerce_int(codex.get("turn_timeout_ms"), 3_600_000), 1),
            read_timeout_ms=max(_coerce_int(codex.get("read_timeout_ms"), 5_000), 1),
            stall_timeout_ms=_coerce_int(codex.get("stall_timeout_ms"), 300_000),
        ),
        workflow_path=workflow_path,
    )


def validate_dispatch_config(config: SymphonyConfig) -> None:
    """Validate the minimum config required to poll and dispatch work."""

    if not config.tracker.kind:
        raise ConfigError("unsupported_tracker_kind", "tracker.kind is required")
    if config.tracker.kind != "linear":
        raise ConfigError(
            "unsupported_tracker_kind",
            f"Unsupported tracker.kind: {config.tracker.kind}",
        )
    if not config.tracker.api_key:
        raise ConfigError("missing_tracker_api_key", "tracker.api_key is required")
    if not config.tracker.project_slug:
        raise ConfigError("missing_tracker_project_slug", "tracker.project_slug is required")
    if not config.codex.command:
        raise ConfigError("missing_codex_command", "codex.command must be non-empty")
