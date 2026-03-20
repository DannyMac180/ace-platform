from __future__ import annotations

from collections.abc import Sequence
from typing import get_args

import pytest

import ace_core
from ace_core.contracts import (
    BYOProviderConfig,
    Entitlements,
    EvalCase,
    EvalCaseResult,
    EvalResult,
    EvalRunner,
    EvalSpec,
    Feature,
    InferenceGateway,
    InferenceMessage,
    ManagedProviderConfig,
    ModelRequest,
    ModelResponse,
    PlaybookRecord,
    PlaybookStore,
    Scope,
    SyncBackend,
    SyncBatch,
    SyncEvent,
)


class LocalPlaybookStore:
    def __init__(self) -> None:
        self._playbooks: dict[str, PlaybookRecord] = {}

    async def get(self, id: str) -> PlaybookRecord | None:
        return self._playbooks.get(id)

    async def put(self, playbook: PlaybookRecord) -> None:
        self._playbooks[playbook.id] = playbook

    async def list(self, scope: Scope) -> list[PlaybookRecord]:
        return [playbook for playbook in self._playbooks.values() if playbook.scope == scope]


class CloudPlaybookStore(LocalPlaybookStore):
    pass


class LocalSyncBackend:
    def __init__(self) -> None:
        self._events: list[SyncEvent] = []

    async def push(self, events: Sequence[SyncEvent]) -> None:
        self._events.extend(events)

    async def pull(self, cursor: str | None = None) -> SyncBatch:
        start = int(cursor) if cursor is not None else 0
        return SyncBatch(events=self._events[start:], next_cursor=str(len(self._events)))


class CloudSyncBackend(LocalSyncBackend):
    pass


class LocalInferenceGateway:
    async def call(self, request: ModelRequest) -> ModelResponse:
        text = " ".join(message.content for message in request.messages)
        return ModelResponse(model=request.model, output_text=text, metadata={"mode": "local"})


class CloudInferenceGateway(LocalInferenceGateway):
    async def call(self, request: ModelRequest) -> ModelResponse:
        response = await super().call(request)
        response.metadata["mode"] = "cloud"
        return response


class LocalEvalRunner:
    async def run(self, spec: EvalSpec) -> EvalResult:
        case_results = [
            EvalCaseResult(
                case_id=case.id,
                passed=case.expected_output == case.prompt,
                actual_output=case.prompt,
                score=1.0 if case.expected_output == case.prompt else 0.0,
            )
            for case in spec.cases
        ]
        passed = all(case_result.passed for case_result in case_results)
        score = sum(case_result.score or 0.0 for case_result in case_results) / len(case_results)
        return EvalResult(spec_id=spec.id, case_results=case_results, passed=passed, score=score)


class CloudEvalRunner(LocalEvalRunner):
    pass


class LocalEntitlements:
    def __init__(self, enabled: set[Feature]) -> None:
        self._enabled = enabled

    async def can(self, feature: Feature) -> bool:
        return feature in self._enabled


class CloudEntitlements(LocalEntitlements):
    pass


@pytest.mark.asyncio
@pytest.mark.parametrize("store_cls", [LocalPlaybookStore, CloudPlaybookStore])
async def test_playbook_store_contract(store_cls: type[LocalPlaybookStore]) -> None:
    store = store_cls()
    scope = Scope(kind="workspace", id="workspace-1")
    playbook = PlaybookRecord(
        id="pb-1",
        name="Core Contract",
        content="Keep interfaces public.",
        scope=scope,
    )

    assert isinstance(store, PlaybookStore)

    await store.put(playbook)
    assert await store.get("pb-1") == playbook
    assert await store.list(scope) == [playbook]


@pytest.mark.asyncio
@pytest.mark.parametrize("backend_cls", [LocalSyncBackend, CloudSyncBackend])
async def test_sync_backend_contract(backend_cls: type[LocalSyncBackend]) -> None:
    backend = backend_cls()
    events = [
        SyncEvent(id="evt-1", entity_type="playbook", entity_id="pb-1", operation="upsert"),
        SyncEvent(id="evt-2", entity_type="playbook", entity_id="pb-1", operation="delete"),
    ]

    assert isinstance(backend, SyncBackend)

    await backend.push(events)
    batch = await backend.pull()

    assert batch.events == events
    assert batch.next_cursor == "2"


@pytest.mark.asyncio
@pytest.mark.parametrize("gateway_cls", [LocalInferenceGateway, CloudInferenceGateway])
async def test_inference_gateway_contract(
    gateway_cls: type[LocalInferenceGateway],
) -> None:
    gateway = gateway_cls()
    request = ModelRequest(
        model="gpt-5.4",
        messages=[InferenceMessage(role="user", content="Define the contract")],
    )

    assert isinstance(gateway, InferenceGateway)

    response = await gateway.call(request)
    assert response.model == "gpt-5.4"
    assert response.output_text == "Define the contract"


@pytest.mark.asyncio
@pytest.mark.parametrize("runner_cls", [LocalEvalRunner, CloudEvalRunner])
async def test_eval_runner_contract(runner_cls: type[LocalEvalRunner]) -> None:
    runner = runner_cls()
    spec = EvalSpec(
        id="eval-1",
        metric="exact_match",
        cases=[
            EvalCase(id="case-1", prompt="pass", expected_output="pass"),
            EvalCase(id="case-2", prompt="fail", expected_output="pass"),
        ],
    )

    assert isinstance(runner, EvalRunner)

    result = await runner.run(spec)
    assert result.spec_id == "eval-1"
    assert len(result.case_results) == 2
    assert result.passed is False
    assert result.score == 0.5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entitlements_cls", "enabled"),
    [
        (LocalEntitlements, {"cloud_sync"}),
        (CloudEntitlements, {"cloud_sync", "managed_inference"}),
    ],
)
async def test_entitlements_contract(
    entitlements_cls: type[LocalEntitlements], enabled: set[Feature]
) -> None:
    entitlements = entitlements_cls(enabled=enabled)

    assert isinstance(entitlements, Entitlements)

    assert await entitlements.can("cloud_sync") is True
    assert await entitlements.can("audit_logs") is False


def test_feature_catalog_matches_product_spec() -> None:
    assert get_args(Feature) == (
        "cloud_sync",
        "hosted_backups",
        "managed_inference",
        "hosted_evals",
        "invite_members",
        "shared_workspace",
        "approvals",
        "rbac",
        "sso",
        "audit_logs",
    )


def test_contracts_are_re_exported_from_ace_core() -> None:
    assert ace_core.BYOProviderConfig is BYOProviderConfig
    assert ace_core.PlaybookStore is PlaybookStore
    assert ace_core.SyncBackend is SyncBackend
    assert ace_core.InferenceGateway is InferenceGateway
    assert ace_core.ManagedProviderConfig is ManagedProviderConfig
    assert ace_core.EvalRunner is EvalRunner
    assert ace_core.Entitlements is Entitlements


def test_model_request_supports_byo_and_managed_inference_configs() -> None:
    byo_request = ModelRequest(
        model="gpt-5.4",
        messages=[InferenceMessage(role="user", content="hello")],
        inference_config=BYOProviderConfig(provider="openai", api_key="sk-byo"),
    )
    managed_request = ModelRequest(
        model="gpt-5.4",
        messages=[InferenceMessage(role="user", content="hello")],
        inference_config=ManagedProviderConfig(provider="openai", workspace_id="ws-1"),
    )

    assert byo_request.inference_config == BYOProviderConfig(
        provider="openai",
        api_key="sk-byo",
    )
    assert managed_request.inference_config == ManagedProviderConfig(
        provider="openai",
        workspace_id="ws-1",
    )
