from __future__ import annotations

from pathlib import Path
from typing import Any

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


class PlaybookExecutionProvider:
    def __init__(self, provider_name: str = "openai"):
        self.provider_name = provider_name
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        system_prompt = "\n".join(
            message.content for message in request.messages if message.role == "system"
        )
        prompt = " ".join(message.content for message in request.messages if message.role == "user")
        expected_output = request.metadata["expected_output"]
        if expected_output in system_prompt and prompt == "Use the saved local playbook":
            output_text = expected_output
        else:
            output_text = "playbook execution mismatch"
        return ModelResponse(
            model=request.model,
            output_text=output_text,
            metadata={
                "provider": self.provider_name,
                "system_prompt": system_prompt,
            },
        )


@pytest.fixture(
    params=[
        pytest.param(
            lambda root: FilesystemPlaybookStore(root / "runtime"),
            id="filesystem-store",
        ),
        pytest.param(
            lambda root: LocalPlaybookStore(root / "runtime.db"),
            id="sqlite-store",
        ),
    ]
)
def local_store_factory(request: pytest.FixtureRequest) -> Any:
    return request.param


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
async def test_local_runtime_happy_path_ingests_persists_retrieves_and_executes_playbook(
    tmp_path: Path,
    local_store_factory: Any,
) -> None:
    scope = Scope(kind="workspace", id="ws-local")
    playbook = PlaybookRecord(
        id="pb-local-happy-path",
        name="Local happy path",
        content=(
            "When the user asks for the saved local playbook result, "
            "reply exactly with 'portable success'."
        ),
        scope=scope,
        description="Deterministic local execution instructions",
        version="v1",
        metadata={"source": "integration-test"},
    )

    store = local_store_factory(tmp_path)
    await store.put(playbook)

    reloaded_store = local_store_factory(tmp_path)
    retrieved_playbook = await reloaded_store.get(playbook.id)

    assert retrieved_playbook == playbook
    assert await reloaded_store.list(scope) == [playbook]

    provider = PlaybookExecutionProvider()
    gateway = DirectInferenceGateway(providers={"openai": provider})
    runner = LocalEvalRunner(gateway, default_model="gpt-4o-mini")

    result = await runner.run(
        ace_core.EvalSpec(
            id="eval-local-happy-path",
            metric="exact_match",
            metadata={
                "provider": "openai",
                "system_prompt": retrieved_playbook.content,
                "expected_output": "portable success",
            },
            cases=[
                EvalCase(
                    id="case-1",
                    prompt="Use the saved local playbook",
                    expected_output="portable success",
                )
            ],
        )
    )

    assert result.passed is True
    assert result.score == 1.0
    assert result.case_results[0].actual_output == "portable success"
    assert provider.requests[0].messages[0] == InferenceMessage(
        role="system",
        content=retrieved_playbook.content,
    )
    assert provider.requests[0].messages[1] == InferenceMessage(
        role="user",
        content="Use the saved local playbook",
    )


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
