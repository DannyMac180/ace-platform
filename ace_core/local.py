"""Local OSS implementations for storage, inference, and eval contracts."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

import openai
from anthropic import AsyncAnthropic

from .contracts import (
    EvalCase,
    EvalCaseResult,
    EvalResult,
    EvalSpec,
    InferenceMessage,
    ModelRequest,
    ModelResponse,
    PlaybookRecord,
    Scope,
    TokenUsage,
)


def _record_to_payload(playbook: PlaybookRecord) -> dict[str, Any]:
    return {
        "id": playbook.id,
        "name": playbook.name,
        "content": playbook.content,
        "scope": {"kind": playbook.scope.kind, "id": playbook.scope.id},
        "description": playbook.description,
        "version": playbook.version,
        "metadata": playbook.metadata,
    }


def _record_from_payload(payload: Mapping[str, Any]) -> PlaybookRecord:
    scope_payload = payload["scope"]
    return PlaybookRecord(
        id=str(payload["id"]),
        name=str(payload["name"]),
        content=str(payload["content"]),
        scope=Scope(kind=scope_payload["kind"], id=scope_payload.get("id")),
        description=payload.get("description"),
        version=payload.get("version"),
        metadata=dict(payload.get("metadata") or {}),
    )


class FilesystemPlaybookStore:
    """Persist playbooks as JSON files under a local directory."""

    def __init__(self, root_dir: str | Path):
        self._root_dir = Path(root_dir)
        self._playbooks_dir = self._root_dir / "playbooks"
        self._playbooks_dir.mkdir(parents=True, exist_ok=True)

    async def get(self, id: str) -> PlaybookRecord | None:
        return await asyncio.to_thread(self._get_sync, id)

    async def put(self, playbook: PlaybookRecord) -> None:
        await asyncio.to_thread(self._put_sync, playbook)

    async def list(self, scope: Scope) -> list[PlaybookRecord]:
        return await asyncio.to_thread(self._list_sync, scope)

    def _get_sync(self, id: str) -> PlaybookRecord | None:
        path = self._playbook_path(id)
        if not path.exists():
            return None
        return _record_from_payload(json.loads(path.read_text(encoding="utf-8")))

    def _put_sync(self, playbook: PlaybookRecord) -> None:
        path = self._playbook_path(playbook.id)
        payload = json.dumps(_record_to_payload(playbook), indent=2, sort_keys=True)
        temp_path = path.with_suffix(".tmp")
        temp_path.write_text(payload + "\n", encoding="utf-8")
        temp_path.replace(path)

    def _list_sync(self, scope: Scope) -> list[PlaybookRecord]:
        records: list[PlaybookRecord] = []
        for path in sorted(self._playbooks_dir.glob("*.json")):
            record = _record_from_payload(json.loads(path.read_text(encoding="utf-8")))
            if record.scope == scope:
                records.append(record)
        return records

    def _playbook_path(self, playbook_id: str) -> Path:
        return self._playbooks_dir / f"{quote(playbook_id, safe='')}.json"


class SQLitePlaybookStore:
    """Persist playbooks in a local SQLite database file."""

    def __init__(self, database_path: str | Path):
        self._database_path = Path(database_path)
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    async def get(self, id: str) -> PlaybookRecord | None:
        return await asyncio.to_thread(self._get_sync, id)

    async def put(self, playbook: PlaybookRecord) -> None:
        await asyncio.to_thread(self._put_sync, playbook)

    async def list(self, scope: Scope) -> list[PlaybookRecord]:
        return await asyncio.to_thread(self._list_sync, scope)

    def _initialize(self) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS playbooks (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    scope_kind TEXT NOT NULL,
                    scope_id TEXT,
                    description TEXT,
                    version TEXT,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            connection.commit()

    def _get_sync(self, id: str) -> PlaybookRecord | None:
        with sqlite3.connect(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT id, name, content, scope_kind, scope_id, description, version, metadata_json
                FROM playbooks
                WHERE id = ?
                """,
                (id,),
            ).fetchone()
        return self._row_to_record(row)

    def _put_sync(self, playbook: PlaybookRecord) -> None:
        with sqlite3.connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO playbooks (
                    id,
                    name,
                    content,
                    scope_kind,
                    scope_id,
                    description,
                    version,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    content = excluded.content,
                    scope_kind = excluded.scope_kind,
                    scope_id = excluded.scope_id,
                    description = excluded.description,
                    version = excluded.version,
                    metadata_json = excluded.metadata_json
                """,
                (
                    playbook.id,
                    playbook.name,
                    playbook.content,
                    playbook.scope.kind,
                    playbook.scope.id,
                    playbook.description,
                    playbook.version,
                    json.dumps(playbook.metadata, sort_keys=True),
                ),
            )
            connection.commit()

    def _list_sync(self, scope: Scope) -> list[PlaybookRecord]:
        with sqlite3.connect(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT id, name, content, scope_kind, scope_id, description, version, metadata_json
                FROM playbooks
                WHERE scope_kind = ? AND (
                    (scope_id IS NULL AND ? IS NULL)
                    OR scope_id = ?
                )
                ORDER BY id
                """,
                (scope.kind, scope.id, scope.id),
            ).fetchall()
        return [record for row in rows if (record := self._row_to_record(row)) is not None]

    def _row_to_record(self, row: tuple[Any, ...] | None) -> PlaybookRecord | None:
        if row is None:
            return None
        return PlaybookRecord(
            id=row[0],
            name=row[1],
            content=row[2],
            scope=Scope(kind=row[3], id=row[4]),
            description=row[5],
            version=row[6],
            metadata=json.loads(row[7]),
        )


LocalPlaybookStore = SQLitePlaybookStore


class InferenceProvider(Protocol):
    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Execute one inference request."""


def _message_to_dict(message: InferenceMessage) -> dict[str, str]:
    payload = {"role": message.role, "content": message.content}
    if message.name is not None:
        payload["name"] = message.name
    return payload


def _message_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else getattr(item, "text", "")
            for item in value
        )
    return str(value)


def _usage_from_response(usage: Any) -> TokenUsage | None:
    if usage is None:
        return None
    input_tokens = getattr(usage, "prompt_tokens", None)
    if input_tokens is None:
        input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "completion_tokens", None)
    if output_tokens is None:
        output_tokens = getattr(usage, "output_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _dump_raw_response(response: Any) -> dict[str, Any] | None:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    return None


def _is_reasoning_model(model: str) -> bool:
    return model.startswith(("gpt-5", "o1", "o3", "o4"))


class OpenAIInferenceProvider:
    """Call OpenAI-compatible chat completion APIs directly."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        organization: str | None = None,
        client: openai.AsyncOpenAI | None = None,
    ):
        self._api_key = api_key
        self._base_url = base_url
        self._organization = organization
        self._client = client

    async def complete(self, request: ModelRequest) -> ModelResponse:
        client = self._client or self._build_client(request)
        params: dict[str, Any] = {
            "model": request.model,
            "messages": [_message_to_dict(message) for message in request.messages],
        }
        if request.max_tokens is not None:
            token_key = (
                "max_completion_tokens"
                if request.model.startswith(("gpt-4o", "gpt-5", "o1", "o3", "o4"))
                else "max_tokens"
            )
            params[token_key] = request.max_tokens
        if request.temperature is not None and not _is_reasoning_model(request.model):
            params["temperature"] = request.temperature
        if _is_reasoning_model(request.model):
            reasoning_effort = request.metadata.get("reasoning_effort")
            if reasoning_effort is not None:
                params["reasoning_effort"] = reasoning_effort
        response = await client.chat.completions.create(**params)
        content = _message_text(response.choices[0].message.content)
        return ModelResponse(
            model=request.model,
            output_text=content,
            finish_reason=response.choices[0].finish_reason,
            usage=_usage_from_response(response.usage),
            raw_response=_dump_raw_response(response),
            metadata={
                "provider": "openai",
                "request_id": getattr(response, "id", None),
            },
        )

    def _build_client(self, request: ModelRequest) -> openai.AsyncOpenAI:
        api_key = request.metadata.get("api_key") or self._api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OpenAI API key is required for direct provider inference. "
                "Set OPENAI_API_KEY or pass metadata['api_key']."
            )
        return openai.AsyncOpenAI(
            api_key=api_key,
            base_url=request.metadata.get("base_url") or self._base_url,
            organization=request.metadata.get("organization") or self._organization,
        )


class AnthropicInferenceProvider:
    """Call Anthropic's Messages API directly."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client: AsyncAnthropic | None = None,
    ):
        self._api_key = api_key
        self._base_url = base_url
        self._client = client

    async def complete(self, request: ModelRequest) -> ModelResponse:
        client = self._client or self._build_client(request)
        system_messages = [
            message.content for message in request.messages if message.role == "system"
        ]
        messages = [
            {
                "role": "assistant" if message.role in {"assistant", "tool"} else "user",
                "content": message.content,
            }
            for message in request.messages
            if message.role != "system"
        ]
        params: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "max_tokens": request.max_tokens or int(request.metadata.get("max_tokens") or 1024),
        }
        if request.temperature is not None:
            params["temperature"] = request.temperature
        if system_messages:
            params["system"] = "\n\n".join(system_messages)
        response = await client.messages.create(**params)
        output_text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        return ModelResponse(
            model=request.model,
            output_text=output_text,
            finish_reason=getattr(response, "stop_reason", None),
            usage=_usage_from_response(getattr(response, "usage", None)),
            raw_response=_dump_raw_response(response),
            metadata={
                "provider": "anthropic",
                "request_id": getattr(response, "id", None),
            },
        )

    def _build_client(self, request: ModelRequest) -> AsyncAnthropic:
        api_key = request.metadata.get("api_key") or self._api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "Anthropic API key is required for direct provider inference. "
                "Set ANTHROPIC_API_KEY or pass metadata['api_key']."
            )
        return AsyncAnthropic(
            api_key=api_key,
            base_url=request.metadata.get("base_url") or self._base_url,
        )


class DirectInferenceGateway:
    """Route portable model requests to direct provider clients."""

    def __init__(
        self,
        *,
        providers: Mapping[str, InferenceProvider] | None = None,
        default_provider: str = "openai",
    ):
        self._providers: dict[str, InferenceProvider] = {
            "openai": OpenAIInferenceProvider(),
            "anthropic": AnthropicInferenceProvider(),
        }
        if providers is not None:
            self._providers.update(providers)
        self._default_provider = default_provider

    async def call(self, request: ModelRequest) -> ModelResponse:
        provider_name = self._resolve_provider(request)
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ValueError(
                f"Unsupported inference provider '{provider_name}'. "
                f"Available providers: {', '.join(sorted(self._providers))}."
            )
        response = await provider.complete(request)
        response.metadata.setdefault("provider", provider_name)
        return response

    def _resolve_provider(self, request: ModelRequest) -> str:
        provider = request.metadata.get("provider")
        if isinstance(provider, str) and provider:
            return provider
        model = request.model.lower()
        if model.startswith("claude"):
            return "anthropic"
        if model.startswith(("gpt-", "o1", "o3", "o4")):
            return "openai"
        return self._default_provider


class LocalEvalRunner:
    """Evaluate prompts locally with a portable inference gateway."""

    def __init__(
        self,
        gateway: Any | None = None,
        *,
        default_model: str | None = None,
    ):
        self._gateway = gateway
        self._default_model = default_model

    async def run(self, spec: EvalSpec) -> EvalResult:
        case_results: list[EvalCaseResult] = []
        for case in spec.cases:
            actual_output = await self._generate_output(spec, case)
            passed, score = self._score_case(spec.metric, actual_output, case.expected_output)
            case_results.append(
                EvalCaseResult(
                    case_id=case.id,
                    passed=passed,
                    actual_output=actual_output,
                    score=score,
                    details={"metric": spec.metric},
                )
            )

        passed = all(case_result.passed for case_result in case_results)
        score = (
            sum(case_result.score or 0.0 for case_result in case_results) / len(case_results)
            if case_results
            else None
        )
        return EvalResult(
            spec_id=spec.id,
            case_results=case_results,
            passed=passed,
            score=score,
            metadata={"metric": spec.metric},
        )

    async def _generate_output(self, spec: EvalSpec, case: EvalCase) -> str:
        actual_output = case.metadata.get("actual_output")
        if isinstance(actual_output, str):
            return actual_output

        if self._gateway is None:
            raise ValueError(
                "LocalEvalRunner requires either a gateway or case.metadata['actual_output']."
            )

        model = case.metadata.get("model") or spec.metadata.get("model") or self._default_model
        if model is None:
            raise ValueError(
                "LocalEvalRunner requires a model via spec.metadata['model'], "
                "case.metadata['model'], or default_model."
            )
        system_prompt = case.metadata.get("system_prompt") or spec.metadata.get("system_prompt")
        messages = []
        if system_prompt:
            messages.append(InferenceMessage(role="system", content=str(system_prompt)))
        messages.append(InferenceMessage(role="user", content=case.prompt))
        response = await self._gateway.call(
            ModelRequest(
                model=str(model),
                messages=messages,
                max_tokens=spec.metadata.get("max_tokens"),
                temperature=spec.metadata.get("temperature"),
                metadata={
                    **dict(spec.metadata),
                    **dict(case.metadata),
                },
            )
        )
        return response.output_text

    def _score_case(
        self,
        metric: str,
        actual_output: str,
        expected_output: str | None,
    ) -> tuple[bool, float | None]:
        if expected_output is None:
            return True, None
        actual_normalized = actual_output.strip()
        expected_normalized = expected_output.strip()
        metric_name = metric.lower()
        if metric_name == "exact_match":
            passed = actual_normalized == expected_normalized
        elif metric_name in {"contains", "substring"}:
            passed = expected_normalized in actual_normalized
        else:
            raise ValueError(
                f"Unsupported local eval metric '{metric}'. "
                "Supported metrics: exact_match, contains."
            )
        return passed, 1.0 if passed else 0.0


__all__ = [
    "AnthropicInferenceProvider",
    "DirectInferenceGateway",
    "FilesystemPlaybookStore",
    "InferenceProvider",
    "LocalEvalRunner",
    "LocalPlaybookStore",
    "OpenAIInferenceProvider",
    "SQLitePlaybookStore",
]
