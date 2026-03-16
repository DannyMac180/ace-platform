from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ace_platform.symphony.codex import CodexAppServerSession, extract_total_usage
from ace_platform.symphony.config import CodexConfig
from ace_platform.symphony.errors import AgentRunnerError


def _write_fake_server(path: Path) -> None:
    path.write_text(
        """
import json
import os
import sys

mode = os.environ.get("FAKE_MODE", "normal")
turn_counter = 0

for raw in sys.stdin:
    message = json.loads(raw)
    method = message.get("method")
    if method == "initialize":
        print(json.dumps({"id": message["id"], "result": {"protocolVersion": "2"}}), flush=True)
    elif method == "initialized":
        continue
    elif method == "thread/start":
        print(json.dumps({
            "id": message["id"],
            "result": {
                "approvalPolicy": "never",
                "cwd": message["params"]["cwd"],
                "model": "test-model",
                "modelProvider": "openai",
                "sandbox": {"type": "workspaceWrite"},
                "thread": {"id": "thread-1"},
            }
        }), flush=True)
    elif method == "turn/start":
        turn_counter += 1
        turn_id = f"turn-{turn_counter}"
        print(json.dumps({"id": message["id"], "result": {"turn": {"id": turn_id, "items": [], "status": "inProgress"}}}), flush=True)
        if mode == "user_input":
            print(json.dumps({
                "id": "req-1",
                "method": "item/tool/requestUserInput",
                "params": {"questions": []},
            }), flush=True)
        else:
            print(json.dumps({
                "method": "thread/tokenUsage/updated",
                "params": {
                    "threadId": "thread-1",
                    "tokenUsage": {"inputTokens": 12, "outputTokens": 4, "totalTokens": 16},
                },
            }), flush=True)
            print(json.dumps({
                "method": "turn/completed",
                "params": {"threadId": "thread-1", "turn": {"id": turn_id, "items": [], "status": "completed"}},
            }), flush=True)
    elif message.get("id") == "req-1":
        print(json.dumps({
            "method": "turn/completed",
            "params": {"threadId": "thread-1", "turn": {"id": "turn-1", "items": [], "status": "interrupted"}},
        }), flush=True)
""",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_codex_session_runs_turn_and_emits_usage(tmp_path: Path):
    server_script = tmp_path / "fake_server.py"
    _write_fake_server(server_script)
    events = []
    session = CodexAppServerSession(
        CodexConfig(command=f"{sys.executable} -u {server_script}", turn_timeout_ms=2_000),
        tmp_path,
        event_callback=events.append,
    )
    await session.start()

    result = await session.run_turn("hello", title="ACE-1")

    assert result.success is True
    assert any(event.event == "session_started" for event in events)
    assert any(
        event.usage == {"input_tokens": 12, "output_tokens": 4, "total_tokens": 16}
        for event in events
    )
    await session.stop()


@pytest.mark.asyncio
async def test_codex_session_fails_when_user_input_is_requested(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    server_script = tmp_path / "fake_server.py"
    _write_fake_server(server_script)
    monkeypatch.setenv("FAKE_MODE", "user_input")
    session = CodexAppServerSession(
        CodexConfig(command=f"{sys.executable} -u {server_script}", turn_timeout_ms=2_000),
        tmp_path,
    )
    await session.start()

    with pytest.raises(AgentRunnerError, match="user input"):
        await session.run_turn("hello", title="ACE-1")

    await session.stop()


def test_extract_total_usage_accepts_common_shapes():
    assert extract_total_usage(
        {"tokenUsage": {"inputTokens": 1, "outputTokens": 2, "totalTokens": 3}}
    ) == {
        "input_tokens": 1,
        "output_tokens": 2,
        "total_tokens": 3,
    }
    assert extract_total_usage({"usage": {"prompt_tokens": 5, "completion_tokens": 7}}) == {
        "input_tokens": 5,
        "output_tokens": 7,
        "total_tokens": 12,
    }
