# Core Interface Contracts

`ace_core.contracts` defines the public OSS/core contracts for storage, sync,
inference, evals, and entitlements.

The package root re-exports the contract surface as well, so callers can choose
either `ace_core.contracts` or `ace_core` as the import path while the
repository settles the longer-term `ace-core` package split.

This module exists to keep the boundary from
[ADR 0001](adr/0001-oss-core-vs-cloud-boundary.md) explicit in code:
local and cloud implementations can satisfy the same interface set without
making `ace_core` depend on hosted-only services.

## Design goals

- Keep the contracts public and implementation-agnostic.
- Use structural typing (`Protocol`) so local and cloud backends do not need a
  shared inheritance tree.
- Keep request and response payloads small and portable.
- Avoid embedding billing, auth, or other cloud-only dependencies in the core
  package.

## Contract surface

- `PlaybookStore`
  - `get(id)` loads one `PlaybookRecord`
  - `put(playbook)` persists or updates one record
  - `list(scope)` returns playbooks visible in a `Scope`
- `SyncBackend`
  - `push(events)` accepts ordered `SyncEvent` objects
  - `pull(cursor)` returns a `SyncBatch` with `next_cursor`
- `InferenceGateway`
  - `call(request)` accepts a portable `ModelRequest`
  - returns a normalized `ModelResponse`
  - `ModelRequest.inference_config` can explicitly select either the BYO path
    or the ACE-managed path
- `EvalRunner`
  - `run(spec)` executes an `EvalSpec`
  - returns an aggregate `EvalResult`
- `Entitlements`
  - `can(feature)` checks a `Feature` from the product spec entitlement catalog

## Shared domain types

The dataclasses in `ace_core.contracts` are intentionally narrow:

- `Scope` and `PlaybookRecord` cover storage visibility and portability.
- `SyncEvent` and `SyncBatch` support both no-op/local export sync and hosted
  cursor-based sync APIs.
- `InferenceMessage`, `ModelRequest`, `ModelResponse`, and `TokenUsage`
  normalize direct-provider and managed-gateway inference paths.
- `BYOProviderConfig` carries caller-managed routing data such as provider name,
  API key, base URL, and organization.
- `ManagedProviderConfig` carries ACE-managed routing data such as provider
  name, workspace scope, or a managed gateway identifier.
- `EvalCase`, `EvalSpec`, `EvalCaseResult`, and `EvalResult` let local and
  hosted eval runners report the same shape.
- `Feature` enumerates the entitlement flags from Section 8 of
  `ACE_Product_Spec_Next_Iteration.md`.

## Expected implementation mapping

Local implementations can satisfy the contracts with:

- filesystem or SQLite backed `PlaybookStore`
- a no-op or export-oriented `SyncBackend`
- direct provider `InferenceGateway`
- a local `EvalRunner`
- static or config-based `Entitlements`

`ace_core.local.RoutedInferenceGateway` can dispatch a request to either a
direct BYO gateway or a managed gateway based on `request.inference_config`.
`DirectInferenceGateway` remains the BYO implementation and raises a clear
error if a managed-only config is sent to it directly.

The current production local adapter surface lives in `ace_core.local` and is
mirrored in `packages/ace-core/src/ace_core/` for the extracted package path.

Cloud implementations can satisfy the same contracts with:

- API or database backed `PlaybookStore`
- hosted push/pull `SyncBackend`
- managed `InferenceGateway`
- queued or remote `EvalRunner`
- workspace-aware `Entitlements`

## Validation strategy

`tests/test_core_interfaces.py` uses both local and cloud-style test doubles to
prove the same protocol surface works for both deployment modes.
