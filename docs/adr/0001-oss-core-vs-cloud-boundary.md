# ADR 0001: OSS/Core Versus Cloud Boundary

- Status: Accepted
- Date: 2026-03-16

## Context

`DAN-16` requires an architecture decision record that makes the ACE OSS/core
versus cloud boundary explicit.

The requested primary source, `docs/ACE_Product_Spec_Next_Iteration.md`, is not
present in this repository checkout or its tracked history. To keep this ADR
grounded in the current repo, it uses the closest next-iteration planning and
architecture sources that do exist:

- `docs/next_iteration_working_stream.md`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/IMPLENTATION_PLAN_CRITIQUES.md`
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/SELF_HOSTED_DEPLOYMENT.md`
- `ace_core/README.md`

Those documents consistently describe ACE as:

- an open-source product with self-hosting support,
- a layered codebase split between `ace_core/` and `ace_platform/`, and
- a hosted service that operates the same product in a managed cloud
  environment.

The ambiguity this ADR resolves is not "which repo is public?" but "where does
the private cloud boundary begin when the product code is open?"

## Decision

ACE will keep the product code and self-hostable system definition public in
this repository, while treating the managed cloud runtime as the private
boundary.

This means:

1. All reusable product code required to build, run, extend, or self-host ACE
   remains public.
2. Private cloud concerns begin at the operated service layer: secrets, managed
   infrastructure, tenant data, billing state, and operator-only workflows.
3. ACE does not rely on a separate closed-source application tier to define the
   hosted offering. The hosted product's differentiation comes from operations,
   convenience, reliability, and managed service delivery, not from withholding
   the core code.

## Boundary Definition

### Public OSS/Core Surface

The following assets are public and should continue to live in the open
repository:

| Public asset | Why it is public |
| --- | --- |
| `ace_core/` | This is the reusable ACE framework and upstream core logic. |
| `ace_platform/` | This is the hosted platform implementation layer described in the implementation plan and architecture docs. |
| `web/` and `docs-site/` | Product-facing UI and documentation source are part of the self-hostable system definition. |
| `playbooks/`, `tests/`, `docs/`, deployment manifests, and local dev scripts | Operators need these assets to understand, validate, and self-host the platform. |
| Optional integrations such as billing or provider hooks when implemented in product code | These are product capabilities, even when a given deployment leaves them disabled. |

In practical terms, ACE's public boundary is "everything needed to understand
and run the product from source."

### Private Cloud Surface

The following assets and responsibilities stay private to the hosted service
operator:

| Private concern | Why it is private |
| --- | --- |
| Production secrets and credentials (`OPENAI_API_KEY`, OAuth secrets, JWT/session secrets, Stripe secrets, internal tokens) | Exposing them would compromise tenants and external integrations. |
| Managed cloud infrastructure and environment configuration for the hosted service | These are operator-managed deployment details, not reusable product IP. |
| Hosted tenant data: user accounts, API keys, playbooks, versions, outcomes, evolution jobs, usage records, and billing records in the operated environment | This is customer data and operational state, not open product code. |
| Platform-managed provider usage, rate limits, abuse controls, monitoring, alerting, backups, and incident procedures | These are operator-only capabilities needed to run the SaaS safely. |
| Internal admin workflows or support tooling built only to operate the hosted environment | These exist to manage the service, not to define the core product boundary. |

The cloud boundary therefore starts at "running ACE for shared tenants," not at
"writing ACE as software."

## Rationale

This boundary follows the repo's current architecture and delivery posture:

- `README.md` presents ACE as both open-source software and an immediately
  available hosted service.
- `docs/ARCHITECTURE.md` separates `ace_core/` from `ace_platform/`, but keeps
  both inside the same product tree.
- `docs/SELF_HOSTED_DEPLOYMENT.md` documents how a third party can run the full
  stack, which only works if the runtime code remains public.
- `docs/IMPLEMENTATION_PLAN.md` and
  `docs/IMPLENTATION_PLAN_CRITIQUES.md` describe a hosted SaaS posture, while
  still calling for self-host friendliness, optional billing, and optional
  per-user keys.
- `docs/next_iteration_working_stream.md` keeps split-specific work inside the
  repository rather than implying a closed cloud-only codebase.

Keeping the code public while keeping operations private is the only boundary
that matches all of those documents at once.

## Consequences

### What this enables

- Contributors and self-hosters can inspect the full product implementation.
- Hosted and self-hosted deployments can share the same codebase and docs.
- Architectural decisions about `ace_core/` versus `ace_platform/` stay visible
  and reviewable in the open.

### What this requires

- New product behavior should default to landing in the public repository unless
  it would expose secrets or operator-only controls.
- Cloud-only features should be framed as operational policy or managed-service
  configuration whenever possible, not as hidden product logic.
- Documentation should keep distinguishing between "available in the open
  product" and "operated by the hosted service."

### What remains intentionally private

- Hosted environment values, customer data, production telemetry, and internal
  operator procedures.
- Any support or admin tooling that exists only to run the managed service.

## Source Alignment

This ADR follows the accessible next-iteration materials in the repository and
documents one explicit caveat: the ticket-requested source file,
`docs/ACE_Product_Spec_Next_Iteration.md`, is unavailable in this checkout.

Because that file is missing, this ADR does not claim line-by-line alignment
with an unavailable product spec. Instead, it aligns to the currently tracked
planning and architecture documents listed in the Context section above.
