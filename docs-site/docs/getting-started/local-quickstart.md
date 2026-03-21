---
sidebar_position: 3
---

# Local Quickstart

This is the fastest docs-site path for a user who wants to start with ACE
without using the hosted cloud service.

Use this guide if you want one of these local options:

- the extracted OSS engine package in your own Python project
- the self-managed ACE API, CLI, and MCP runtime from this repository

If you want the managed product instead, use the
[ACE Cloud Quick Start](/docs/getting-started/quick-start).

## Choose Your Local Path

| Path | Use it when | What you get |
| --- | --- | --- |
| `packages/ace-core` | You want the ACE engine/library in your own Python workflow | Public OSS package with the core playbook engine |
| Local runtime from this repo | You want ACE's local API, CLI, and MCP server running on your machine | Self-managed runtime using this repository plus your own infra |

## Option 1: Install The Extracted OSS Package

This is the smallest public surface in the repo today.

Clone the repository and change into it first so the local package path exists:

```bash
git clone https://github.com/DannyMac180/ace-platform.git
cd ace-platform
python -m venv .venv
source .venv/bin/activate
python -m pip install ./packages/ace-core
python -c "from ace_core import ACE; print(ACE.__name__)"
```

That installs the extracted `ace-core` package directly from the repo and
confirms the public package imports cleanly.

## Option 2: Run The Local ACE Runtime

This path uses the current self-managed runtime that still lives in
`ace_platform/` while the package split continues.

### 1. Clone and install

```bash
git clone https://github.com/DannyMac180/ace-platform.git
cd ace-platform
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

### 2. Configure your local environment

```bash
cp .env.example .env
```

Minimum settings for the local runtime:

```text
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ace_platform
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=sk-...
JWT_SECRET_KEY=replace-me
```

### 3. Start local infrastructure

```bash
docker compose up -d postgres redis
source venv/bin/activate && alembic upgrade head
```

### 4. Start the runtime

Run these in separate shells:

```bash
source venv/bin/activate && uvicorn ace_platform.api.main:app --reload
source venv/bin/activate && python -m ace_platform.mcp.server
source venv/bin/activate && celery -A ace_platform.workers.celery_app worker -l info
```

The API will be available at `http://localhost:8000` and the local MCP server
will be available from the same self-managed codebase.

## What The Local Path Includes

- A public ACE engine package for embedding in your own Python workflow
- A self-managed API, CLI, and MCP runtime that you run with your own infra
- Local persistence, background jobs, and model-provider setup under your control

## What The Local Path Does Not Include

The OSS/self-managed path is intentionally different from hosted ACE:

- no ACE-hosted auth or cloud sessions
- no managed billing or entitlements
- no ACE-operated sync, backups, or restore
- no managed inference gateway
- no ACE-operated team collaboration or governance services

Those remain hosted/private cloud features, even while some transition-stage
code is still colocated in this repository today.

## Related Docs

- [OSS Overview](./oss-overview)
- [ACE Cloud Quick Start](/docs/getting-started/quick-start)
