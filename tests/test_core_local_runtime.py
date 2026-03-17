from __future__ import annotations

from pathlib import Path

import pytest

import ace_core
from ace_core.contracts import (
    EvalCase,
    EvalResult,
    EvalRunner,
    InferenceGateway,
    InferenceMessage,
    ModelRequest,
    ModelResponse,
    PlaybookRecord,
    PlaybookStore,
    Scope,
)
from ace_core.local import (
    DirectInferenceGateway,
    FilesystemPlaybookStore,
    LocalEvalRunner,
    LocalPlaybookStore,
    SQLitePlaybookStore,
)


class RecordingProvider:
    def __init__(self, provider_name: str, outputs: dict[str, str] | None = None):
        self.provider_name = provider_name
        self.outputs = outputs or {}
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        prompt = " ".join(message.content for message in request.messages if message.role == "user")
        return ModelResponse(
            model=request.model,
            output_text=self.outputs.get(prompt, prompt),
            metadata={"provider": self.provider_name},
        )


@pytest.mark.asyncio
async def test_filesystem_playbook_store_persists_records(tmp_path: Path) -> None:
    scope = Scope(kind="workspace", id="ws-1")
    playbook = PlaybookRecord(
        id="pb:1/portable",
        name="Filesystem",
        content="persist locally",
        scope=scope,
        metadata={"tier": "oss"},
    )

    store = FilesystemPlaybookStore(tmp_path / "runtime")
    assert isinstance(store, PlaybookStore)

    await store.put(playbook)

    reloaded_store = FilesystemPlaybookStore(tmp_path / "runtime")
    assert await reloaded_store.get("pb:1/portable") == playbook
    assert await reloaded_store.list(scope) == [playbook]


@pytest.mark.asyncio
async def test_sqlite_playbook_store_persists_records(tmp_path: Path) -> None:
    scope = Scope(kind="user", id="user-1")
    playbook = PlaybookRecord(
        id="pb-2",
        name="SQLite",
        content="persist in sqlite",
        scope=scope,
        version="v1",
    )

    store = SQLitePlaybookStore(tmp_path / "ace.db")
    alias_store = LocalPlaybookStore(tmp_path / "ace.db")

    assert isinstance(store, PlaybookStore)
    assert isinstance(alias_store, PlaybookStore)

    await store.put(playbook)

    reloaded_store = SQLitePlaybookStore(tmp_path / "ace.db")
    assert await reloaded_store.get("pb-2") == playbook
    assert await reloaded_store.list(scope) == [playbook]


@pytest.mark.asyncio
async def test_direct_inference_gateway_routes_requests() -> None:
    openai_provider = RecordingProvider("openai")
    anthropic_provider = RecordingProvider("anthropic")
    gateway = DirectInferenceGateway(
        providers={
            "openai": openai_provider,
            "anthropic": anthropic_provider,
        }
    )

    anthropic_response = await gateway.call(
        ModelRequest(
            model="claude-3-7-sonnet",
            messages=[InferenceMessage(role="user", content="anthropic request")],
        )
    )
    openai_response = await gateway.call(
        ModelRequest(
            model="custom-model",
            messages=[InferenceMessage(role="user", content="openai request")],
            metadata={"provider": "openai"},
        )
    )

    assert isinstance(gateway, InferenceGateway)
    assert anthropic_response.output_text == "anthropic request"
    assert anthropic_response.metadata["provider"] == "anthropic"
    assert openai_response.output_text == "openai request"
    assert openai_response.metadata["provider"] == "openai"
    assert len(anthropic_provider.requests) == 1
    assert len(openai_provider.requests) == 1


@pytest.mark.asyncio
async def test_local_eval_runner_scores_with_gateway_output() -> None:
    provider = RecordingProvider(
        "openai",
        outputs={
            "pass": "pass",
            "fail": "different",
        },
    )
    gateway = DirectInferenceGateway(providers={"openai": provider})
    runner = LocalEvalRunner(gateway, default_model="gpt-4o-mini")

    result = await runner.run(
        ace_core.EvalSpec(
            id="eval-local",
            metric="exact_match",
            metadata={"provider": "openai"},
            cases=[
                EvalCase(id="case-1", prompt="pass", expected_output="pass"),
                EvalCase(id="case-2", prompt="fail", expected_output="fail"),
            ],
        )
    )

    assert isinstance(runner, EvalRunner)
    assert isinstance(result, EvalResult)
    assert result.spec_id == "eval-local"
    assert [case.passed for case in result.case_results] == [True, False]
    assert result.passed is False
    assert result.score == 0.5


@pytest.mark.asyncio
async def test_local_eval_runner_supports_offline_actual_output() -> None:
    runner = LocalEvalRunner()

    result = await runner.run(
        ace_core.EvalSpec(
            id="eval-offline",
            metric="contains",
            cases=[
                EvalCase(
                    id="case-1",
                    prompt="unused",
                    expected_output="portable",
                    metadata={"actual_output": "portable local runtime"},
                )
            ],
        )
    )

    assert result.passed is True
    assert result.score == 1.0
    assert result.case_results[0].actual_output == "portable local runtime"


def test_local_runtime_is_re_exported_from_ace_core() -> None:
    assert ace_core.DirectInferenceGateway is DirectInferenceGateway
    assert ace_core.FilesystemPlaybookStore is FilesystemPlaybookStore
    assert ace_core.LocalEvalRunner is LocalEvalRunner
    assert ace_core.LocalPlaybookStore is LocalPlaybookStore
    assert ace_core.SQLitePlaybookStore is SQLitePlaybookStore
