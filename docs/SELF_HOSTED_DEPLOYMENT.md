# Self-Hosted Deployment Guide

This guide covers deploying ACE Platform on your own infrastructure using Docker Compose.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [Configuration](#configuration)
- [Database Setup](#database-setup)
- [Running the Stack](#running-the-stack)
- [Health Checks and Monitoring](#health-checks-and-monitoring)
- [Optional: Billing Configuration](#optional-billing-configuration)
- [Optional: Error Tracking](#optional-error-tracking)
- [Scaling](#scaling)
- [Backup and Recovery](#backup-and-recovery)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

- **Docker** 20.10+ and **Docker Compose** v2.0+
- **4GB RAM** minimum (8GB recommended)
- **20GB disk space** minimum
- **OpenAI API key** for playbook evolution
- Domain name (for production) with SSL certificate

### Verify Docker Installation

```bash
docker --version
docker compose version
```

---

## Quick Start

Get ACE Platform running in under 5 minutes:

```bash
# 1. Clone the repository
git clone https://github.com/DannyMac180/ace-platform.git
cd ace-platform

# 2. Create environment file
cp .env.example .env

# 3. Edit .env with your settings (minimum required)
#    - Set OPENAI_API_KEY
#    - Set JWT_SECRET_KEY (use: openssl rand -hex 32)

# 4. Start the complete stack
docker compose --profile full up -d

# 5. Verify services are running
docker compose ps

# 6. Check API health
curl http://localhost:8000/health
```

---

## Architecture Overview

The ACE Platform consists of the following services:

```
┌─────────────────────────────────────────────────────────────────┐
│                        ACE Platform                              │
├──────────────┬──────────────┬───────────────┬──────────────────┤
│     API      │     MCP      │    Worker     │      Beat        │
│   (FastAPI)  │   Server     │   (Celery)    │   (Scheduler)    │
│   :8000      │   :8001      │               │                  │
└──────┬───────┴──────┬───────┴───────┬───────┴────────┬─────────┘
       │              │               │                │
       ▼              ▼               ▼                ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Shared Infrastructure                        │
├────────────────────────────────┬─────────────────────────────────┤
│         PostgreSQL             │            Redis                │
│           :5432                │            :6379                │
└────────────────────────────────┴─────────────────────────────────┘
```

| Service | Description | Port |
|---------|-------------|------|
| **api** | REST API server (FastAPI) | 8000 |
| **mcp** | Model Context Protocol server | 8001 |
| **worker** | Background task processor (Celery) | - |
| **beat** | Periodic task scheduler | - |
| **postgres** | Primary database | 5432 |
| **redis** | Task queue and caching | 6379 |

---

## Configuration

### Environment Variables

Create a `.env` file from the template:

```bash
cp .env.example .env
```

**Required settings:**

```bash
# Database (uses defaults for Docker Compose)
DATABASE_URL=postgresql://postgres:postgres@postgres:5432/ace_platform

# Redis (uses defaults for Docker Compose)
REDIS_URL=redis://redis:6379/0

# OpenAI API key (REQUIRED)
OPENAI_API_KEY=sk-proj-your-key-here

# JWT secret (REQUIRED - generate a secure key)
JWT_SECRET_KEY=$(openssl rand -hex 32)

# Environment
ENVIRONMENT=production
DEBUG=false
```

**Production settings:**

```bash
# Strong database password
DATABASE_URL=postgresql://ace_user:strong_password_here@postgres:5432/ace_platform

# CORS - only your domains
CORS_ORIGINS=["https://app.yourdomain.com"]

# Logging
LOG_FORMAT=json
LOG_LEVEL=INFO
```

See [ENVIRONMENT_VARIABLES.md](./ENVIRONMENT_VARIABLES.md) for complete reference.

---

## Database Setup

### Initial Setup

The migration service runs automatically when using `--profile full`:

```bash
# Migrations run automatically with:
docker compose --profile full up -d

# Or run migrations manually:
docker compose run --rm migrate
```

### Using External Database

For production, you may want to use a managed PostgreSQL service:

```bash
# .env
DATABASE_URL=postgresql://user:password@your-db-host.com:5432/ace_platform
DATABASE_URL_ASYNC=postgresql+asyncpg://user:password@your-db-host.com:5432/ace_platform
```

Then start without the local postgres:

```bash
# Start only app services (assumes external DB)
docker compose --profile full up -d api mcp worker beat
```

### Database Backups

```bash
# Create backup
docker compose exec postgres pg_dump -U postgres ace_platform > backup_$(date +%Y%m%d).sql

# Restore backup
docker compose exec -T postgres psql -U postgres ace_platform < backup_20240101.sql
```

---

## Running the Stack

### Development Mode

Infrastructure only (run app locally for hot-reload):

```bash
# Start just PostgreSQL and Redis
docker compose up -d postgres redis

# Run app locally
source venv/bin/activate
uvicorn ace_platform.api.main:app --reload
```

### Production Mode

Full stack with all services:

```bash
# Start everything
docker compose --profile full up -d

# View logs
docker compose logs -f api worker

# Stop everything
docker compose --profile full down
```

### Individual Service Control

```bash
# Restart a specific service
docker compose restart api

# Scale workers
docker compose up -d --scale worker=3

# View service logs
docker compose logs -f worker --tail=100
```

---

## Health Checks and Monitoring

### Health Check Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Basic liveness check |
| `GET /ready` | Readiness check (includes DB) |
| `GET /metrics` | Prometheus metrics |

```bash
# Check API health
curl http://localhost:8000/health
# {"status": "healthy", "service": "ace-platform"}

# Check readiness
curl http://localhost:8000/ready
# {"status": "ready", "database": "connected"}
```

### Prometheus Metrics

The `/metrics` endpoint exposes Prometheus-format metrics:

```bash
curl http://localhost:8000/metrics
```

Key metrics:
- `ace_outcomes_by_status_total` - Outcome counts
- `ace_evolutions_triggered_total` - Evolution triggers
- `ace_evolution_duration_seconds` - Evolution job duration
- `ace_tokens_used_total` - LLM token usage
- `ace_evolution_jobs_active` - Active evolution jobs

### Docker Health Checks

All services have built-in health checks:

```bash
# Check container health
docker compose ps

# View health check logs
docker inspect ace-api | jq '.[0].State.Health'
```

### Monitoring Stack (Optional)

Add Prometheus and Grafana for dashboards:

```yaml
# docker-compose.monitoring.yml
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"
    networks:
      - ace-network

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"
    networks:
      - ace-network
```

```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml --profile full up -d
```

---

## Optional: Billing Configuration

Enable Stripe billing for paid tiers:

```bash
# .env
BILLING_ENABLED=true
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

### Stripe Webhook Setup

1. Create webhook in Stripe Dashboard pointing to:
   `https://yourdomain.com/billing/webhook`

2. Select events:
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.paid`
   - `invoice.payment_failed`

3. Copy the signing secret to `STRIPE_WEBHOOK_SECRET`

---

## Optional: Error Tracking

Enable Sentry for error tracking:

```bash
# .env
SENTRY_DSN=https://...@sentry.io/...
SENTRY_TRACES_SAMPLE_RATE=0.1
SENTRY_PROFILES_SAMPLE_RATE=0.1
```

Sentry will automatically capture:
- Unhandled exceptions in API and workers
- Performance traces
- User context for authenticated requests

---

## Scaling

### Horizontal Scaling

Scale workers for more processing capacity:

```bash
# Scale to 4 workers
docker compose up -d --scale worker=4
```

### API Scaling

The API container runs with 4 uvicorn workers by default. For more capacity:

1. Scale API containers:
   ```bash
   docker compose up -d --scale api=2
   ```

2. Add a load balancer (nginx, traefik, or cloud LB)

### Resource Limits

Add resource constraints in docker-compose.override.yml:

```yaml
services:
  api:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
```

---

## Backup and Recovery

### Automated Backups

Create a backup script:

```bash
#!/bin/bash
# backup.sh
BACKUP_DIR=/backups
DATE=$(date +%Y%m%d_%H%M%S)

# Backup PostgreSQL
docker compose exec -T postgres pg_dump -U postgres ace_platform | gzip > $BACKUP_DIR/db_$DATE.sql.gz

# Keep last 7 days
find $BACKUP_DIR -name "db_*.sql.gz" -mtime +7 -delete
```

Add to crontab:
```bash
0 2 * * * /path/to/backup.sh
```

### Recovery

```bash
# Stop services
docker compose --profile full down

# Restore database
gunzip -c backup.sql.gz | docker compose exec -T postgres psql -U postgres ace_platform

# Restart services
docker compose --profile full up -d
```

---

## Troubleshooting

### Common Issues

**Services won't start:**
```bash
# Check logs
docker compose logs api

# Verify environment
docker compose config

# Reset and rebuild
docker compose --profile full down -v
docker compose --profile full up -d --build
```

**Database connection errors:**
```bash
# Check postgres is healthy
docker compose ps postgres

# Test connection
docker compose exec postgres psql -U postgres -c "SELECT 1"
```

**Worker not processing tasks:**
```bash
# Check worker logs
docker compose logs worker -f

# Verify Redis connection
docker compose exec redis redis-cli ping
```

**Out of memory:**
```bash
# Check container memory usage
docker stats

# Reduce worker concurrency
# In docker-compose.override.yml:
# worker:
#   command: celery -A ace_platform.workers.celery_app worker --concurrency=2
```

### Logs

```bash
# All logs
docker compose logs -f

# Specific service
docker compose logs -f api --tail=100

# Export logs
docker compose logs > logs.txt
```

### Reset Everything

```bash
# Stop and remove all containers, volumes, and networks
docker compose --profile full down -v

# Remove images
docker compose --profile full down --rmi all

# Fresh start
docker compose --profile full up -d --build
```

---

## Next Steps

- [API Reference](./API_REFERENCE.md) - Complete API documentation
- [MCP Integration](./MCP_INTEGRATION.md) - Integrate with AI assistants
- [Environment Variables](./ENVIRONMENT_VARIABLES.md) - All configuration options
