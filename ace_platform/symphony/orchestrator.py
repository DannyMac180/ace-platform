"""Long-running Symphony orchestrator."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ace_platform.symphony.codex import CodexAppServerSession
from ace_platform.symphony.config import (
    SymphonyConfig,
    config_from_workflow,
    validate_dispatch_config,
)
from ace_platform.symphony.errors import AgentRunnerError, ConfigError, SymphonyError, TrackerError
from ace_platform.symphony.models import (
    AgentEvent,
    CodexTotals,
    Issue,
    RetryEntry,
    RunningEntry,
    RuntimeState,
    WorkflowDefinition,
    utc_now,
)
from ace_platform.symphony.tracker import LinearTrackerClient
from ace_platform.symphony.workflow import build_turn_prompt, load_workflow_definition
from ace_platform.symphony.workspace import WorkspaceManager

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class WorkflowState:
    """Current effective workflow definition and config."""

    definition: WorkflowDefinition
    config: SymphonyConfig
    mtime_ns: int


class SymphonyOrchestrator:
    """Single-authority poller/runner for Symphony issues."""

    def __init__(self, workflow_path: Path) -> None:
        self._workflow_path = workflow_path
        self._workflow_state: WorkflowState | None = None
        self._state: RuntimeState | None = None
        self._tracker: LinearTrackerClient | None = None
        self._workspace_manager: WorkspaceManager | None = None
        self._stop_event = asyncio.Event()
        self._refresh_event = asyncio.Event()
        self._watch_task: asyncio.Task[None] | None = None

    @property
    def config(self) -> SymphonyConfig:
        if self._workflow_state is None:
            raise RuntimeError("Workflow has not been loaded")
        return self._workflow_state.config

    @property
    def workflow_definition(self) -> WorkflowDefinition:
        if self._workflow_state is None:
            raise RuntimeError("Workflow has not been loaded")
        return self._workflow_state.definition

    @property
    def state(self) -> RuntimeState:
        if self._state is None:
            raise RuntimeError("Orchestrator has not started")
        return self._state

    async def run(self) -> None:
        """Start the orchestrator and run until stopped."""

        await self._reload_workflow(force=True, fail_on_error=True)
        self._state = RuntimeState(
            poll_interval_ms=self.config.polling.interval_ms,
            max_concurrent_agents=self.config.agent.max_concurrent_agents,
        )
        await self._startup_terminal_workspace_cleanup()
        self._watch_task = asyncio.create_task(self._watch_workflow())

        try:
            while not self._stop_event.is_set():
                await self.tick()
                await self._wait_for_next_tick()
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the orchestrator and cancel in-flight work."""

        self._stop_event.set()
        if self._watch_task is not None:
            self._watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watch_task

        if self._state is None:
            return

        for retry in list(self.state.retry_attempts.values()):
            if retry.timer_handle:
                retry.timer_handle.cancel()
        self.state.retry_attempts.clear()

        running_entries = list(self.state.running.items())
        for issue_id, entry in running_entries:
            entry.cancel_reason = "shutdown"
            entry.task.cancel()

        if running_entries:
            await asyncio.gather(
                *(entry.task for _, entry in running_entries), return_exceptions=True
            )

        self.state.running.clear()
        self.state.claimed.clear()

    async def tick(self) -> None:
        """Run one reconcile + dispatch cycle."""

        await self._reconcile_running_issues()

        try:
            await self._reload_workflow(force=False, fail_on_error=False)
            validate_dispatch_config(self.config)
        except (ConfigError, SymphonyError) as exc:
            logger.error("dispatch_validation_failed error=%s", exc)
            return

        try:
            issues = await self._tracker.fetch_candidate_issues()
        except TrackerError as exc:
            logger.error("tracker_fetch_failed error=%s", exc)
            return

        for issue in self._sort_issues(issues):
            if self._available_global_slots() <= 0:
                break
            if self._should_dispatch(issue):
                self._dispatch_issue(issue, attempt=None)

    def snapshot(self) -> dict[str, Any]:
        """Return a synchronous runtime snapshot suitable for monitoring."""

        now = utc_now()
        running = []
        for issue_id, entry in self.state.running.items():
            running.append(
                {
                    "issue_id": issue_id,
                    "issue_identifier": entry.issue.identifier,
                    "state": entry.issue.state,
                    "session_id": entry.session_id,
                    "turn_count": entry.turn_count,
                    "last_event": entry.last_codex_event,
                    "last_message": entry.last_codex_message,
                    "started_at": entry.started_at.isoformat(),
                    "last_event_at": entry.last_codex_timestamp.isoformat()
                    if entry.last_codex_timestamp
                    else None,
                    "tokens": {
                        "input_tokens": entry.codex_input_tokens,
                        "output_tokens": entry.codex_output_tokens,
                        "total_tokens": entry.codex_total_tokens,
                    },
                }
            )
        retrying = [
            {
                "issue_id": retry.issue_id,
                "issue_identifier": retry.identifier,
                "attempt": retry.attempt,
                "due_at": _from_due_at_ms(retry.due_at_ms).isoformat(),
                "error": retry.error,
            }
            for retry in self.state.retry_attempts.values()
        ]
        totals = CodexTotals(
            input_tokens=self.state.codex_totals.input_tokens,
            output_tokens=self.state.codex_totals.output_tokens,
            total_tokens=self.state.codex_totals.total_tokens,
            seconds_running=self.state.codex_totals.seconds_running
            + sum(
                (now - entry.started_at).total_seconds() for entry in self.state.running.values()
            ),
        )
        return {
            "generated_at": now.isoformat(),
            "counts": {"running": len(running), "retrying": len(retrying)},
            "running": running,
            "retrying": retrying,
            "codex_totals": {
                "input_tokens": totals.input_tokens,
                "output_tokens": totals.output_tokens,
                "total_tokens": totals.total_tokens,
                "seconds_running": totals.seconds_running,
            },
            "rate_limits": self.state.codex_rate_limits,
        }

    def request_refresh(self) -> None:
        """Trigger an immediate best-effort poll + reconcile cycle."""

        self._refresh_event.set()

    async def _wait_for_next_tick(self) -> None:
        timeout = self.state.poll_interval_ms / 1000
        try:
            await asyncio.wait_for(self._refresh_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return
        finally:
            self._refresh_event.clear()

    async def _watch_workflow(self) -> None:
        while not self._stop_event.is_set():
            await asyncio.sleep(1)
            await self._reload_workflow(force=False, fail_on_error=False)

    async def _reload_workflow(self, *, force: bool, fail_on_error: bool) -> None:
        try:
            mtime_ns = self._workflow_path.stat().st_mtime_ns
        except FileNotFoundError as exc:
            if fail_on_error:
                raise
            logger.error("workflow_reload_failed error=%s", exc)
            return

        if (
            not force
            and self._workflow_state is not None
            and mtime_ns == self._workflow_state.mtime_ns
        ):
            return

        try:
            definition = load_workflow_definition(self._workflow_path)
            config = config_from_workflow(definition, self._workflow_path)
            validate_dispatch_config(config)
        except Exception as exc:
            if fail_on_error:
                raise
            logger.error("workflow_reload_failed error=%s", exc)
            return

        self._workflow_state = WorkflowState(
            definition=definition, config=config, mtime_ns=mtime_ns
        )
        self._tracker = LinearTrackerClient(config.tracker)
        self._workspace_manager = WorkspaceManager(config.workspace, config.hooks)
        if self._state is not None:
            self._state.poll_interval_ms = config.polling.interval_ms
            self._state.max_concurrent_agents = config.agent.max_concurrent_agents
        logger.info("workflow_reloaded path=%s", self._workflow_path)
        self.request_refresh()

    async def _startup_terminal_workspace_cleanup(self) -> None:
        try:
            terminal_issues = await self._tracker.fetch_issues_by_states(
                self.config.tracker.terminal_states
            )
        except TrackerError as exc:
            logger.warning("startup_cleanup_failed error=%s", exc)
            return
        for issue in terminal_issues:
            await self._workspace_manager.remove_for_issue(issue.identifier)

    async def _reconcile_running_issues(self) -> None:
        await self._reconcile_stalled_runs()
        if not self.state.running:
            return
        try:
            refreshed = await self._tracker.fetch_issue_states_by_ids(list(self.state.running))
        except TrackerError as exc:
            logger.warning("running_state_refresh_failed error=%s", exc)
            return

        refreshed_by_id = {issue.id: issue for issue in refreshed}
        for issue_id, entry in list(self.state.running.items()):
            latest = refreshed_by_id.get(issue_id)
            if latest is None:
                continue
            normalized_state = latest.normalized_state()
            if normalized_state in self.config.tracker.normalized_terminal_states:
                await self._terminate_running_issue(
                    issue_id, cleanup_workspace=True, reason="terminal"
                )
            elif normalized_state in self.config.tracker.normalized_active_states:
                entry.issue = latest
            else:
                await self._terminate_running_issue(
                    issue_id, cleanup_workspace=False, reason="non_active"
                )

    async def _reconcile_stalled_runs(self) -> None:
        stall_timeout_ms = self.config.codex.stall_timeout_ms
        if stall_timeout_ms <= 0:
            return
        now = utc_now()
        for issue_id, entry in list(self.state.running.items()):
            reference = entry.last_codex_timestamp or entry.started_at
            elapsed_ms = (now - reference).total_seconds() * 1000
            if elapsed_ms > stall_timeout_ms:
                await self._terminate_running_issue(
                    issue_id, cleanup_workspace=False, reason="stalled"
                )

    async def _terminate_running_issue(
        self,
        issue_id: str,
        *,
        cleanup_workspace: bool,
        reason: str,
    ) -> None:
        entry = self.state.running.get(issue_id)
        if entry is None:
            return
        entry.cancel_reason = reason
        entry.task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await entry.task
        if cleanup_workspace:
            await self._workspace_manager.remove_for_issue(entry.issue.identifier)

    def _dispatch_issue(self, issue: Issue, *, attempt: int | None) -> None:
        if issue.id in self.state.running or issue.id in self.state.claimed:
            return
        task = asyncio.create_task(self._run_issue_attempt(issue, attempt))
        entry = RunningEntry(
            issue=issue,
            workspace_path=self._workspace_manager.workspace_path_for_identifier(issue.identifier),
            started_at=utc_now(),
            task=task,
            retry_attempt=attempt,
        )
        self.state.running[issue.id] = entry
        self.state.claimed.add(issue.id)
        retry_entry = self.state.retry_attempts.pop(issue.id, None)
        if retry_entry and retry_entry.timer_handle:
            retry_entry.timer_handle.cancel()
        task.add_done_callback(
            lambda completed_task, issue_id=issue.id: asyncio.create_task(
                self._handle_worker_exit(issue_id, completed_task)
            )
        )
        logger.info(
            "issue_dispatched issue_id=%s issue_identifier=%s attempt=%s",
            issue.id,
            issue.identifier,
            attempt,
        )

    async def _run_issue_attempt(self, issue: Issue, attempt: int | None) -> None:
        workspace = await self._workspace_manager.create_for_issue(issue.identifier)
        session: CodexAppServerSession | None = None
        try:
            await self._workspace_manager.prepare_for_run(workspace)
            session = CodexAppServerSession(
                self.config.codex,
                workspace.path,
                tool_handler=self._handle_dynamic_tool_call,
                event_callback=lambda event: self._handle_agent_event(issue.id, event),
            )
            await session.start()

            current_issue = issue
            turn_number = 1
            while True:
                prompt = build_turn_prompt(
                    self.workflow_definition,
                    current_issue,
                    attempt,
                    turn_number,
                    self.config.agent.max_turns,
                )
                result = await session.run_turn(
                    prompt,
                    title=f"{current_issue.identifier}: {current_issue.title}",
                )
                if not result.success:
                    raise AgentRunnerError(result.status, result.error or result.status)

                refreshed = await self._tracker.fetch_issue_states_by_ids([current_issue.id])
                if refreshed:
                    current_issue = refreshed[0]

                if (
                    current_issue.normalized_state()
                    not in self.config.tracker.normalized_active_states
                ):
                    break
                if turn_number >= self.config.agent.max_turns:
                    break
                turn_number += 1
        finally:
            if session is not None:
                await session.stop()
            await self._workspace_manager.after_run(workspace)

    async def _handle_worker_exit(self, issue_id: str, task: asyncio.Task[None]) -> None:
        entry = self.state.running.pop(issue_id, None)
        if entry is None:
            return
        self._add_runtime_seconds(entry)

        if task.cancelled():
            reason = entry.cancel_reason or "cancelled"
            logger.info(
                "issue_cancelled issue_id=%s issue_identifier=%s reason=%s",
                issue_id,
                entry.issue.identifier,
                reason,
            )
            if reason in {"terminal", "non_active", "shutdown"}:
                self.state.claimed.discard(issue_id)
                self.state.retry_attempts.pop(issue_id, None)
                return
            if reason == "stalled":
                self._schedule_retry(
                    issue_id,
                    self._next_retry_attempt(entry.retry_attempt),
                    identifier=entry.issue.identifier,
                    error="stalled session",
                )
                return

        exc = task.exception()
        if exc is None:
            self.state.completed.add(issue_id)
            self._schedule_retry(issue_id, 1, identifier=entry.issue.identifier, continuation=True)
            return

        self._schedule_retry(
            issue_id,
            self._next_retry_attempt(entry.retry_attempt),
            identifier=entry.issue.identifier,
            error=str(exc),
        )

    async def _handle_retry(self, issue_id: str) -> None:
        retry_entry = self.state.retry_attempts.get(issue_id)
        if retry_entry is None:
            return
        try:
            issues = await self._tracker.fetch_candidate_issues()
        except TrackerError as exc:
            self._schedule_retry(
                issue_id,
                retry_entry.attempt,
                identifier=retry_entry.identifier,
                error=str(exc),
            )
            return

        issue = next((candidate for candidate in issues if candidate.id == issue_id), None)
        if issue is None:
            self._release_issue(issue_id)
            return
        if self._available_global_slots() <= 0 or not self._has_state_slot(issue):
            self._schedule_retry(
                issue_id,
                retry_entry.attempt,
                identifier=retry_entry.identifier,
                error="no available orchestrator slots",
            )
            return
        if not self._should_dispatch(issue, allow_claimed_issue_id=issue_id):
            self._release_issue(issue_id)
            return
        self._dispatch_issue(issue, attempt=retry_entry.attempt)

    async def _handle_dynamic_tool_call(self, tool_name: str, arguments: Any) -> dict[str, Any]:
        if tool_name != "linear_graphql":
            return _tool_payload(False, {"error": "unsupported_tool_call", "tool": tool_name})
        try:
            if isinstance(arguments, str):
                query = arguments
                variables = None
            elif isinstance(arguments, dict):
                query = arguments.get("query", "")
                variables = arguments.get("variables")
            else:
                return _tool_payload(False, {"error": "invalid_tool_arguments"})
            data = await self._tracker.execute_raw_graphql(query, variables)
            return _tool_payload(True, data)
        except TrackerError as exc:
            return _tool_payload(False, {"error": exc.code, "message": str(exc)})

    def _handle_agent_event(self, issue_id: str, event: AgentEvent) -> None:
        entry = self.state.running.get(issue_id)
        if entry is None:
            return

        entry.session_id = event.session_id or entry.session_id
        entry.thread_id = event.thread_id or entry.thread_id
        entry.turn_id = event.turn_id or entry.turn_id
        entry.codex_app_server_pid = event.codex_app_server_pid or entry.codex_app_server_pid
        entry.last_codex_event = event.event
        entry.last_codex_timestamp = event.timestamp
        entry.last_codex_message = event.message

        if event.event == "session_started":
            entry.turn_count += 1

        if event.usage:
            input_total = max(event.usage.get("input_tokens", 0), 0)
            output_total = max(event.usage.get("output_tokens", 0), 0)
            total_total = max(event.usage.get("total_tokens", 0), 0)

            self.state.codex_totals.input_tokens += max(
                input_total - entry.last_reported_input_tokens, 0
            )
            self.state.codex_totals.output_tokens += max(
                output_total - entry.last_reported_output_tokens, 0
            )
            self.state.codex_totals.total_tokens += max(
                total_total - entry.last_reported_total_tokens, 0
            )

            entry.codex_input_tokens = input_total
            entry.codex_output_tokens = output_total
            entry.codex_total_tokens = total_total
            entry.last_reported_input_tokens = input_total
            entry.last_reported_output_tokens = output_total
            entry.last_reported_total_tokens = total_total

        if event.rate_limits is not None:
            self.state.codex_rate_limits = event.rate_limits

    def _sort_issues(self, issues: list[Issue]) -> list[Issue]:
        def sort_key(issue: Issue) -> tuple[Any, Any, str]:
            priority = issue.priority if issue.priority is not None else 999
            created_at = issue.created_at or datetime.max.replace(tzinfo=timezone.utc)
            return (priority, created_at, issue.identifier)

        return sorted(issues, key=sort_key)

    def _should_dispatch(self, issue: Issue, allow_claimed_issue_id: str | None = None) -> bool:
        normalized_state = issue.normalized_state()
        if normalized_state not in self.config.tracker.normalized_active_states:
            return False
        if normalized_state in self.config.tracker.normalized_terminal_states:
            return False
        if issue.id in self.state.running:
            return False
        if issue.id in self.state.claimed and issue.id != allow_claimed_issue_id:
            return False
        if self._available_global_slots() <= 0:
            return False
        if not self._has_state_slot(issue):
            return False
        if normalized_state == "todo":
            for blocker in issue.blocked_by:
                blocker_state = blocker.normalized_state()
                if (
                    blocker_state
                    and blocker_state not in self.config.tracker.normalized_terminal_states
                ):
                    return False
        return True

    def _available_global_slots(self) -> int:
        return max(self.config.agent.max_concurrent_agents - len(self.state.running), 0)

    def _has_state_slot(self, issue: Issue) -> bool:
        normalized_state = issue.normalized_state()
        limit = self.config.agent.max_concurrent_agents_by_state.get(
            normalized_state,
            self.config.agent.max_concurrent_agents,
        )
        running_count = sum(
            1
            for entry in self.state.running.values()
            if entry.issue.normalized_state() == normalized_state
        )
        return running_count < limit

    def _schedule_retry(
        self,
        issue_id: str,
        attempt: int,
        *,
        identifier: str,
        error: str | None = None,
        continuation: bool = False,
    ) -> None:
        existing = self.state.retry_attempts.pop(issue_id, None)
        if existing and existing.timer_handle:
            existing.timer_handle.cancel()

        delay_ms = (
            1_000
            if continuation
            else min(
                10_000 * (2 ** max(attempt - 1, 0)),
                self.config.agent.max_retry_backoff_ms,
            )
        )
        due_at_ms = int(time.monotonic() * 1000) + delay_ms
        handle = asyncio.get_running_loop().call_later(
            delay_ms / 1000,
            lambda: asyncio.create_task(self._handle_retry(issue_id)),
        )
        self.state.retry_attempts[issue_id] = RetryEntry(
            issue_id=issue_id,
            identifier=identifier,
            attempt=attempt,
            due_at_ms=due_at_ms,
            timer_handle=handle,
            error=error,
        )
        self.state.claimed.add(issue_id)
        logger.info(
            "issue_retry_scheduled issue_id=%s issue_identifier=%s attempt=%s delay_ms=%s error=%s",
            issue_id,
            identifier,
            attempt,
            delay_ms,
            error,
        )

    def _release_issue(self, issue_id: str) -> None:
        retry_entry = self.state.retry_attempts.pop(issue_id, None)
        if retry_entry and retry_entry.timer_handle:
            retry_entry.timer_handle.cancel()
        self.state.claimed.discard(issue_id)

    @staticmethod
    def _next_retry_attempt(previous_attempt: int | None) -> int:
        return 1 if previous_attempt is None else previous_attempt + 1

    def _add_runtime_seconds(self, entry: RunningEntry) -> None:
        self.state.codex_totals.seconds_running += max(
            (utc_now() - entry.started_at).total_seconds(), 0.0
        )


def _tool_payload(success: bool, body: Any) -> dict[str, Any]:
    import json

    return {
        "success": success,
        "contentItems": [{"type": "inputText", "text": json.dumps(body, sort_keys=True)}],
    }


def _from_due_at_ms(due_at_ms: int):
    seconds = due_at_ms / 1000
    delta = seconds - time.monotonic()
    return utc_now() if delta <= 0 else utc_now() + timedelta(seconds=delta)
