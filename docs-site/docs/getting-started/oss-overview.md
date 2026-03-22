---
sidebar_position: 2
---

# OSS Overview

ACE supports both a hosted cloud product and a local-first OSS path.

Use this guide to decide where to start if you want to stay inside the public,
self-managed side of ACE instead of the hosted dashboard flow.

## Choose Your Starting Point

| Path | Use it when | Start here |
| --- | --- | --- |
| ACE OSS package | You want the ACE engine inside your own Python workflow | [Install the OSS package](./local-quickstart#option-1-install-the-extracted-oss-package) |
| Self-managed local runtime | You want ACE's API, CLI, and MCP runtime on your own machine or infra | [Run the local runtime](./local-quickstart#option-2-run-the-local-ace-runtime) |
| Hosted ACE Cloud | You want the fastest managed setup, sync, and dashboard workflow | [ACE Cloud Quick Start](/docs/getting-started/quick-start) |

## How ACE Is Packaged

ACE v2 follows a clear split between public OSS/runtime capabilities and
ACE-operated cloud services.

| Offer | Primary value |
| --- | --- |
| **ACE OSS** | Local-first playbook engine and self-managed runtime |
| **ACE Cloud Personal** | Hosted convenience for one user |
| **ACE Cloud Team** | Hosted collaboration, shared workflows, and governance |
| **ACE Enterprise** | Private deployment and enterprise controls |

This docs-site path follows the product direction in the ACE v2 product spec
and the accepted OSS/core-versus-cloud boundary ADR: the OSS path should remain
meaningfully useful on its own, while hosted value comes from ACE-operated
services.

## What Counts As Public OSS Today

These capabilities belong on the public side and should remain usable without
ACE-operated cloud services:

| Public capability | Current repo mapping | Why it matters |
| --- | --- | --- |
| Core ACE engine and domain logic | `packages/ace-core/`, `ace_core/` | Lets you embed ACE in your own local workflows |
| Local CLI and bootstrap flows | `ace_platform/cli.py` | Supports local init, doctor, benchmark, import, and export workflows |
| Local API and MCP runtime | `ace_platform/api/main.py`, `ace_platform/mcp/` | Lets you run ACE services yourself |
| Public starter content and portability assets | `playbooks/`, docs, tests | Keeps local usage, examples, and import/export flows portable |

If a single self-managed user can reasonably run the capability with their own
infrastructure and model credentials, it belongs on the public side.

## What Hosted ACE Adds

Hosted ACE is intentionally different from the OSS/local path.

| Capability | OSS package / self-managed runtime | Hosted ACE |
| --- | --- | --- |
| Core engine | Yes | Yes |
| Local API, CLI, MCP | Yes | Optional |
| Bring your own model keys | Yes | Yes |
| Hosted auth and sessions | No | Yes |
| Billing and entitlements | No | Yes |
| Cloud sync and backups | No | Yes |
| Managed inference gateway | No | Yes |
| Team collaboration and governance | No | Yes |

The important rule is that premium value comes from ACE-operated server-side
services, not from hiding local features behind license checks.

## What The Repo Looks Like Today

The package split is still in progress, so current folder names are a transition
state rather than the final product boundary.

| Path | Classification | Notes |
| --- | --- | --- |
| `packages/ace-core/` | Public OSS | Extracted shared engine package |
| `ace_core/` | Public OSS (legacy mirror) | Older core tree retained during extraction |
| `ace_platform/` | Mixed transition area | Local runtime entrypoints and cloud-oriented services still coexist here |
| `web/` | Hosted/cloud-oriented app surface | Dashboard frontend for managed workflows |

For user onboarding, the important distinction is capability, not the temporary
repo layout.

## Where To Go Next

- If you want the public/local path, continue to the [Local Quickstart](./local-quickstart).
- If you want the fastest managed experience, use the [ACE Cloud Quick Start](/docs/getting-started/quick-start).
