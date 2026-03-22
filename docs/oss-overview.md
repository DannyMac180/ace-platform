# ACE OSS Overview

ACE is moving toward a clean split between a useful public OSS runtime and
hosted cloud services operated by ACE.

This repository is still in the middle of that extraction, so this document
answers three questions directly:

1. What is open-source OSS today?
2. What is hosted/private cloud value?
3. Where should a new user start?

## Product Packaging

| Offer | Primary value |
| --- | --- |
| **ACE OSS** | Local-first playbook engine and self-managed runtime |
| **ACE Cloud Personal** | Hosted convenience for one user |
| **ACE Cloud Team** | Hosted collaboration, shared workflows, and governance |
| **ACE Enterprise** | Private deployment and enterprise controls |

This follows the product spec in
[`docs/ACE_Product_Spec_Next_Iteration.md`](./ACE_Product_Spec_Next_Iteration.md)
and the accepted boundary in
[`docs/adr/0001-oss-core-vs-cloud-boundary.md`](./adr/0001-oss-core-vs-cloud-boundary.md).

## What Is Public OSS Today

These capabilities belong on the public side of the boundary and are intended
to remain usable without ACE-operated cloud services:

| Public capability | Current repo mapping | Notes |
| --- | --- | --- |
| Core ACE engine and domain logic | `packages/ace-core/`, `ace_core/` | `packages/ace-core/` is the extracted package; `ace_core/` remains during the transition |
| Local CLI and project bootstrap flows | `ace_platform/cli.py` | Supports local init, doctor, benchmark, import, and export flows |
| Local/self-managed API and MCP runtime | `ace_platform/api/main.py`, `ace_platform/mcp/` | Local runtime entrypoints remain in `ace_platform/` until further extraction |
| Public starter content and portability assets | `playbooks/`, docs, tests | Supports local usage, import/export, and examples |

If a single self-managed user can reasonably run the capability with their own
infrastructure and model credentials, it belongs on the public side.

## What Is Hosted Or Private Cloud Value

These capabilities define hosted value and are not part of the OSS happy path,
even if some implementation still lives in this repository during the
transition:

- Hosted auth and session management
- Billing and subscription enforcement
- Workspace membership, entitlements, and seat management
- Cloud sync, backups, and restore
- Hosted eval workers and managed job execution
- Managed inference gateway and usage metering
- Team workflows such as shared registries, approvals, RBAC, and audit trails
- Cloud dashboard experiences tied to those hosted services

The important rule is that premium value comes from ACE-operated server-side
services, not from hiding a local feature behind a license check.

## Repo Layout Today

Folder names are not yet the whole story. Use this repo map as the current
guide:

| Path | Classification | Why |
| --- | --- | --- |
| `packages/ace-core/` | Public OSS | Extracted shared engine package |
| `ace_core/` | Public OSS (legacy mirror) | Older core tree retained while extraction continues |
| `ace_platform/` | Mixed transition area | Contains public runtime entrypoints plus temporary compatibility bridges while the split completes |
| `web/` | Hosted/cloud-oriented shim | Public marker directory that points hosted dashboard work to `ace-private` |
| `docs/` | Mixed documentation surface | Public docs plus architecture notes describing the split |

## Target Layout

The target package/service layout from the product spec appendix is:

```text
packages/
  ace-core/
  ace-cli/
  ace-local-server/
  ace-mcp/
  ace-protocol/
  ace-provider-openai/
  ace-provider-anthropic/
examples/
  starter-project/
  benchmark-demo/
docs/
  oss-overview.md
  local-quickstart.md

services/
  auth/
  workspaces/
  entitlements/
  sync-api/
  eval-workers/
  billing/
  inference-gateway/
apps/
  cloud-dashboard/
```

The current repository has not finished that extraction yet. Until it does, use
the capability-based boundary above rather than assuming every current folder is
already in its final home.

## Hosted Implementation Canonical Home

The hosted control-plane implementation is now expected to live in the private
companion repo, `ace-private`.

Use `ace-private` for:

- hosted dashboard/frontend implementation
- Fly deploy automation and app configs
- operator-only secrets/bootstrap scripts
- hosted personal-workspace migration and backup automation

The public repo keeps OSS/core docs, examples, packages, and local/self-managed
development paths. Any remaining public bridges to hosted behavior should be
treated as compatibility shims, not the canonical implementation.

## Where To Start

- If you want the fastest hosted experience, use [docs/QUICKSTART.md](./QUICKSTART.md).
- If you want the open-source local path, use [docs/local-quickstart.md](./local-quickstart.md).
- If you want to deploy the full stack yourself, use [docs/SELF_HOSTED_DEPLOYMENT.md](./SELF_HOSTED_DEPLOYMENT.md).
