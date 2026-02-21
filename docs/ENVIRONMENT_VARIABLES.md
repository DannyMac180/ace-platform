# Environment Variables Reference

This document provides a comprehensive reference for all environment variables used by the ACE Platform.

## Quick Reference

| Category | Required | Description |
|----------|----------|-------------|
| [Database](#database) | Yes | PostgreSQL connection |
| [Redis](#redis) | Yes | Task queue and caching |
| [OpenAI](#openai) | Yes | LLM API access |
| [JWT Authentication](#jwt-authentication) | Yes* | Token signing (*must change default in production) |
| [Billing](#billing-stripe) | No | Stripe integration |
| [MCP Server](#mcp-server) | No | Model Context Protocol server |
| [Evolution](#evolution-settings) | No | Playbook evolution tuning |
| [API Server](#api-server) | No | HTTP server configuration |
| [Environment](#environment-settings) | No | Runtime environment |
| [Logging](#logging) | No | Log configuration |
| [Error Tracking](#error-tracking-sentry) | No | Sentry integration |

---

## Database

### DATABASE_URL

PostgreSQL connection string for synchronous database operations (used by Celery workers).

| Property | Value |
|----------|-------|
| Required | Yes |
| Default | `postgresql://postgres:postgres@localhost:5432/ace_platform` |
| Format | `postgresql://user:password@host:port/database` |

**Examples:**
```bash
# Local development
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ace_platform

# Docker Compose
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/ace_platform

# Production (with SSL)
DATABASE_URL=postgresql://user:password@db.example.com:5432/ace_platform?sslmode=require
```

### DATABASE_URL_ASYNC

PostgreSQL connection string for async operations (used by FastAPI and MCP server).

| Property | Value |
|----------|-------|
| Required | No |
| Default | Auto-derived from `DATABASE_URL` |
| Format | `postgresql+asyncpg://user:password@host:port/database` |

**Note:** If not set, this is automatically derived from `DATABASE_URL` by replacing `postgresql://` with `postgresql+asyncpg://`.

---

## Redis

### REDIS_URL

Redis connection string for Celery task queue and rate limiting.

| Property | Value |
|----------|-------|
| Required | Yes |
| Default | `redis://localhost:6379/0` |
| Format | `redis://[:password@]host:port/db` |

**Examples:**
```bash
# Local development
REDIS_URL=redis://localhost:6379/0

# Docker Compose
REDIS_URL=redis://redis:6379/0

# Production with password
REDIS_URL=redis://:mypassword@redis.example.com:6379/0

# Production with TLS
REDIS_URL=rediss://:mypassword@redis.example.com:6380/0
```

---

## OpenAI

### OPENAI_API_KEY

OpenAI API key for LLM calls during playbook evolution.

| Property | Value |
|----------|-------|
| Required | Yes |
| Default | (empty) |
| Format | `sk-...` |

**Example:**
```bash
OPENAI_API_KEY=sk-proj-abc123...
```

**Security:** Never commit this value to version control. Use secrets management in production.

---

## JWT Authentication

### JWT_SECRET_KEY

Secret key used for signing JWT access and refresh tokens.

| Property | Value |
|----------|-------|
| Required | Yes (must change in production) |
| Default | `change-me-in-production` |
| Format | Random string (32+ characters recommended) |

**Example:**
```bash
# Generate a secure key
JWT_SECRET_KEY=$(openssl rand -hex 32)
```

**Security:** Use a strong, random value in production. Rotating this key will invalidate all existing tokens.

### JWT_ALGORITHM

Algorithm used for JWT token signing.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `HS256` |
| Options | `HS256`, `HS384`, `HS512` |

### JWT_ACCESS_TOKEN_EXPIRE_MINUTES

Access token expiration time in minutes.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `30` |
| Range | 1-1440 (1 minute to 24 hours) |

### JWT_REFRESH_TOKEN_EXPIRE_DAYS

Refresh token expiration time in days.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `7` |
| Range | 1-365 |

---

## Billing (Stripe)

Stripe integration is optional and disabled by default.

### BILLING_ENABLED

Enable or disable Stripe billing integration.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `false` |
| Options | `true`, `false` |

**Feature Flag:** When `false`, billing routes remain available, but Stripe-dependent actions return configuration errors until billing is enabled and Stripe keys are set.

### STRIPE_SECRET_KEY

Stripe secret API key.

| Property | Value |
|----------|-------|
| Required | Only if `BILLING_ENABLED=true` |
| Default | (empty) |
| Format | `sk_test_...` or `sk_live_...` |

### STRIPE_WEBHOOK_SECRET

Stripe webhook signing secret for verifying webhook events.

| Property | Value |
|----------|-------|
| Required | Only if `BILLING_ENABLED=true` |
| Default | (empty) |
| Format | `whsec_...` |

**Example configuration for billing:**
```bash
BILLING_ENABLED=true
STRIPE_SECRET_KEY=sk_live_abc123...
STRIPE_WEBHOOK_SECRET=whsec_xyz789...
```

---

## MCP Server

In hosted deployments, the MCP Streamable HTTP endpoint is mounted on the API domain at `/mcp`.
Legacy SSE endpoints (`/mcp/sse` and `/mcp/messages`) remain available through **May 22, 2026**.
`MCP_SERVER_HOST` and `MCP_SERVER_PORT` apply when running `python -m ace_platform.mcp.server` directly.

### MCP_SERVER_HOST

Host address for the MCP (Model Context Protocol) server.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `0.0.0.0` |

### MCP_SERVER_PORT

Port for the MCP server.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `8001` |

---

## Evolution Settings

These settings control the automatic playbook evolution behavior.

### EVOLUTION_OUTCOME_THRESHOLD

Number of unprocessed outcomes required to trigger automatic evolution.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `5` |
| Range | 5-100 |

### EVOLUTION_API_PROVIDER

LLM provider for evolution operations.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `openai` |
| Options | `openai`, `anthropic`, `together` |

### EVOLUTION_GENERATOR_MODEL

Model used for the Generator agent during evolution.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `gpt-4o` |

### EVOLUTION_REFLECTOR_MODEL

Model used for the Reflector agent during evolution.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `gpt-4o` |

### EVOLUTION_CURATOR_MODEL

Model used for the Curator agent during evolution.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `gpt-4o` |

### EVOLUTION_MAX_TOKENS

Maximum tokens per LLM call during evolution.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `4096` |

### EVOLUTION_PLAYBOOK_TOKEN_BUDGET

Maximum tokens allowed for playbook content.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `80000` |

---

## API Server

### API_HOST

Host address for the FastAPI server.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `0.0.0.0` |

### API_PORT

Port for the FastAPI server.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `8000` |

### CORS_ORIGINS

Allowed CORS origins for cross-origin requests.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `["http://localhost:3000", "http://localhost:8000"]` |
| Format | JSON array or comma-separated list |

**Examples:**
```bash
# JSON array
CORS_ORIGINS=["https://app.example.com", "https://admin.example.com"]

# Comma-separated (also works)
CORS_ORIGINS=https://app.example.com,https://admin.example.com
```

---

## Environment Settings

### ENVIRONMENT

Environment name for configuration and logging.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `development` |
| Options | `development`, `staging`, `production` |

**Effects:**
- `development`: Verbose logging defaults
- `staging`: Production-like behavior with staging-safe defaults
- `production`: Minimal logging defaults

### DEBUG

Enable debug mode for verbose logging and developer features.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `false` |
| Options | `true`, `false` |

**Effects when `true`:**
- Swagger UI (`/docs`) and ReDoc (`/redoc`) endpoints enabled
- When `false`, `/docs` and `/redoc` are not mounted
- Detailed error messages in API responses
- SQL query logging

---

## Logging

### LOG_LEVEL

Override the default log level.

| Property | Value |
|----------|-------|
| Required | No |
| Default | Auto-determined based on environment |
| Options | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

### LOG_FORMAT

Log output format.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `auto` |
| Options | `json`, `text`, `auto` |

**Options:**
- `json`: Structured JSON logs (recommended for production)
- `text`: Human-readable logs (recommended for development)
- `auto`: `text` in development, `json` in production

---

## Error Tracking (Sentry)

Sentry integration is optional and disabled by default.

### SENTRY_DSN

Sentry Data Source Name for error tracking.

| Property | Value |
|----------|-------|
| Required | No |
| Default | (empty - Sentry disabled) |
| Format | `https://...@sentry.io/...` |

**Example:**
```bash
SENTRY_DSN=https://abc123@o123456.ingest.sentry.io/7891011
```

### SENTRY_RELEASE

Optional release identifier for Sentry event grouping.

| Property | Value |
|----------|-------|
| Required | No |
| Default | Derived from `CI_COMMIT_SHA`, `GITHUB_SHA`, `GIT_COMMIT`, `FLY_COMMIT_SHA`, then package version |
| Example | `SENTRY_RELEASE=ace-platform@<commit-sha>` |

You can also set explicit process overrides:

- `SENTRY_RELEASE_API`
- `SENTRY_RELEASE_MCP`
- `SENTRY_RELEASE_WORKER`
- `SENTRY_RELEASE_BEAT`

If a process-specific value is set, that value takes precedence over the global `SENTRY_RELEASE`.

### SENTRY_TRACES_SAMPLE_RATE

Sample rate for Sentry performance monitoring.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `0.1` (10%) |
| Range | `0.0` to `1.0` |

You can set per-process overrides:

- `SENTRY_TRACES_SAMPLE_RATE_API`
- `SENTRY_TRACES_SAMPLE_RATE_MCP`
- `SENTRY_TRACES_SAMPLE_RATE_WORKER`
- `SENTRY_TRACES_SAMPLE_RATE_BEAT`

### SENTRY_PROFILES_SAMPLE_RATE

Sample rate for Sentry profiling.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `0.1` (10%) |
| Range | `0.0` to `1.0` |

You can set per-process overrides:

- `SENTRY_PROFILES_SAMPLE_RATE_API`
- `SENTRY_PROFILES_SAMPLE_RATE_MCP`
- `SENTRY_PROFILES_SAMPLE_RATE_WORKER`
- `SENTRY_PROFILES_SAMPLE_RATE_BEAT`

### Frontend Sentry env vars (Vite)

Frontend values are build-time only and used by `web`:

- `VITE_SENTRY_DSN`
- `VITE_SENTRY_RELEASE`
- `VITE_SENTRY_ENVIRONMENT`
- `VITE_SENTRY_TRACES_SAMPLE_RATE`

### SENTRY_TRANSPORT_QUEUE_SIZE

Queue size used by the Sentry transport while sending events in the background.

| Property | Value |
|----------|-------|
| Required | No |
| Default | `100` |
| Range | `1` or greater |

Process-specific overrides:

- `SENTRY_TRANSPORT_QUEUE_SIZE_API`
- `SENTRY_TRANSPORT_QUEUE_SIZE_MCP`
- `SENTRY_TRANSPORT_QUEUE_SIZE_WORKER`
- `SENTRY_TRANSPORT_QUEUE_SIZE_BEAT`

### Telemetry Redaction Policy

For API exception reporting, request header values are sanitized before being
attached to Sentry context.

- Always redacted: `Authorization`, `Proxy-Authorization`, `Cookie`, `Set-Cookie`,
  `X-Api-Key`, and other token/secret/session-style headers
- Preserved: non-sensitive operational headers (for example correlation IDs and
  user agent) for debugging and traceability

---

## Deployment Scenarios

### Local Development

Minimal configuration for local development:

```bash
# .env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ace_platform
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=sk-proj-your-key-here
JWT_SECRET_KEY=development-only-secret-key
ENVIRONMENT=development
DEBUG=true
```

### Docker Compose Development

Configuration when using Docker Compose:

```bash
# .env
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/ace_platform
REDIS_URL=redis://redis:6379/0
OPENAI_API_KEY=sk-proj-your-key-here
JWT_SECRET_KEY=development-only-secret-key
ENVIRONMENT=development
DEBUG=true
```

### Production (Self-Hosted)

Recommended production configuration:

```bash
# .env (or use secrets management)
DATABASE_URL=postgresql://user:password@db.internal:5432/ace_platform?sslmode=require
REDIS_URL=rediss://:password@redis.internal:6380/0
OPENAI_API_KEY=sk-proj-your-production-key

# Security
JWT_SECRET_KEY=<generate with: openssl rand -hex 32>
ENVIRONMENT=production
DEBUG=false

# Optional: Error tracking
SENTRY_DSN=https://...@sentry.io/...
SENTRY_TRACES_SAMPLE_RATE=0.1
SENTRY_RELEASE=ace-platform@main
SENTRY_RELEASE_API=ace-platform-api@main
SENTRY_RELEASE_WORKER=ace-platform-worker@main
SENTRY_TRACES_SAMPLE_RATE_API=0.1
SENTRY_TRACES_SAMPLE_RATE_MCP=0.05
SENTRY_TRACES_SAMPLE_RATE_WORKER=0.05
SENTRY_PROFILES_SAMPLE_RATE=0.05
SENTRY_PROFILES_SAMPLE_RATE_API=0.05
SENTRY_PROFILES_SAMPLE_RATE_MCP=0.0
SENTRY_PROFILES_SAMPLE_RATE_WORKER=0.0
SENTRY_TRANSPORT_QUEUE_SIZE=100

# Optional: Billing
BILLING_ENABLED=true
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# CORS for your domain
CORS_ORIGINS=["https://app.yourdomain.com"]
```

### Production (Fly.io)

When deploying to Fly.io, use `fly secrets set`:

```bash
# Set secrets (these override .env)
fly secrets set \
  DATABASE_URL="postgres://..." \
  REDIS_URL="redis://..." \
  OPENAI_API_KEY="sk-..." \
  JWT_SECRET_KEY="$(openssl rand -hex 32)" \
  ENVIRONMENT="production" \
  SENTRY_DSN="https://...@sentry.io/..."
```

---

## Security Best Practices

1. **Never commit secrets** - Use `.env` files locally (gitignored) and secrets management in production
2. **Rotate JWT_SECRET_KEY** - Use a strong random value and rotate periodically
3. **Use SSL/TLS** - Enable `sslmode=require` for database and `rediss://` for Redis in production
4. **Limit CORS origins** - Only allow your actual domains, never use `*`
5. **Disable debug** - Set `DEBUG=false` in production to hide sensitive error details
6. **Use separate API keys** - Use different OpenAI keys for development vs production
