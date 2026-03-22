# Self-Hosted Deployment Guide

This public repository no longer carries the canonical hosted control-plane
implementation for ACE Cloud. After the hosted cutover, the cloud dashboard,
Fly deploy configs, operator secrets/bootstrap scripts, and other hosted-only
control-plane assets now live in `ace-private`.

Use this repo for:

- `ACE OSS` packages and examples
- local/self-managed development against the public runtime
- infrastructure helpers such as local Postgres/Redis via `docker compose`

Use `ace-private` for:

- hosted/private deployment implementation
- hosted dashboard work
- operator-only deploy and secret management automation
- hosted workspace migration and backup operations

## Public Repo Quickstart

If you want the public self-managed path, read these in order:

1. [OSS overview](./oss-overview.md)
2. [Local quickstart](./local-quickstart.md)
3. [Environment variable reference](./ENVIRONMENT_VARIABLES.md)

For the public repo's local infrastructure bootstrap:

```bash
git clone https://github.com/DannyMac180/ace-platform.git
cd ace-platform
cp .env.example .env
docker compose up -d postgres redis
source venv/bin/activate && alembic upgrade head
```

That keeps the OSS/local workflow intact without claiming this repo is the
deployable source of truth for ACE-hosted control-plane services.

## Hosted/Private Deployment Boundary

If your task needs any of the following, switch to `ace-private` instead of
continuing in this public repo:

- hosted dashboard/frontend implementation
- Fly staging or production deployment automation
- operator-only secrets/bootstrap scripts
- hosted personal-workspace migration or backup automation

This boundary follows:

- [ACE Product Spec Next Iteration](./ACE_Product_Spec_Next_Iteration.md)
- [Next Iteration Working Stream](./next_iteration_working_stream.md)
- [ADR 0001: OSS/Core Versus Cloud Boundary](./adr/0001-oss-core-vs-cloud-boundary.md)
