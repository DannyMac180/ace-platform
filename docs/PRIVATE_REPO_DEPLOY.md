# `ace-private` Deployment Runbook

This runbook is the source of truth for staging and production hosted deploys
that run from the private repository. It is intentionally cloud-only
operational guidance and is not part of the OSS/self-hosted contract described
in [ADR 0001](./adr/0001-oss-core-vs-cloud-boundary.md).

## Workflow Inventory

The private repo should carry these GitHub Actions workflows and protection
targets:

| File | Purpose | Trigger |
| --- | --- | --- |
| `.github/workflows/ci.yml` | Required PR/main validation for backend, frontend, and deployable artifacts | `pull_request`, `push`, `merge_group` |
| `.github/workflows/staging.yml` | Automatic staging deploy plus staging smoke checks | `push` to `main`, manual dispatch |
| `.github/workflows/production.yml` | Manual production deploy or rollback with environment protection | Manual dispatch |

Required branch checks for `main`:

- `Backend Validation`
- `Frontend Validation`
- `Backend Release Artifact`
- `Frontend Release Artifact`

GitHub protection settings for the private repo:

- Protect `main` with pull requests required, branch up-to-date required, and
  the four checks above marked as required.
- Disable direct pushes to `main` except for administrators if your release
  policy requires emergency bypass.
- Add a `staging` environment with deploy branches restricted to `main`.
- Add a `production` environment with deploy branches restricted to `main`,
  required reviewers enabled, and self-approval disabled.

GitHub environment rules are documented in the GitHub deployments/environments
reference:
https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments

## Fly App Topology

Hosted ACE currently deploys two Fly apps per environment:

| Environment | Backend app | Frontend app | Notes |
| --- | --- | --- | --- |
| Staging | `ace-platform-staging` | `ace-platform-web-staging` | Backend app serves API plus worker/beat process groups |
| Production | `ace-platform` | `ace-platform-web` | Backend app serves API plus worker/beat process groups |

The backend Fly configs are `fly.staging.toml` and `fly.toml`.
The frontend Fly configs are `web/fly.staging.toml` and `web/fly.toml`.

Every deploy now labels Fly images with the Git commit SHA via
`--image-label $GITHUB_SHA`. That gives the private repo a stable rollback
handle without depending on the public repo state.

## Secret And Runtime Parity

### GitHub secrets and environment protections

GitHub only needs one deploy secret per environment:

| Scope | Name | Purpose |
| --- | --- | --- |
| `staging` environment secret | `FLY_API_TOKEN` | Allows the staging deploy workflow to call `flyctl` |
| `staging` environment secret | `FRONTEND_VITE_SENTRY_DSN` | Optional build-time Sentry DSN for the dashboard |
| `production` environment secret | `FLY_API_TOKEN` | Allows the protected production deploy/rollback workflow to call `flyctl` |
| `production` environment secret | `FRONTEND_VITE_SENTRY_DSN` | Optional build-time Sentry DSN for the dashboard |
| Repository secret | `CODECOV_TOKEN` | Optional coverage upload from `ci.yml` |

### Fly runtime settings

The Fly apps need these settings in addition to the GitHub deploy token. Values
come from either tracked `fly*.toml` files, Fly secrets, or Fly-managed
attachments.

| Category | Variable | Staging source | Production source |
| --- | --- | --- | --- |
| Database | `DATABASE_URL` | Fly Postgres attachment | Fly Postgres attachment |
| Database | `DATABASE_URL_ASYNC` | Fly secret or auto-derived | Fly secret or auto-derived |
| Redis | `REDIS_URL` | Fly Redis attachment | Fly Redis attachment |
| LLM | `OPENAI_API_KEY` | Fly secret | Fly secret |
| LLM | `ANTHROPIC_API_KEY` | Fly secret when enabled | Fly secret when enabled |
| Auth | `JWT_SECRET_KEY` | Fly secret | Fly secret |
| Auth | `SESSION_SECRET_KEY` | Fly secret | Fly secret |
| Auth | `GOOGLE_OAUTH_CLIENT_ID` | Fly secret when enabled | Fly secret when enabled |
| Auth | `GOOGLE_OAUTH_CLIENT_SECRET` | Fly secret when enabled | Fly secret when enabled |
| Auth | `GITHUB_OAUTH_CLIENT_ID` | Fly secret when enabled | Fly secret when enabled |
| Auth | `GITHUB_OAUTH_CLIENT_SECRET` | Fly secret when enabled | Fly secret when enabled |
| Auth | `FRONTEND_URL` | `fly.staging.toml` | `fly.toml` |
| Auth | `OAUTH_REDIRECT_BASE_URL` | `fly.staging.toml` | `fly.toml` |
| Auth | `SESSION_COOKIE_SECURE` | `fly.staging.toml` | `fly.toml` |
| Auth | `SESSION_COOKIE_SAMESITE` | `fly.staging.toml` | `fly.toml` |
| Auth | `SESSION_COOKIE_DOMAIN` | leave unset unless a shared staging apex exists | `fly.toml` |
| Web/API | `CORS_ORIGINS` | `fly.staging.toml` | `fly.toml` |
| Web/API | `DOCS_URL` | `fly.staging.toml` | `fly.toml` |
| Billing | `BILLING_ENABLED` | `fly.staging.toml` | `fly.toml` |
| Billing | `STRIPE_SECRET_KEY` | Fly secret when billing is enabled | Fly secret when billing is enabled |
| Billing | `STRIPE_WEBHOOK_SECRET` | Fly secret when billing is enabled | Fly secret when billing is enabled |
| Email | `RESEND_API_KEY` | Fly secret when email is enabled | Fly secret when email is enabled |
| Email | `EMAIL_FROM_ADDRESS` | `fly.staging.toml` | `fly.toml` |
| Email | `EMAIL_FROM_NAME` | `fly.staging.toml` | `fly.toml` |
| Email | `SUPPORT_EMAIL` | `fly.staging.toml` | `fly.toml` |
| Alerts | `ADMIN_ALERT_EMAIL` | Fly secret when alerts are enabled | Fly secret when alerts are enabled |
| Alerts | `ADMIN_ALERT_SLACK_WEBHOOK` | Fly secret when alerts are enabled | Fly secret when alerts are enabled |
| Observability | `SENTRY_DSN` | Fly secret when Sentry is enabled | Fly secret when Sentry is enabled |
| Observability | `SENTRY_RELEASE` / `SENTRY_RELEASE_*` | deploy-time image label or Fly secret override | deploy-time image label or Fly secret override |
| Observability | `SENTRY_TRACES_SAMPLE_RATE*` | `fly.staging.toml` plus optional Fly secret overrides | `fly.toml` plus optional Fly secret overrides |
| Observability | `SENTRY_PROFILES_SAMPLE_RATE*` | `fly.staging.toml` plus optional Fly secret overrides | `fly.toml` plus optional Fly secret overrides |
| Observability | `SENTRY_TRANSPORT_QUEUE_SIZE*` | `fly.staging.toml` plus optional Fly secret overrides | `fly.toml` plus optional Fly secret overrides |
| Metrics | `METRICS_AUTH_TOKEN` | Fly secret when `/metrics` is protected | Fly secret when `/metrics` is protected |
| Dashboard build | `VITE_API_URL` | workflow build arg and `web/fly.staging.toml` | workflow build arg and `web/fly.toml` |
| Dashboard build | `VITE_DOCS_URL` | workflow build arg and `web/fly.staging.toml` | workflow build arg and `web/fly.toml` |
| Dashboard build | `VITE_SENTRY_DSN` | GitHub environment secret `FRONTEND_VITE_SENTRY_DSN` or blank | GitHub environment secret `FRONTEND_VITE_SENTRY_DSN` or blank |
| Dashboard build | `VITE_SENTRY_RELEASE` | workflow build arg from commit SHA | workflow build arg from commit SHA |
| Dashboard build | `VITE_SENTRY_ENVIRONMENT` | workflow build arg = `staging` | workflow build arg = `production` |
| Dashboard build | `VITE_SENTRY_TRACES_SAMPLE_RATE` | workflow build arg = `0.0` | workflow build arg = `0.05` |

### Provisioning checklist

Run these from the private repo root after authenticating `flyctl`:

```bash
# Staging
fly secrets set -a ace-platform-staging \
  OPENAI_API_KEY=... \
  JWT_SECRET_KEY=... \
  SESSION_SECRET_KEY=...

# Production
fly secrets set -a ace-platform \
  OPENAI_API_KEY=... \
  JWT_SECRET_KEY=... \
  SESSION_SECRET_KEY=...
```

Add optional OAuth, Stripe, email, Sentry, and alerting secrets in the same
way when those integrations are enabled. Set `FRONTEND_VITE_SENTRY_DSN` as a
GitHub environment secret because the dashboard consumes it at image build time.
`DATABASE_URL` and `REDIS_URL` should come from Fly-managed Postgres/Redis
attachments rather than hand-entered values.

## Deploy Procedure

### Staging

1. Merge to `main` in the private repo.
2. Wait for `CI` to pass and for `.github/workflows/staging.yml` to complete.
3. Confirm backend health at `https://ace-platform-staging.fly.dev/health`.
4. Confirm frontend health at `https://ace-platform-web-staging.fly.dev/`.
5. Confirm the backend app has running `api`, `worker`, and `beat` machines in
   the Fly deploy summary.

### Production

1. Open the `Deploy to Production` workflow in GitHub Actions.
2. Select `action=deploy`.
3. Type `deploy` in the confirmation input.
4. Wait for protected-environment approval and deployment completion.
5. Confirm backend health at `https://aceagent.io/health`.
6. Confirm frontend health at `https://app.aceagent.io/`.

## Rollback Procedure

Fly’s official rollback guidance is to redeploy a previously shipped image:
https://fly.io/docs/blueprints/rollback-guide/

### Manual rollback from GitHub Actions

1. Gather the prior image refs:

```bash
fly releases --app ace-platform --image
fly releases --app ace-platform-web --image
```

2. Open the `Deploy to Production` workflow in GitHub Actions.
3. Select `action=rollback`.
4. Type `rollback` in the confirmation input.
5. Paste the exact backend and frontend image refs from step 1.
6. Approve the protected `production` environment if required.
7. Re-check backend/frontend health, confirm the backend app has running `api`,
   `worker`, and `beat` machines, and inspect `fly status` / `fly logs`.

The production rollback workflow skips Fly's release command for the backend
image so an older container can be restored even if the database has already
advanced past that image's Alembic revision graph.

### CLI rollback from the private repo

```bash
fly deploy --app ace-platform --config fly.toml --image registry.fly.io/ace-platform:<label> --skip-release-command
cd web
fly deploy --app ace-platform-web --config fly.toml --image registry.fly.io/ace-platform-web:<label>
```

Notes:

- Rollbacks only restore the container image. They do not revert database
  schema changes, `fly.toml`, or secret updates.
- Prefer non-destructive migrations so the prior image can still boot after a
  rollback.
