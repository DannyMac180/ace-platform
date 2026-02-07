---
sidebar_position: 3
---

# Deployment & Self-Hosting

This guide covers deploying ACE Platform to your own infrastructure using Docker Compose or Fly.io.

## Prerequisites

- Python 3.10+
- Docker & Docker Compose
- Required API keys: OpenAI, Stripe (for billing)

## Environment Variables

Create a `.env` file with the following required variables:

```bash
DATABASE_URL=postgresql://user:pass@localhost:5432/ace_platform
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=sk-...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
JWT_SECRET_KEY=your-secret-key
```

## Docker Compose Deployment

The simplest way to run the full stack is with Docker Compose.

### Start the Full Stack

```bash
# 1. Set up environment variables
cp .env.example .env
# Edit .env with your API keys

# 2. Start all services (postgres, redis, api, mcp, worker, beat)
docker compose --profile full up -d

# 3. View logs
docker compose logs -f api       # API server logs
docker compose logs -f worker    # Worker logs

# 4. Stop everything
docker compose --profile full down
```

### Infrastructure Only

If you want to run the application locally but use containerized Postgres and Redis:

```bash
docker compose up -d postgres redis
```

Then run the application services locally:

```bash
source venv/bin/activate
alembic upgrade head                                      # Run migrations
uvicorn ace_platform.api.main:app --reload                # API server (port 8000)
celery -A ace_platform.workers.celery_app worker -l info  # Background worker
```

## Fly.io Deployment

ACE Platform can be deployed to [Fly.io](https://fly.io) for production hosting.

### Initial Setup

```bash
# 1. Install flyctl
curl -L https://fly.io/install.sh | sh

# 2. Login to Fly.io
fly auth login

# 3. Create the app (first time only)
fly launch --no-deploy

# 4. Create Postgres database
fly postgres create --name ace-platform-db
fly postgres attach ace-platform-db

# 5. Create Redis instance
fly redis create --name ace-platform-redis

# 6. Set required secrets
fly secrets set \
  OPENAI_API_KEY=sk-... \
  JWT_SECRET_KEY=your-secure-secret \
  STRIPE_SECRET_KEY=sk_live_... \
  STRIPE_WEBHOOK_SECRET=whsec_...

# 7. Deploy
fly deploy

# 8. Scale processes as needed
fly scale count api=2 worker=2 beat=1
```

### Common Fly.io Commands

| Command | Description |
|---------|-------------|
| `fly deploy` | Deploy latest changes |
| `fly logs` | View application logs |
| `fly status` | Check app status |
| `fly scale count api=N worker=N` | Scale processes |
| `fly ssh console` | SSH into a running machine |
| `fly secrets list` | List configured secrets |
| `fly postgres connect -a ace-platform-db` | Connect to Postgres |

## CI/CD

The project includes GitHub Actions workflows for continuous deployment:

| Workflow | Trigger | Description |
|----------|---------|-------------|
| `staging.yml` | Push to `main` | Runs tests, then auto-deploys to staging |
| `production.yml` | Manual dispatch | Requires confirmation, then deploys to production |

**Typical flow:**

1. Develop locally and run tests
2. Push to `main` to automatically deploy to staging
3. Validate on staging
4. Trigger production deploy manually from GitHub Actions
