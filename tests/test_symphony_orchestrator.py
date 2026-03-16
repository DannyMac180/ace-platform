from __future__ import annotations

import asyncio
import time
from datetime import timedelta
from pathlib import Path

import pytest
import pytest_asyncio

from ace_platform.symphony.models import (
    AgentEvent,
    BlockerRef,
    Issue,
    RunningEntry,
    RuntimeState,
    utc_now,
)
from ace_platform.symphony.orchestrator import SymphonyOrchestrator


class _DummyWorkspaceManager:
    def __init__(self):
        self.removed = []

    def workspace_path_for_identifier(self, identifier: str) -> Path:
        return Path("/tmp") / identifier

    async def remove_for_issue(self, identifier: str) -> None:
        self.removed.append(identifier)


@pytest_asyncio.fixture
async def orchestrator(tmp_path: Path):
    workflow_path = tmp_path / "WORKFLOW.md"
    workflow_path.write_text(
        "---\ntracker:\n  kind: linear\n  api_key: test\n  project_slug: ace\nagent:\n  max_concurrent_agents: 2\n  max_retry_backoff_ms: 20000\n---\n{{ issue.identifier }}",
        encoding="utf-8",
    )
    orchestrator = SymphonyOrchestrator(workflow_path)
    await orchestrator._reload_workflow(force=True, fail_on_error=True)
    orchestrator._state = RuntimeState(
        poll_interval_ms=orchestrator.config.polling.interval_ms,
        max_concurrent_agents=orchestrator.config.agent.max_concurrent_agents,
    )
    orchestrator._workspace_manager = _DummyWorkspaceManager()
    return orchestrator


@pytest.mark.asyncio
async def test_should_dispatch_blocks_todo_with_non_terminal_blocker(
    orchestrator: SymphonyOrchestrator,
):
    blocked_issue = Issue(
        id="1",
        identifier="ACE-1",
        title="Blocked",
        state="Todo",
        blocked_by=(BlockerRef(id="2", identifier="ACE-2", state="In Progress"),),
    )
    ready_issue = Issue(
        id="2",
        identifier="ACE-2",
        title="Ready",
        state="Todo",
        blocked_by=(BlockerRef(id="3", identifier="ACE-3", state="Done"),),
    )

    assert orchestrator._should_dispatch(blocked_issue) is False
    assert orchestrator._should_dispatch(ready_issue) is True


@pytest.mark.asyncio
async def test_sort_issues_priority_then_oldest(orchestrator: SymphonyOrchestrator):
    newer = Issue(
        id="1", identifier="ACE-2", title="Newer", state="Todo", priority=1, created_at=utc_now()
    )
    older = Issue(
        id="2",
        identifier="ACE-1",
        title="Older",
        state="Todo",
        priority=1,
        created_at=utc_now() - timedelta(days=1),
    )
    low_priority = Issue(id="3", identifier="ACE-3", title="Low", state="Todo", priority=3)

    ordered = orchestrator._sort_issues([newer, low_priority, older])

    assert [issue.identifier for issue in ordered] == ["ACE-1", "ACE-2", "ACE-3"]


@pytest.mark.asyncio
async def test_schedule_retry_uses_continuation_delay_and_backoff(
    orchestrator: SymphonyOrchestrator, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(time, "monotonic", lambda: 100.0)

    orchestrator._schedule_retry("1", 1, identifier="ACE-1", continuation=True)
    continuation = orchestrator.state.retry_attempts["1"]

    orchestrator._schedule_retry("2", 3, identifier="ACE-2", error="boom")
    failure = orchestrator.state.retry_attempts["2"]

    assert continuation.due_at_ms == 101000
    assert failure.due_at_ms == 120000


@pytest.mark.asyncio
async def test_handle_worker_exit_normal_schedules_continuation_retry(
    orchestrator: SymphonyOrchestrator,
):
    task = asyncio.get_running_loop().create_future()
    task.set_result(None)
    running_task = asyncio.create_task(asyncio.sleep(0))
    await running_task
    entry = RunningEntry(
        issue=Issue(id="1", identifier="ACE-1", title="Title", state="Todo"),
        workspace_path=Path("/tmp/ACE-1"),
        started_at=utc_now(),
        task=running_task,
    )
    orchestrator.state.running["1"] = entry
    orchestrator.state.claimed.add("1")

    await orchestrator._handle_worker_exit("1", running_task)

    assert orchestrator.state.retry_attempts["1"].attempt == 1


@pytest.mark.asyncio
async def test_handle_agent_event_accumulates_absolute_usage(orchestrator: SymphonyOrchestrator):
    running_task = asyncio.create_task(asyncio.sleep(3600))
    entry = RunningEntry(
        issue=Issue(id="1", identifier="ACE-1", title="Title", state="Todo"),
        workspace_path=Path("/tmp/ACE-1"),
        started_at=utc_now(),
        task=running_task,
    )
    orchestrator.state.running["1"] = entry

    orchestrator._handle_agent_event(
        "1",
        AgentEvent(
            event="notification",
            timestamp=utc_now(),
            usage={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
        ),
    )
    orchestrator._handle_agent_event(
        "1",
        AgentEvent(
            event="notification",
            timestamp=utc_now(),
            usage={"input_tokens": 12, "output_tokens": 7, "total_tokens": 19},
        ),
    )

    assert orchestrator.state.codex_totals.input_tokens == 12
    assert orchestrator.state.codex_totals.output_tokens == 7
    assert orchestrator.state.codex_totals.total_tokens == 19

    running_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await running_task
