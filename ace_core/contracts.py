"""Shared OSS/core contracts for storage, sync, inference, evals, and entitlements."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

Feature = Literal[
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
]
ScopeKind = Literal["user", "workspace", "organization", "global"]
SyncOperation = Literal["upsert", "delete"]
InferenceRole = Literal["system", "user", "assistant", "tool"]


@dataclass(slots=True)
class Scope:
    """Identifies the tenant or visibility boundary for a playbook."""

    kind: ScopeKind
    id: str | None = None


@dataclass(slots=True)
class PlaybookRecord:
    """Portable playbook payload that can be stored locally or in the cloud."""

    id: str
    name: str
    content: str
    scope: Scope
    description: str | None = None
    version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SyncEvent:
    """Represents one synchronization change for a shared domain object."""

    id: str
    entity_type: str
    entity_id: str
    operation: SyncOperation
    payload: dict[str, Any] | None = None
    occurred_at: datetime | None = None


@dataclass(slots=True)
class SyncBatch:
    """Cursor-based sync response that works for local no-op and cloud backends."""

    events: Sequence[SyncEvent]
    next_cursor: str | None = None


@dataclass(slots=True)
class InferenceMessage:
    """Normalized chat-style inference message."""

    role: InferenceRole
    content: str
    name: str | None = None


@dataclass(slots=True)
class TokenUsage:
    """Token accounting returned by an inference backend when available."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(slots=True)
class ModelRequest:
    """Portable inference request for either direct-provider or managed gateways."""

    model: str
    messages: Sequence[InferenceMessage]
    max_tokens: int | None = None
    temperature: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ModelResponse:
    """Portable inference response shape shared by local and hosted runtimes."""

    model: str
    output_text: str
    finish_reason: str | None = None
    usage: TokenUsage | None = None
    raw_response: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EvalCase:
    """One evaluation example for a runner implementation."""

    id: str
    prompt: str
    expected_output: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EvalSpec:
    """Batch evaluation request that can target a local or hosted runner."""

    id: str
    cases: Sequence[EvalCase]
    metric: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EvalCaseResult:
    """Per-case evaluation result detail."""

    case_id: str
    passed: bool
    actual_output: str | None = None
    score: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EvalResult:
    """Aggregate evaluation output shared by local and cloud runners."""

    spec_id: str
    case_results: Sequence[EvalCaseResult]
    passed: bool
    score: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class PlaybookStore(Protocol):
    async def get(self, id: str) -> PlaybookRecord | None:
        """Load a playbook by id."""

    async def put(self, playbook: PlaybookRecord) -> None:
        """Persist or update a playbook."""

    async def list(self, scope: Scope) -> Sequence[PlaybookRecord]:
        """List playbooks visible within the provided scope."""


@runtime_checkable
class SyncBackend(Protocol):
    async def push(self, events: Sequence[SyncEvent]) -> None:
        """Push a sequence of local changes."""

    async def pull(self, cursor: str | None = None) -> SyncBatch:
        """Pull changes newer than the provided cursor."""


@runtime_checkable
class InferenceGateway(Protocol):
    async def call(self, request: ModelRequest) -> ModelResponse:
        """Execute one model request."""


@runtime_checkable
class EvalRunner(Protocol):
    async def run(self, spec: EvalSpec) -> EvalResult:
        """Run an evaluation spec and return aggregate results."""


@runtime_checkable
class Entitlements(Protocol):
    async def can(self, feature: Feature) -> bool:
        """Return whether the requested feature is enabled for the caller."""


__all__ = [
    "Entitlements",
    "EvalCase",
    "EvalCaseResult",
    "EvalResult",
    "EvalRunner",
    "EvalSpec",
    "Feature",
    "InferenceGateway",
    "InferenceMessage",
    "InferenceRole",
    "ModelRequest",
    "ModelResponse",
    "PlaybookRecord",
    "PlaybookStore",
    "Scope",
    "ScopeKind",
    "SyncBackend",
    "SyncBatch",
    "SyncEvent",
    "SyncOperation",
    "TokenUsage",
]
