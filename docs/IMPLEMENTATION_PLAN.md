# ACE Platform Implementation Plan

## Overview

This plan transforms the existing ACE core implementation into a hosted "Playbooks as a Service" platform. The `ace_core/` directory is already fully implemented with the three-agent architecture (Generator, Reflector, Curator). This plan focuses on building the `ace_platform/` layer.

**Timeline:** 4 weeks (solo developer with Claude Code)
**Current State:** Core ACE implementation complete, platform scaffolding in place

---

## Key Architecture Decisions

These decisions must be finalized before coding begins to avoid rework.

### 1. Package Naming
- **Decision:** Use `ace_platform/` (not `platform/`)
- **Rationale:** `platform` is a Python standard library module; naming conflicts cause import shadowing and runtime issues

### 2. Execution Model: Async Web Tier, Sync Workers
- **Web tier (API + MCP):** AsyncSession with `asyncpg` for high concurrency I/O-bound operations
- **Workers (Celery):** Sync Session with `psycopg2-binary` for simpler CPU-bound evolution tasks
- **Rationale:** Best of both worlds—async where it matters for performance, sync where it simplifies code

### 3. Playbook Versioning Strategy
- **Decision:** Implement `PlaybookVersion` table for full evolution history
- **Rationale:** Required for "evolution history" feature; retrofitting later is costly
- **Implementation:** Each evolution creates a new version; playbook points to current version

### 4. Authentication Strategy
- **Web dashboard:** JWT tokens (short-lived access + refresh)
- **MCP clients:** Per-user API keys (hashed, revocable, scoped)
- **Rationale:** Different auth patterns for different client types

### 5. Evolution Concurrency & Idempotency
- **Decision:** Only one active evolution per playbook at a time
- **Implementation:** Partial unique index on `(playbook_id)` where status in `(queued, running)`
- **Idempotency:** `trigger_evolution()` returns existing job if one is queued/running
- **Atomicity:** New version + outcome linking happens in single transaction

### 6. LLM Key Strategy
- **Default:** Platform-managed OpenAI key (SaaS model)
- **Future:** Optional per-user encrypted keys (self-hosted friendly)
- **Rationale:** Start simple; design schema to support both

### 7. Billing Model
- **Decision:** Make billing optional via `BILLING_ENABLED` feature flag
- **Default:** Disabled for self-hosted deployments
- **Rationale:** Usage tracking always enabled (cost visibility); Stripe integration only when needed

---

## Week 1: Foundation

### 1.1 Database Schema & Models
**File:** `ace_platform/db/models.py`

Create SQLAlchemy models for:

```python
# Core entities
User:
  - id: UUID (primary key)
  - email: str (unique, indexed, normalized lowercase)
  - hashed_password: str
  - is_active: bool (default True)
  - email_verified: bool (default False)
  - stripe_customer_id: str (nullable)
  - created_at: datetime
  - updated_at: datetime

Playbook:
  - id: UUID (primary key)
  - user_id: UUID (foreign key, indexed)
  - name: str
  - description: str (nullable)
  - current_version_id: UUID (foreign key, nullable)
  - status: enum (active, archived)
  - source: enum (starter, user_created, imported)
  - created_at: datetime
  - updated_at: datetime

PlaybookVersion:
  - id: UUID (primary key)
  - playbook_id: UUID (foreign key, indexed)
  - version_number: int
  - content: text
  - bullet_count: int
  - created_at: datetime
  - created_by_job_id: UUID (foreign key, nullable)
  - diff_summary: str (nullable)

Outcome:
  - id: UUID (primary key)
  - playbook_id: UUID (foreign key, indexed)
  - task_description: str
  - outcome_status: enum (success, failure, partial)
  - reasoning_trace: text (nullable)
  - notes: text (nullable)
  - reflection_data: JSONB (nullable)
  - created_at: datetime
  - updated_at: datetime
  - processed_at: datetime (nullable)
  - evolution_job_id: UUID (foreign key, nullable)

EvolutionJob:
  - id: UUID (primary key)
  - playbook_id: UUID (foreign key, indexed)
  - status: enum (queued, running, completed, failed)
  - from_version_id: UUID (foreign key, nullable)
  - to_version_id: UUID (foreign key, nullable)
  - outcomes_processed: int (default 0)
  - started_at: datetime (nullable)
  - completed_at: datetime (nullable)
  - error_message: text (nullable)
  - token_totals: JSONB (nullable)
  - ace_core_version: str (nullable)
  - created_at: datetime

UsageRecord:
  - id: UUID (primary key)
  - user_id: UUID (foreign key, indexed)
  - playbook_id: UUID (foreign key, nullable)
  - evolution_job_id: UUID (foreign key, nullable)
  - operation: str (e.g., "reflect", "curate", "generate")
  - model: str
  - prompt_tokens: int
  - completion_tokens: int
  - total_tokens: int
  - cost_usd: Decimal(10, 6)
  - request_id: str (nullable)
  - metadata: JSONB (nullable)
  - created_at: datetime

ApiKey:
  - id: UUID (primary key)
  - user_id: UUID (foreign key, indexed)
  - name: str
  - key_prefix: str (first 8 chars for identification)
  - hashed_key: str
  - scopes: JSONB (e.g., ["read", "write", "evolve"])
  - created_at: datetime
  - last_used_at: datetime (nullable)
  - revoked_at: datetime (nullable)
```

**Indexes & Constraints:**
- Unique index on `User.email`
- Unique partial index on `EvolutionJob(playbook_id)` WHERE `status IN ('queued', 'running')` (prevents concurrent evolution)
- Composite index on `Outcome(playbook_id, processed_at)` for unprocessed outcome queries
- Index on `UsageRecord(user_id, created_at)` for billing aggregation

**Tasks:**
- [ ] Implement SQLAlchemy models in `ace_platform/db/models.py`
- [ ] Create database connection utilities in `ace_platform/db/session.py`
  - [ ] Async engine + `AsyncSession` factory for API/MCP (using `asyncpg`)
  - [ ] Sync engine + `Session` factory for workers (using `psycopg2-binary`)
- [ ] Set up Alembic for migrations in `ace_platform/db/migrations/`
- [ ] Write initial migration for all tables with indexes and constraints
- [ ] Add partial unique index for evolution concurrency control

### 1.2 Environment & Configuration
**File:** `ace_platform/config.py`

```python
# Configuration needed
- DATABASE_URL (PostgreSQL connection string)
- DATABASE_URL_ASYNC (PostgreSQL async connection string, derived if not set)
- REDIS_URL (for Celery)
- OPENAI_API_KEY
- JWT_SECRET_KEY
- JWT_ACCESS_TOKEN_EXPIRE_MINUTES (default: 30)
- JWT_REFRESH_TOKEN_EXPIRE_DAYS (default: 7)

# Billing (optional)
- BILLING_ENABLED (default: false)
- STRIPE_SECRET_KEY (required if billing enabled)
- STRIPE_WEBHOOK_SECRET (required if billing enabled)

# MCP
- MCP_SERVER_HOST (default: 0.0.0.0)
- MCP_SERVER_PORT (default: 8001)

# Evolution
- EVOLUTION_OUTCOME_THRESHOLD (default: 5)
- EVOLUTION_TIME_THRESHOLD_HOURS (default: 24)
```

**Tasks:**
- [ ] Create `ace_platform/config.py` with Pydantic Settings
- [ ] Add validation for required vs optional fields based on feature flags
- [ ] Create `.env.example` with all variables and documentation
- [ ] Set up development PostgreSQL database (Docker)
- [ ] Set up development Redis instance (Docker)
- [ ] Create `docker-compose.yml` for local development infrastructure

### 1.3 Evolution Wrapper
**File:** `ace_platform/core/evolution.py`

Wrap the upstream ACE code to:
- Accept a playbook and list of outcomes
- Run the Reflector on each outcome to tag bullet effectiveness
- Run the Curator to update the playbook
- Return the evolved playbook content with token usage

**Tasks:**
- [ ] Create `EvolutionService` class that wraps `ace_core/ace/ace.py`
- [ ] Implement `evolve_playbook(playbook_content, outcomes) -> EvolutionResult`
- [ ] Capture token usage from API response (prefer over tiktoken estimates)
- [ ] Fall back to tiktoken counting only when API usage unavailable
- [ ] Return `EvolutionResult(new_content, token_usage, diff_summary)`
- [ ] Implement atomic version creation in transaction
- [ ] Write unit tests for evolution wrapper

### 1.4 Token Cost Analysis
**Deliverable:** Documentation of token economics

**Tasks:**
- [ ] Run sample ACE evolution loop with token counting
- [ ] Document tokens per Generator/Reflector/Curator call
- [ ] Calculate cost per evolution at current OpenAI prices
- [ ] Create pricing model recommendations
- [ ] Document in `docs/TOKEN_ECONOMICS.md`

---

## Week 2: MCP Server

### 2.1 MCP Server Core
**File:** `ace_platform/mcp/server.py`

**Architecture Decision:** Host MCP as part of FastAPI app to reduce operational complexity. Use separate router with MCP-specific middleware.

**Tasks:**
- [ ] Install and configure `mcp` package
- [ ] Create MCP server as FastAPI sub-application or separate process (evaluate SDK requirements)
- [ ] Implement API key authentication middleware
  - [ ] Look up hashed key in database
  - [ ] Validate key is not revoked
  - [ ] Check scopes for requested operation
  - [ ] Update `last_used_at` timestamp
- [ ] Set up server configuration (host, port, transport)

### 2.2 MCP Tools Implementation
**File:** `ace_platform/mcp/tools.py`

Implement the core MCP tools:

#### `list_playbooks`
```python
Parameters:
  - include_starters: bool (optional, default: true)
Returns: Array of { id, name, description, last_updated, bullet_count, outcome_count }
```

#### `get_playbook`
```python
Parameters:
  - playbook_id: str (required)
  - section: str (optional)
  - version: int (optional, default: current)
Returns: Playbook content as structured text
```

#### `report_outcome`
```python
Parameters:
  - playbook_id: str (required)
  - task_description: str (required)
  - outcome: "success" | "failure" | "partial" (required)
  - reasoning_trace: str (optional, max 10KB)
  - notes: str (optional, max 2KB)
Returns: { outcome_id: str, status: "recorded", pending_outcomes: int }
```

#### `trigger_evolution`
```python
Parameters:
  - playbook_id: str (required)
Returns: { job_id: str, status: str, is_new: bool }
# Note: is_new=false if returning existing queued/running job (idempotent)
```

#### `get_evolution_status`
```python
Parameters:
  - job_id: str (required)
Returns: {
  job_id: str,
  status: str,
  outcomes_processed: int,
  started_at: datetime,
  completed_at: datetime (nullable),
  error_message: str (nullable)
}
```

**Tasks:**
- [ ] Implement `list_playbooks` tool with ownership filtering
- [ ] Implement `get_playbook` tool with section filtering and version support
- [ ] Implement `report_outcome` tool with input size limits
- [ ] Implement `trigger_evolution` tool with idempotency (return existing job if queued/running)
- [ ] Implement `get_evolution_status` tool for job monitoring
- [ ] Add input validation for all tools (size limits, format)
- [ ] Add error handling and meaningful error messages
- [ ] Enforce playbook ownership in all tools

### 2.3 LLM Proxy Layer
**File:** `ace_platform/core/llm_proxy.py`

Wrap LLM calls to add metering:

**Tasks:**
- [ ] Create `MeteredLLMClient` that wraps OpenAI client
- [ ] Extract token usage from API response (primary source)
- [ ] Fall back to tiktoken only when response lacks usage data
- [ ] Log usage to `UsageRecord` table
- [ ] Associate usage with user, playbook, and evolution job
- [ ] Add correlation ID for request tracing

### 2.4 MCP Integration Testing

**Tasks:**
- [ ] Test MCP server connection with `mcp` CLI tools
- [ ] Test with Claude Code as MCP client
- [ ] Test API key authentication and scopes
- [ ] Test idempotent evolution triggering
- [ ] Document MCP integration steps
- [ ] Create example agent configuration

---

## Week 3: Dashboard & Workers

### 3.1 FastAPI Application
**File:** `ace_platform/api/main.py`

**Tasks:**
- [ ] Set up FastAPI application with CORS
- [ ] Configure middleware (logging, error handling, request ID)
- [ ] Set up structured JSON logging
- [ ] Set up dependency injection (`ace_platform/api/deps.py`)
- [ ] Create health check endpoint
- [ ] Add rate limiting middleware (especially for outcome reporting)

### 3.2 Authentication
**File:** `ace_platform/api/routes/auth.py`

**Tasks:**
- [ ] Implement JWT-based authentication with access + refresh tokens
- [ ] Create `/auth/register` endpoint with email validation
- [ ] Create `/auth/login` endpoint with rate limiting
- [ ] Create `/auth/refresh` endpoint for token refresh
- [ ] Create `/auth/me` endpoint
- [ ] Add password hashing (bcrypt)
- [ ] Create auth dependency for protected routes
- [ ] Implement API key generation for MCP access
- [ ] Create `/auth/api-keys` CRUD endpoints

### 3.3 Playbook API Routes
**File:** `ace_platform/api/routes/playbooks.py`

```
GET    /playbooks                    - List user's playbooks
POST   /playbooks                    - Create new playbook
GET    /playbooks/{id}               - Get playbook details (with current version)
PUT    /playbooks/{id}               - Update playbook metadata
DELETE /playbooks/{id}               - Archive playbook (soft delete)
GET    /playbooks/{id}/versions      - List playbook versions
GET    /playbooks/{id}/versions/{v}  - Get specific version
GET    /playbooks/{id}/outcomes      - List outcomes for playbook
POST   /playbooks/{id}/outcomes      - Create outcome (REST fallback for MCP)
GET    /playbooks/{id}/evolutions    - List evolution history (jobs)
POST   /playbooks/{id}/evolutions    - Trigger evolution (REST fallback for MCP)
GET    /evolutions/{job_id}          - Get evolution job status
```

**Tasks:**
- [ ] Implement CRUD endpoints for playbooks
- [ ] Implement version listing and retrieval
- [ ] Implement outcome creation endpoint (REST fallback)
- [ ] Add pagination for list endpoints
- [ ] Include outcome counts and evolution status in responses
- [ ] Enforce ownership on all operations

### 3.4 Background Workers
**File:** `ace_platform/workers/evolution_worker.py`

**Evolution Triggering Rules:**
- Trigger after **N unprocessed outcomes** (configurable, default: 5)
- OR after **T hours since last evolution** with at least 1 unprocessed outcome (configurable, default: 24h)
- Whichever condition is met first
- Outcomes arriving during a running job wait for next run

**Tasks:**
- [ ] Set up Celery application with Redis backend
- [ ] Create `process_evolution` task with sync database session
- [ ] Implement locking via `SELECT ... FOR UPDATE` on playbook row
- [ ] Implement atomic transaction for:
  - Create new PlaybookVersion
  - Update Playbook.current_version_id
  - Mark outcomes as processed with job_id link
  - Update EvolutionJob status
- [ ] Implement automatic evolution triggering (threshold-based)
- [ ] Add periodic task to check time-based threshold
- [ ] Add task status tracking
- [ ] Handle failures gracefully with retries and exponential backoff
- [ ] Log token usage to UsageRecord

### 3.5 Web Dashboard (Minimal MVP)
**Directory:** `web/`

**Decision:** Use Jinja2 server-rendered templates for MVP speed. React SPA deferred to post-MVP.

**Pages needed:**
- Login / Register
- Dashboard (list playbooks, usage summary)
- Playbook Detail (content, outcomes, evolution history, version diff)
- API Keys management
- Usage statistics

**Tasks:**
- [ ] Set up Jinja2 templates
- [ ] Implement login/register pages
- [ ] Implement dashboard with playbook list
- [ ] Implement playbook detail view with version history
- [ ] Implement API key management page
- [ ] Add basic usage statistics display

### 3.6 Starter Playbooks
**Directory:** `playbooks/`

**Tasks:**
- [ ] Create `coding_agent.md` starter playbook
- [ ] Create seeding script for starter playbooks
- [ ] Mark starter playbooks as system-owned (source: 'starter')
- [ ] Allow users to clone starters (creates user_created copy)

---

## Week 4: Billing, Observability & Launch

### 4.1 Observability (Critical for Operations)
**Files:** `ace_platform/core/logging.py`, `ace_platform/core/metrics.py`

**Tasks:**
- [ ] Set up structured JSON logging with correlation IDs
- [ ] Add request correlation ID middleware
- [ ] Configure error tracking (Sentry or similar)
- [ ] Implement basic metrics:
  - Outcomes recorded (counter)
  - Evolutions triggered/succeeded/failed (counters)
  - Evolution duration (histogram)
  - Token usage by model (counter)
- [ ] Add health check endpoint with dependency status
- [ ] Configure log levels per environment

### 4.2 Security & Abuse Prevention
**File:** `ace_platform/core/security.py`

**Tasks:**
- [ ] Implement rate limiting:
  - Login attempts: 5/minute per IP
  - Outcome reporting: 100/hour per user
  - Evolution triggering: 10/hour per playbook
- [ ] Add input size limits:
  - Playbook content: 100KB
  - Reasoning trace: 10KB
  - Notes: 2KB
- [ ] Implement login attempt lockout (exponential backoff)
- [ ] Ensure playbook content not logged by default
- [ ] Add optional content truncation in logs
- [ ] Define retention policy for reasoning traces (configurable)

### 4.3 Stripe Integration (Optional)
**File:** `ace_platform/core/billing.py`

**Note:** Only implemented when `BILLING_ENABLED=true`

**Tasks:**
- [ ] Set up Stripe products and prices
- [ ] Implement subscription creation flow
- [ ] Create webhook handler for Stripe events
- [ ] Implement simple billing model (flat subscription + usage cap)
- [ ] Add billing status to user model
- [ ] Defer usage-based billing to post-MVP

### 4.4 Metering System
**File:** `ace_platform/core/metering.py`

**Note:** Always enabled (useful for cost visibility even without billing)

**Tasks:**
- [ ] Aggregate usage records for billing periods
- [ ] Create usage reporting endpoint for dashboard
- [ ] Implement usage limits based on subscription tier (when billing enabled)
- [ ] Create usage summary by day/week/month

### 4.5 API Routes for Billing
**File:** `ace_platform/api/routes/billing.py`

```
GET  /billing/subscription    - Get current subscription status
POST /billing/subscribe       - Create checkout session (if billing enabled)
GET  /billing/usage           - Get usage summary
POST /billing/webhook         - Stripe webhook handler
```

**Tasks:**
- [ ] Implement billing endpoints
- [ ] Add subscription status checks to protected routes (when billing enabled)
- [ ] Return graceful "billing not enabled" responses when disabled

### 4.6 CI/CD & Code Quality
**Files:** `.github/workflows/ci.yml`, `pyproject.toml`

**Tasks:**
- [ ] Set up GitHub Actions for CI:
  - Ruff linting
  - Ruff formatting check
  - pytest with coverage
  - Type checking (optional: mypy)
- [ ] Add pre-commit hooks configuration
- [ ] Set up test database for CI

### 4.7 Deployment
**Files:** `Dockerfile`, `docker-compose.yml`, `fly.toml`

**Tasks:**
- [ ] Create production Dockerfile (multi-stage build)
- [ ] Set up docker-compose for local development (all services)
- [ ] Create Fly.io configuration
- [ ] Deploy PostgreSQL (Fly Postgres or managed)
- [ ] Deploy Redis (Upstash or Fly)
- [ ] Deploy combined API + MCP server
- [ ] Deploy Celery workers
- [ ] Set up environment variables in production
- [ ] Configure health checks and autoscaling

### 4.8 Documentation

**Tasks:**
- [ ] Write MCP integration guide
- [ ] Document API endpoints (OpenAPI auto-generated)
- [ ] Create quick start guide
- [ ] Add troubleshooting section
- [ ] Document environment variables
- [ ] Document self-hosted deployment

### 4.9 End-to-End Testing

**Tasks:**
- [ ] Test full flow: register → create playbook → MCP get_playbook → report_outcome → evolution
- [ ] Test evolution idempotency (concurrent triggers)
- [ ] Test version history and diff viewing
- [ ] Test API key creation and MCP authentication
- [ ] Test billing flow (if enabled)
- [ ] Load test MCP server
- [ ] Fix any issues discovered

---

## File Structure (Final)

```
ace-platform/
├── ace_core/                    # Upstream ACE (existing, minimal changes)
│   ├── ace/
│   ├── finance/
│   ├── llm.py
│   ├── logger.py
│   ├── playbook_utils.py
│   ├── utils.py
│   └── requirements.txt
│
├── ace_platform/
│   ├── __init__.py
│   ├── config.py                # Pydantic settings with feature flags
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app
│   │   ├── deps.py              # Dependencies (db session, current user)
│   │   ├── middleware.py        # Logging, rate limiting, request ID
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── playbooks.py
│   │   │   └── billing.py
│   │   └── schemas/
│   │       ├── __init__.py
│   │       ├── auth.py          # Pydantic schemas for auth
│   │       ├── playbooks.py     # Pydantic schemas for playbooks
│   │       └── billing.py       # Pydantic schemas for billing
│   │
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── server.py            # MCP server entry point
│   │   ├── tools.py             # Tool implementations
│   │   └── auth.py              # MCP API key authentication
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── playbooks.py         # Playbook business logic
│   │   ├── evolution.py         # ACE wrapper for evolution
│   │   ├── llm_proxy.py         # Metered LLM client
│   │   ├── metering.py          # Usage tracking
│   │   ├── billing.py           # Stripe integration (optional)
│   │   ├── security.py          # Rate limiting, input validation
│   │   ├── logging.py           # Structured logging setup
│   │   └── metrics.py           # Basic metrics collection
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py            # SQLAlchemy models
│   │   ├── session.py           # Async + Sync session factories
│   │   └── migrations/
│   │       ├── env.py
│   │       └── versions/
│   │
│   └── workers/
│       ├── __init__.py
│       ├── celery_app.py        # Celery configuration
│       └── evolution_worker.py  # Background evolution tasks
│
├── web/                         # Dashboard frontend
│   ├── templates/               # Jinja2 templates
│   └── static/
│
├── playbooks/
│   ├── coding_agent.md          # Starter playbook
│   └── README.md
│
├── tests/
│   ├── conftest.py
│   ├── test_api/
│   ├── test_mcp/
│   ├── test_evolution/
│   └── test_billing/
│
├── docs/
│   ├── IMPLEMENTATION_PLAN.md
│   ├── TOKEN_ECONOMICS.md
│   └── MCP_INTEGRATION.md
│
├── .env.example
├── .github/
│   └── workflows/
│       └── ci.yml
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── fly.toml
└── README.md
```

---

## Dependencies

```toml
# pyproject.toml
[project]
dependencies = [
    # Web framework
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",

    # Database - Async
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncpg>=0.29.0",

    # Database - Sync (for workers)
    "psycopg2-binary>=2.9.0",

    # Migrations
    "alembic>=1.13.0",

    # Background tasks
    "celery[redis]>=5.3.0",
    "redis>=5.0.0",

    # Auth
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "python-multipart>=0.0.6",

    # MCP
    "mcp>=1.0.0",

    # Billing (optional)
    "stripe>=7.0.0",

    # LLM
    "openai>=1.0.0",
    "tiktoken>=0.5.0",

    # Templates
    "jinja2>=3.1.0",

    # HTTP client
    "httpx>=0.26.0",

    # Utilities
    "pydantic-settings>=2.0.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.0.0",
    "ruff>=0.1.0",
    "httpx>=0.26.0",  # For TestClient
]
```

---

## Key Integration Points

### ACE Core → Platform

The platform wraps `ace_core` through `ace_platform/core/evolution.py`:

```python
from ace_core.ace.ace import ACE
from ace_core.ace.core.reflector import Reflector
from ace_core.ace.core.curator import Curator

class EvolutionService:
    def __init__(self, llm_client: MeteredLLMClient):
        self.llm_client = llm_client

    async def evolve_playbook(
        self,
        playbook_content: str,
        outcomes: list[Outcome],
        job_id: UUID
    ) -> EvolutionResult:
        """
        1. Initialize Reflector with metered LLM client
        2. For each outcome, run reflection to tag bullets
        3. Initialize Curator with accumulated feedback
        4. Run curation to update playbook
        5. Return new playbook + token usage + diff summary
        """
        pass
```

### MCP → Database

MCP tools interact with the database through core services:

```python
# ace_platform/mcp/tools.py
from ace_platform.core.playbooks import PlaybookService
from ace_platform.db.session import get_async_db

@mcp.tool()
async def get_playbook(playbook_id: str, section: str = None):
    async with get_async_db() as db:
        service = PlaybookService(db)
        # Ownership check happens inside service
        return await service.get_playbook(
            playbook_id,
            section,
            user_id=current_user.id  # From auth middleware
        )
```

### Evolution Concurrency Control

```python
# ace_platform/workers/evolution_worker.py
@celery_app.task(bind=True, max_retries=3)
def process_evolution(self, job_id: str):
    with get_sync_db() as db:
        # Lock playbook row
        job = db.execute(
            select(EvolutionJob)
            .where(EvolutionJob.id == job_id)
            .with_for_update()
        ).scalar_one()

        # ... run evolution ...

        # Atomic commit: new version + link outcomes + update job
        db.commit()
```

---

## Success Criteria

By end of Week 4:

- [ ] User can register and log in via dashboard
- [ ] User can create/view/archive playbooks via dashboard
- [ ] User can view playbook version history and diffs
- [ ] User can generate and manage API keys
- [ ] MCP server responds to all five tool calls
- [ ] API key authentication works for MCP
- [ ] Outcomes are recorded and trigger evolution (threshold-based)
- [ ] Evolution jobs are idempotent (concurrent triggers return same job)
- [ ] Evolution creates proper version history
- [ ] Token usage is tracked and displayed
- [ ] Structured logging and basic metrics in place
- [ ] Rate limiting protects abuse vectors
- [ ] Stripe subscription flow works (if billing enabled)
- [ ] Platform deployed and accessible
- [ ] CI pipeline runs tests and linting
- [ ] Documentation complete

---

## Risk Mitigations

| Risk | Mitigation |
|------|------------|
| Token costs too high | Implement rate limiting; set minimum outcome batch size for evolution |
| MCP integration issues | Test early in Week 2; have REST API fallback ready |
| Evolution quality | Use existing ACE defaults; defer quality tuning to post-MVP |
| Scope creep | Strictly follow MVP scope; defer React SPA, teams, sharing |
| Concurrent evolution corruption | Partial unique index + idempotent trigger + row locking |
| API key compromise | Hash keys (like passwords); implement revocation; short key display prefix only |

---

## Deferred to Post-MVP

The following are explicitly out of scope for the 4-week MVP:

1. **React SPA** - Use Jinja2 templates instead
2. **Usage-based Stripe billing** - Flat subscription + cap is simpler
3. **Per-user LLM keys** - Platform key only for now
4. **Team collaboration** - Single user per account
5. **Playbook sharing** - Private playbooks only
6. **Advanced analytics** - Basic usage stats only
7. **Email verification flow** - Mark as unverified, enforce later

---

## Commands Reference

```bash
# Development
docker-compose up -d postgres redis    # Start services
alembic upgrade head                    # Run migrations
uvicorn ace_platform.api.main:app --reload  # Start API server
python -m ace_platform.mcp.server           # Start MCP server
celery -A ace_platform.workers.celery_app worker --loglevel=info  # Start worker

# Testing
pytest tests/ -v                        # Run tests
pytest tests/test_mcp/ -v              # Run MCP tests only
pytest --cov=ace_platform tests/       # With coverage

# Code quality
ruff check .                           # Lint
ruff format .                          # Format

# Production
fly deploy                              # Deploy to Fly.io
fly logs                                # View logs
```
