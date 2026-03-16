# ADR 0001: OSS/Core Versus Cloud Boundary

**Status:** Accepted  
**Date:** 2026-03-16  
**Owners:** ACE Platform

## Context

`docs/ACE_Product_Spec_Next_Iteration.md` makes the product direction explicit: ACE should become a local-first, open-source playbook engine with a hosted cloud product for convenience, collaboration, and governance. The same spec also sets the core rule for monetization and architecture:

- the OSS version must remain genuinely useful
- premium value must depend on private services ACE operates
- the security boundary is the server boundary
- the next-iteration work starts by documenting the OSS/core versus cloud split in an ADR (`Section 9`, `Epic 0`, `E0-T2`)

The spec is also explicit about what belongs on each side of the boundary:

- `Decision 3` says the public side includes the local engine and local runtime
- `Decision 3` says the private side includes the cloud control plane and managed services
- `Appendix: Suggested Package and Service Layout` gives the target package split for public packages and private cloud services

Today this repository is still a mixed codebase. Public runtime code, self-hosting assets, and cloud-specific code are not yet fully extracted into separate top-level packages. This ADR defines the boundary now so future work can move code in the right direction without product or licensing ambiguity.

## Decision

ACE will be developed as one product with two classifications:

1. **Public OSS/core code**: the code required to run ACE locally or self-managed without ACE-operated cloud services.
2. **Private cloud services**: the server-side control plane and managed services that create durable hosted value for ACE Cloud Personal, Cloud Team, and Enterprise deployments.

The classification is based on capability, not the current folder name. Until the extraction work in the spec is complete, some public and private concerns may temporarily live in the same repository, but new work must still honor the boundary defined here.

## What Is Public

The following code and assets are public OSS/core:

| Public scope | Why it is public | Current repo mapping | Target shape from the spec |
| --- | --- | --- | --- |
| Core playbook engine and domain logic | This is the product's local-first engine and must stay useful without a cloud account | `ace_core/` | `packages/ace-core/` |
| Local API, CLI, and MCP runtime | `Decision 3` explicitly includes the local runtime, local API/CLI, and local MCP server in OSS | Public runtime code that currently lives in `ace_platform/` plus local tooling documented in `README.md` | `packages/ace-cli/`, `packages/ace-local-server/`, `packages/ace-mcp/` |
| Local storage and execution paths | A single user must be able to run ACE with local persistence and direct model access | Self-hosted/local execution paths, background jobs, and storage code used without ACE-operated services | Local implementations behind the public runtime |
| Provider adapters and protocol contracts | Users must be able to bring their own model keys and integrate providers without cloud lock-in | Adapter and protocol code in the public runtime | `packages/ace-protocol/`, provider packages |
| Import/export formats and portability tooling | The spec requires users to move artifacts between local and hosted contexts | Import/export code, playbook files, and starter content such as `playbooks/` | Public file formats and examples |
| Self-hosting assets and docs | Self-managed installation is part of the OSS story | `README.md`, `docs/SELF_HOSTED_DEPLOYMENT.md`, Docker assets, public docs, and tests | `docs/oss-overview.md`, `docs/local-quickstart.md`, public deployment docs |

Public code must remain sufficient for a single user to install, configure, run, persist, and use ACE locally with their own infrastructure and model credentials.

## What Is Private

The following services are private cloud-side services and must not be required for the OSS/core happy path:

| Private scope | Why it is private | Target shape from the spec |
| --- | --- | --- |
| Hosted auth and session management | Managed identity is a hosted convenience and part of the control plane | `services/auth/` |
| Workspace, membership, and entitlement services | Plans, seats, and premium access must be enforced server-side | `services/workspaces/`, `services/entitlements/` |
| Billing and subscription systems | Monetization depends on private service enforcement, not hidden client checks | `services/billing/` |
| Cloud sync, backups, and restore | Cross-device continuity is a hosted value layer | `services/sync-api/` plus backup/restore systems |
| Hosted eval workers and managed job execution | Managed background execution is part of the paid hosted experience | `services/eval-workers/` |
| Managed inference gateway and usage metering | ACE-operated model routing and usage accounting are private service value | `services/inference-gateway/` |
| Team collaboration and governance features | Shared registry, approvals, RBAC, audit logs, and admin workflows are hosted/team value | `apps/cloud-dashboard/` plus private control-plane services |
| Operator-only automation, secrets, and production runbooks | These are required to operate the cloud safely and are not part of the OSS product | Private operational assets outside the public runtime |

Private cloud services may be operated by ACE for hosted plans or delivered under commercial terms for enterprise/private deployments. That deployment option does not make the control-plane code part of the OSS/core boundary.

## Boundary Rules

The boundary will be enforced by the following rules:

1. OSS/core features must work without calling ACE-operated private services.
2. Cloud features may depend on OSS/core modules, but OSS/core modules must not depend on billing, entitlements, hosted auth, or other cloud-only services.
3. Premium value must come from server-side capabilities, data custody, and managed operations, not from hiding UI code or adding local license gates.
4. Interfaces shared between local and cloud implementations should remain public so both sides can implement the same contracts cleanly.
5. When a feature is ambiguous, the deciding question is: "Can a single self-managed user reasonably run this without ACE operating a server for them?" If yes, it belongs on the public side. If no, it belongs on the private cloud side.

## Alignment With the Product Spec

This ADR follows the spec directly in the following ways:

- It adopts `Decision 3` by making the local engine and local runtime public while keeping the cloud control plane private.
- It follows the packaging table by preserving a meaningful OSS product and reserving hosted convenience, collaboration, and governance for cloud offerings.
- It follows `Guiding Principle 4` by treating the server boundary as the security and premium-feature boundary.
- It satisfies `Section 9`, `Epic 0`, `E0-T2` by explicitly documenting what is public, what is private, and why.
- It uses the appendix package/service layout as the target-state boundary for future extraction work.

## Current-State Divergence

The repo has not finished the extraction described in the spec yet. That creates one intentional short-term divergence:

- **Current state:** some public runtime code and cloud-oriented code still coexist in `ace_platform/` and the current web app structure.
- **Target state:** the public runtime is extracted into the public packages listed in the spec appendix, while cloud-only services live behind private service and dashboard boundaries.

This is an implementation-stage divergence, not a product-strategy divergence. Until the extraction lands, code review should classify new modules by the boundary in this ADR rather than by where they happen to live today.

## Consequences

- Future extraction work must keep `ace_core` and the local runtime free of private cloud dependencies.
- Cloud Personal, Cloud Team, and Enterprise value should be built by adding private services on top of the OSS/core, not by weakening the OSS/core.
- Documentation must explain the split clearly so users understand the difference between OSS, hosted personal, team, and enterprise offerings.
- Self-hosting remains part of the public story for the local/runtime layer, while managed cloud operations and commercial governance remain private.
