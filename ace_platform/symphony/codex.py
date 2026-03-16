"""Codex app-server runner used by Symphony workers."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from ace_platform.symphony.config import CodexConfig
from ace_platform.symphony.errors import AgentRunnerError, TrackerError
from ace_platform.symphony.models import AgentEvent, AgentRunResult, utc_now

logger = logging.getLogger(__name__)
MAX_PROTOCOL_LINE_BYTES = 10 * 1024 * 1024

ToolHandler = Callable[[str, Any], Awaitable[dict[str, Any]]]


class CodexAppServerSession:
    """Manage one live Codex app-server subprocess."""

    def __init__(
        self,
        config: CodexConfig,
        workspace_path: Path,
        *,
        tool_handler: ToolHandler | None = None,
        event_callback: Callable[[AgentEvent], None] | None = None,
    ) -> None:
        self._config = config
        self._workspace_path = workspace_path
        self._tool_handler = tool_handler
        self._event_callback = event_callback
        self._process: asyncio.subprocess.Process | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._active_turn_future: asyncio.Future[AgentRunResult] | None = None
        self._thread_id: str | None = None
        self._turn_id: str | None = None
        self._closed = False

    @property
    def pid(self) -> int | None:
        return self._process.pid if self._process else None

    @property
    def thread_id(self) -> str | None:
        return self._thread_id

    async def start(self) -> CodexAppServerSession:
        """Launch the app-server and perform the startup handshake."""

        if not self._workspace_path.is_absolute():
            raise AgentRunnerError(
                "invalid_workspace_cwd",
                f"Workspace path must be absolute: {self._workspace_path}",
            )

        try:
            self._process = await asyncio.create_subprocess_exec(
                "bash",
                "-lc",
                self._config.command,
                cwd=str(self._workspace_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=MAX_PROTOCOL_LINE_BYTES,
            )
        except FileNotFoundError as exc:
            raise AgentRunnerError("codex_not_found", str(exc)) from exc
        except OSError as exc:
            raise AgentRunnerError("codex_not_found", str(exc)) from exc

        self._stdout_task = asyncio.create_task(self._read_stdout())
        self._stderr_task = asyncio.create_task(self._read_stderr())

        await self._request(
            "initialize",
            {"clientInfo": {"name": "symphony", "version": "1.0"}, "capabilities": {}},
        )
        await self._notify("initialized", {})

        thread_result = await self._request(
            "thread/start",
            {
                "approvalPolicy": self._config.approval_policy,
                "sandbox": self._config.thread_sandbox,
                "cwd": str(self._workspace_path),
            },
        )
        self._thread_id = _extract_thread_id(thread_result)
        if not self._thread_id:
            raise AgentRunnerError(
                "response_error", "thread/start response did not include thread id"
            )

        return self

    async def run_turn(self, prompt: str, *, title: str) -> AgentRunResult:
        """Run one Codex turn on the current thread."""

        if not self._thread_id:
            raise AgentRunnerError("response_error", "Session has not been started")

        loop = asyncio.get_running_loop()
        self._active_turn_future = loop.create_future()
        turn_result = await self._request(
            "turn/start",
            {
                "threadId": self._thread_id,
                "input": [{"type": "text", "text": prompt}],
                "cwd": str(self._workspace_path),
                "title": title,
                "approvalPolicy": self._config.approval_policy,
                "sandboxPolicy": self._config.turn_sandbox_policy,
            },
        )
        self._turn_id = _extract_turn_id(turn_result)
        session_id = _compose_session_id(self._thread_id, self._turn_id)
        self._emit(
            "session_started",
            session_id=session_id,
            thread_id=self._thread_id,
            turn_id=self._turn_id,
        )

        try:
            result = await asyncio.wait_for(
                self._active_turn_future,
                timeout=self._config.turn_timeout_ms / 1000,
            )
        except asyncio.TimeoutError as exc:
            raise AgentRunnerError("turn_timeout", "Turn timed out") from exc
        finally:
            self._active_turn_future = None
        return result

    async def stop(self) -> None:
        """Terminate the app-server subprocess."""

        if self._closed:
            return
        self._closed = True

        for future in self._pending.values():
            if not future.done():
                future.set_exception(
                    AgentRunnerError("port_exit", "Codex app-server exited before responding")
                )
        self._pending.clear()

        if self._process and self._process.returncode is None:
            self._process.terminate()
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._process.wait(), timeout=2)
            if self._process.returncode is None:
                self._process.kill()
                await self._process.wait()

        for task in (self._stdout_task, self._stderr_task):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    async def _request(self, method: str, params: Any) -> dict[str, Any]:
        if not self._process or not self._process.stdin:
            raise AgentRunnerError("port_exit", "Codex app-server is not running")

        self._request_id += 1
        request_id = self._request_id
        loop = asyncio.get_running_loop()
        future: asyncio.Future[dict[str, Any]] = loop.create_future()
        self._pending[request_id] = future
        await self._send_json({"id": request_id, "method": method, "params": params})
        try:
            response = await asyncio.wait_for(
                future,
                timeout=self._config.read_timeout_ms / 1000,
            )
        except asyncio.TimeoutError as exc:
            self._pending.pop(request_id, None)
            raise AgentRunnerError("response_timeout", f"{method} response timed out") from exc

        if response.get("error"):
            raise AgentRunnerError("response_error", json.dumps(response["error"]))
        result = response.get("result")
        if not isinstance(result, dict):
            raise AgentRunnerError("response_error", f"{method} response missing result object")
        return result

    async def _notify(self, method: str, params: Any) -> None:
        await self._send_json({"method": method, "params": params})

    async def _send_json(self, payload: dict[str, Any]) -> None:
        if not self._process or not self._process.stdin:
            raise AgentRunnerError("port_exit", "Codex app-server stdin is unavailable")
        self._process.stdin.write(json.dumps(payload).encode("utf-8") + b"\n")
        await self._process.stdin.drain()

    async def _read_stdout(self) -> None:
        if not self._process or not self._process.stdout:
            return
        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break
                try:
                    payload = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    self._emit("malformed", message=line.decode("utf-8", errors="replace").strip())
                    continue
                await self._handle_message(payload)
        finally:
            if self._active_turn_future and not self._active_turn_future.done():
                self._active_turn_future.set_exception(
                    AgentRunnerError("port_exit", "Codex app-server exited during a turn")
                )

    async def _read_stderr(self) -> None:
        if not self._process or not self._process.stderr:
            return
        while True:
            line = await self._process.stderr.readline()
            if not line:
                break
            logger.info(
                "codex_stderr pid=%s message=%s",
                self.pid,
                line.decode("utf-8", errors="replace").strip(),
            )

    async def _handle_message(self, payload: dict[str, Any]) -> None:
        if (
            "id" in payload
            and ("result" in payload or "error" in payload)
            and "method" not in payload
        ):
            future = self._pending.pop(int(payload["id"]), None)
            if future and not future.done():
                future.set_result(payload)
            return

        if "method" in payload and "id" in payload:
            await self._handle_server_request(payload)
            return

        if "method" in payload:
            self._handle_notification(payload)
            return

        self._emit("other_message", payload=payload, message=_summarize_payload(payload))

    async def _handle_server_request(self, payload: dict[str, Any]) -> None:
        method = str(payload.get("method"))
        request_id = payload["id"]
        params = payload.get("params", {})

        if method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}:
            decision = "acceptForSession"
            await self._send_json({"id": request_id, "result": {"decision": decision}})
            self._emit("approval_auto_approved", payload={"method": method})
            return

        if method in {"execCommandApproval", "applyPatchApproval"}:
            await self._send_json(
                {"id": request_id, "result": {"decision": "approved_for_session"}}
            )
            self._emit("approval_auto_approved", payload={"method": method})
            return

        if method == "item/permissions/requestApproval":
            await self._send_json(
                {
                    "id": request_id,
                    "result": {"permissions": params.get("permissions") or {}, "scope": "session"},
                }
            )
            self._emit("approval_auto_approved", payload={"method": method})
            return

        if method == "item/tool/call":
            tool_name = str(params.get("tool"))
            arguments = params.get("arguments")
            if self._tool_handler is None:
                result = _tool_failure_payload("unsupported_tool_call", tool_name)
                self._emit("unsupported_tool_call", payload={"tool": tool_name})
            else:
                try:
                    result = await self._tool_handler(tool_name, arguments)
                except TrackerError as exc:
                    result = _tool_failure_payload(exc.code, tool_name, message=str(exc))
                except Exception as exc:  # pragma: no cover - defensive
                    result = _tool_failure_payload("tool_call_failed", tool_name, message=str(exc))
            await self._send_json({"id": request_id, "result": result})
            return

        if method == "mcpServer/elicitation/request":
            await self._send_json({"id": request_id, "result": {"action": "decline"}})
            self._fail_active_turn("turn_input_required", "MCP elicitation requested user input")
            self._emit("turn_input_required", payload=params)
            return

        if method == "item/tool/requestUserInput":
            await self._send_json({"id": request_id, "result": {"answers": {}}})
            self._fail_active_turn("turn_input_required", "Tool requested user input")
            self._emit("turn_input_required", payload=params)
            return

        await self._send_json({"id": request_id, "result": {}})
        self._emit("other_message", payload=payload, message=f"Unhandled request {method}")

    def _handle_notification(self, payload: dict[str, Any]) -> None:
        method = str(payload.get("method"))
        params = payload.get("params", {})
        if method == "thread/tokenUsage/updated":
            usage = extract_total_usage(params)
            if usage:
                self._emit("notification", payload=params, usage=usage)
            return

        if method == "account/rateLimits/updated":
            self._emit("notification", payload=params, rate_limits=params.get("rateLimits", params))
            return

        if method == "turn/started":
            turn = params.get("turn") if isinstance(params, dict) else {}
            if isinstance(turn, dict) and turn.get("id"):
                self._turn_id = str(turn["id"])
            self._emit(
                "notification",
                thread_id=self._thread_id,
                turn_id=self._turn_id,
                message="turn_started",
                payload=params,
            )
            return

        if method == "turn/completed":
            turn = params.get("turn") if isinstance(params, dict) else {}
            status = str(turn.get("status", "completed")) if isinstance(turn, dict) else "completed"
            turn_id = (
                str(turn.get("id")) if isinstance(turn, dict) and turn.get("id") else self._turn_id
            )
            self._turn_id = turn_id
            session_id = _compose_session_id(self._thread_id, turn_id)
            if status == "completed":
                result = AgentRunResult(
                    success=True,
                    status="completed",
                    session_id=session_id,
                    thread_id=self._thread_id,
                    turn_id=turn_id,
                )
                self._resolve_active_turn(result)
                self._emit("turn_completed", session_id=session_id, turn_id=turn_id, payload=params)
                return
            if status == "interrupted":
                result = AgentRunResult(
                    success=False,
                    status="cancelled",
                    error="turn interrupted",
                    session_id=session_id,
                    thread_id=self._thread_id,
                    turn_id=turn_id,
                )
                self._resolve_active_turn(result)
                self._emit("turn_cancelled", session_id=session_id, turn_id=turn_id, payload=params)
                return
            error_message = _extract_turn_error(turn) or "turn failed"
            result = AgentRunResult(
                success=False,
                status="failed",
                error=error_message,
                session_id=session_id,
                thread_id=self._thread_id,
                turn_id=turn_id,
            )
            self._resolve_active_turn(result)
            self._emit(
                "turn_failed",
                session_id=session_id,
                turn_id=turn_id,
                payload=params,
                message=error_message,
            )
            return

        self._emit("notification", payload=params, message=_summarize_payload(params) or method)

    def _resolve_active_turn(self, result: AgentRunResult) -> None:
        if self._active_turn_future and not self._active_turn_future.done():
            self._active_turn_future.set_result(result)

    def _fail_active_turn(self, code: str, message: str) -> None:
        if self._active_turn_future and not self._active_turn_future.done():
            self._active_turn_future.set_exception(AgentRunnerError(code, message))

    def _emit(self, event: str, **kwargs: Any) -> None:
        if self._event_callback is None:
            return
        self._event_callback(
            AgentEvent(
                event=event,
                timestamp=utc_now(),
                session_id=kwargs.pop(
                    "session_id", _compose_session_id(self._thread_id, self._turn_id)
                ),
                thread_id=kwargs.pop("thread_id", self._thread_id),
                turn_id=kwargs.pop("turn_id", self._turn_id),
                codex_app_server_pid=self.pid,
                message=kwargs.pop("message", None),
                usage=kwargs.pop("usage", None),
                rate_limits=kwargs.pop("rate_limits", None),
                payload=kwargs.pop("payload", None),
            )
        )


def _extract_thread_id(result: dict[str, Any]) -> str | None:
    thread = result.get("thread")
    if isinstance(thread, dict) and thread.get("id"):
        return str(thread["id"])
    return None


def _extract_turn_id(result: dict[str, Any]) -> str | None:
    turn = result.get("turn")
    if isinstance(turn, dict) and turn.get("id"):
        return str(turn["id"])
    return None


def _compose_session_id(thread_id: str | None, turn_id: str | None) -> str | None:
    if not thread_id or not turn_id:
        return None
    return f"{thread_id}-{turn_id}"


def _extract_turn_error(turn: Any) -> str | None:
    if not isinstance(turn, dict):
        return None
    error = turn.get("error")
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])
    return None


def _tool_failure_payload(
    code: str, tool_name: str | None, *, message: str | None = None
) -> dict[str, Any]:
    body = {"error": code}
    if tool_name:
        body["tool"] = tool_name
    if message:
        body["message"] = message
    return {
        "success": False,
        "contentItems": [{"type": "inputText", "text": json.dumps(body, sort_keys=True)}],
    }


def extract_total_usage(payload: Any) -> dict[str, int] | None:
    """Extract absolute token totals from a compatible payload shape."""

    if not isinstance(payload, dict):
        return None

    candidates = [
        payload.get("tokenUsage"),
        payload.get("total_token_usage"),
        payload.get("totalTokenUsage"),
        payload.get("usage"),
        payload,
    ]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        input_tokens = _coerce_int(
            candidate.get(
                "inputTokens", candidate.get("input_tokens", candidate.get("prompt_tokens"))
            )
        )
        output_tokens = _coerce_int(
            candidate.get(
                "outputTokens",
                candidate.get("output_tokens", candidate.get("completion_tokens")),
            )
        )
        total_tokens = _coerce_int(candidate.get("totalTokens", candidate.get("total_tokens")))
        if any(value is not None for value in (input_tokens, output_tokens, total_tokens)):
            total = total_tokens
            if total is None and input_tokens is not None and output_tokens is not None:
                total = input_tokens + output_tokens
            return {
                "input_tokens": input_tokens or 0,
                "output_tokens": output_tokens or 0,
                "total_tokens": total or 0,
            }
    return None


def _coerce_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _summarize_payload(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key in ("message", "text", "summary", "status"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        for value in payload.values():
            summary = _summarize_payload(value)
            if summary:
                return summary
        return None
    if isinstance(payload, list):
        for item in payload:
            summary = _summarize_payload(item)
            if summary:
                return summary
    return None
