# ACE Local Quickstart

This is the fastest path for an external user who wants to start with ACE
without using the hosted cloud service.

Use this guide if you want one of these local paths:

- the extracted OSS engine package in your own Python project
- the self-managed ACE API and MCP runtime from this repository

If you want the hosted product instead, start with
[docs/QUICKSTART.md](./QUICKSTART.md).

## Choose Your Local Path

| Path | Use it when | What you get |
| --- | --- | --- |
| `packages/ace-core` | You want the ACE engine/library in your own Python workflow | Public OSS package with the core playbook engine |
| Local runtime from this repo | You want ACE's local CLI and transition-stage self-managed runtime helpers on your machine | Self-managed runtime using this repository plus your own infra |

## Option 1: Install The Extracted OSS Package

This is the smallest public surface in the repo today.

```bash
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

### 2. Configure local environment

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

If you are looking for the hosted dashboard, cloud control-plane deployment
assets, or operator-only automation, those no longer live in this public repo.
Use `ace-private` for hosted/private deployment implementation work.

## What Local OSS Does Not Include

The local OSS/self-managed path is intentionally different from ACE Cloud:

- no ACE-hosted auth or cloud sessions
- no managed billing or entitlements
- no ACE-operated sync/backups
- no managed inference gateway
- no team collaboration/governance services operated by ACE

Those are hosted/private cloud features, even if some transition-stage code is
still colocated in this repository today.

## Related Docs

- [OSS overview](./oss-overview.md)
- [Self-hosted deployment guide](./SELF_HOSTED_DEPLOYMENT.md)
- [Root README](../README.md)
