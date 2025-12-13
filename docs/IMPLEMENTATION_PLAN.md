# ACE Platform Implementation Plan

## Overview

This plan transforms the existing ACE core implementation into a hosted "Playbooks as a Service" platform. The `ace_core/` directory is already fully implemented with the three-agent architecture (Generator, Reflector, Curator). This plan focuses on building the `platform/` layer.

**Timeline:** 4 weeks (solo developer with Claude Code)
**Current State:** Core ACE implementation complete, platform scaffolding in place

---

## Week 1: Foundation

### 1.1 Database Schema & Models
**File:** `platform/db/models.py`

Create SQLAlchemy models for:

```python
# Core entities
- User (id, email, hashed_password, stripe_customer_id, created_at)
- Playbook (id, user_id, name, description, content, bullet_count, created_at, updated_at)
- Outcome (id, playbook_id, task_description, outcome_status, reasoning_trace, notes, processed, created_at)
- EvolutionJob (id, playbook_id, status, started_at, completed_at, outcomes_processed, error_message)
- UsageRecord (id, user_id, playbook_id, operation, tokens_used, cost_usd, created_at)
```

**Tasks:**
- [ ] Implement SQLAlchemy models in `platform/db/models.py`
- [ ] Create database connection utilities in `platform/db/session.py`
- [ ] Set up Alembic for migrations in `platform/db/migrations/`
- [ ] Write initial migration for all tables
- [ ] Add indexes for common queries (user_id, playbook_id, created_at)

### 1.2 Environment & Configuration
**File:** `platform/config.py`

```python
# Configuration needed
- DATABASE_URL (PostgreSQL connection string)
- REDIS_URL (for Celery)
- OPENAI_API_KEY
- STRIPE_SECRET_KEY
- STRIPE_WEBHOOK_SECRET
- JWT_SECRET_KEY
- MCP_SERVER_HOST/PORT
```

**Tasks:**
- [ ] Create `platform/config.py` with Pydantic Settings
- [ ] Create `.env.example` with all required variables
- [ ] Set up development PostgreSQL database (Docker or local)
- [ ] Set up development Redis instance

### 1.3 Evolution Wrapper
**File:** `platform/core/evolution.py`

Wrap the upstream ACE code to:
- Accept a playbook and list of outcomes
- Run the Reflector on each outcome to tag bullet effectiveness
- Run the Curator to update the playbook
- Return the evolved playbook content

**Tasks:**
- [ ] Create `EvolutionService` class that wraps `ace_core/ace/ace.py`
- [ ] Implement `evolve_playbook(playbook_content, outcomes) -> new_playbook_content`
- [ ] Add token counting for each LLM call (using tiktoken)
- [ ] Return token usage alongside evolved playbook
- [ ] Write unit tests for evolution wrapper

### 1.4 Token Cost Analysis
**Deliverable:** Documentation of token economics

**Tasks:**
- [ ] Run sample ACE evolution loop with token counting
- [ ] Document tokens per Generator/Reflector/Curator call
- [ ] Calculate cost per evolution at current OpenAI prices
- [ ] Create pricing model recommendations

---

## Week 2: MCP Server

### 2.1 MCP Server Core
**File:** `platform/mcp/server.py`

Implement MCP server using the Python MCP SDK:

**Tasks:**
- [ ] Install and configure `mcp` package
- [ ] Create MCP server entry point
- [ ] Implement authentication middleware (API key based)
- [ ] Set up server configuration (host, port, transport)

### 2.2 MCP Tools Implementation
**File:** `platform/mcp/tools.py`

Implement the four core MCP tools:

#### `get_playbook`
```python
Parameters:
  - playbook_id: str (required)
  - section: str (optional)
Returns: Playbook content as structured text
```

#### `report_outcome`
```python
Parameters:
  - playbook_id: str (required)
  - task_description: str (required)
  - outcome: "success" | "failure" | "partial" (required)
  - reasoning_trace: str (optional)
  - notes: str (optional)
Returns: { outcome_id: str, status: "recorded" }
```

#### `list_playbooks`
```python
Parameters:
  - include_starters: bool (optional, default: true)
Returns: Array of { id, name, description, last_updated, bullet_count }
```

#### `trigger_evolution`
```python
Parameters:
  - playbook_id: str (required)
Returns: { job_id: str, status: str, estimated_completion: str }
```

**Tasks:**
- [ ] Implement `get_playbook` tool with section filtering
- [ ] Implement `report_outcome` tool with database persistence
- [ ] Implement `list_playbooks` tool with starter playbook inclusion
- [ ] Implement `trigger_evolution` tool that queues Celery job
- [ ] Add input validation for all tools
- [ ] Add error handling and meaningful error messages

### 2.3 LLM Proxy Layer
**File:** `platform/core/llm_proxy.py`

Wrap LLM calls to add metering:

**Tasks:**
- [ ] Create `MeteredLLMClient` that wraps OpenAI client
- [ ] Count tokens for each request/response
- [ ] Log usage to `UsageRecord` table
- [ ] Associate usage with user and playbook

### 2.4 MCP Integration Testing

**Tasks:**
- [ ] Test MCP server connection with `mcp` CLI tools
- [ ] Test with Claude Code as MCP client
- [ ] Document MCP integration steps
- [ ] Create example agent configuration

---

## Week 3: Dashboard & Workers

### 3.1 FastAPI Application
**File:** `platform/api/main.py`

**Tasks:**
- [ ] Set up FastAPI application with CORS
- [ ] Configure middleware (logging, error handling)
- [ ] Set up dependency injection (`platform/api/deps.py`)
- [ ] Create health check endpoint

### 3.2 Authentication
**File:** `platform/api/routes/auth.py`

**Tasks:**
- [ ] Implement JWT-based authentication
- [ ] Create `/auth/register` endpoint
- [ ] Create `/auth/login` endpoint
- [ ] Create `/auth/me` endpoint
- [ ] Add password hashing (bcrypt)
- [ ] Create auth dependency for protected routes

### 3.3 Playbook API Routes
**File:** `platform/api/routes/playbooks.py`

```
GET    /playbooks           - List user's playbooks
POST   /playbooks           - Create new playbook
GET    /playbooks/{id}      - Get playbook details
PUT    /playbooks/{id}      - Update playbook metadata
DELETE /playbooks/{id}      - Delete playbook
GET    /playbooks/{id}/outcomes - List outcomes for playbook
GET    /playbooks/{id}/evolutions - List evolution history
```

**Tasks:**
- [ ] Implement CRUD endpoints for playbooks
- [ ] Add pagination for list endpoints
- [ ] Include outcome counts and evolution status in responses

### 3.4 Background Workers
**File:** `platform/workers/evolution_worker.py`

**Tasks:**
- [ ] Set up Celery application with Redis backend
- [ ] Create `process_evolution` task
- [ ] Implement automatic evolution triggering (threshold-based)
- [ ] Add task status tracking
- [ ] Handle failures gracefully with retries

### 3.5 Web Dashboard (Minimal MVP)
**Directory:** `web/`

For MVP, use server-rendered templates (Jinja2) or a simple React SPA:

**Pages needed:**
- Login / Register
- Dashboard (list playbooks, usage summary)
- Playbook Detail (content, outcomes, evolution history)
- Usage & Billing

**Tasks:**
- [ ] Choose frontend approach (templates vs React)
- [ ] Implement login/register pages
- [ ] Implement dashboard with playbook list
- [ ] Implement playbook detail view
- [ ] Add basic usage statistics display

### 3.6 Starter Playbooks
**Directory:** `playbooks/`

**Tasks:**
- [ ] Create `coding_agent.md` starter playbook
- [ ] Seed starter playbooks in database on startup
- [ ] Mark starter playbooks as system-owned (not editable)

---

## Week 4: Billing & Launch

### 4.1 Stripe Integration
**File:** `platform/core/billing.py`

**Tasks:**
- [ ] Set up Stripe products and prices
- [ ] Implement subscription creation flow
- [ ] Create webhook handler for Stripe events
- [ ] Implement usage-based billing for LLM tokens
- [ ] Add billing status to user model

### 4.2 Metering System
**File:** `platform/core/metering.py`

**Tasks:**
- [ ] Aggregate usage records for billing
- [ ] Create usage reporting endpoint for dashboard
- [ ] Implement usage limits based on subscription tier

### 4.3 API Routes for Billing
**File:** `platform/api/routes/billing.py`

```
GET  /billing/subscription    - Get current subscription status
POST /billing/subscribe       - Create checkout session
GET  /billing/usage           - Get usage summary
POST /billing/webhook         - Stripe webhook handler
```

**Tasks:**
- [ ] Implement billing endpoints
- [ ] Add subscription status checks to protected routes

### 4.4 Deployment
**Files:** `Dockerfile`, `docker-compose.yml`, `fly.toml`

**Tasks:**
- [ ] Create production Dockerfile
- [ ] Set up docker-compose for local development
- [ ] Create Fly.io configuration
- [ ] Deploy PostgreSQL (Fly Postgres or managed)
- [ ] Deploy Redis (Upstash or Fly)
- [ ] Deploy API server
- [ ] Deploy MCP server
- [ ] Deploy Celery workers
- [ ] Set up environment variables in production

### 4.5 Documentation

**Tasks:**
- [ ] Write MCP integration guide
- [ ] Document API endpoints
- [ ] Create quick start guide
- [ ] Add troubleshooting section

### 4.6 End-to-End Testing

**Tasks:**
- [ ] Test full flow: register → create playbook → MCP get_playbook → report_outcome → evolution
- [ ] Test billing flow
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
├── platform/
│   ├── __init__.py
│   ├── config.py                # Pydantic settings
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app
│   │   ├── deps.py              # Dependencies (db session, current user)
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── playbooks.py
│   │   │   └── billing.py
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── auth.py          # Pydantic schemas for auth
│   │       ├── playbooks.py     # Pydantic schemas for playbooks
│   │       └── billing.py       # Pydantic schemas for billing
│   │
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── server.py            # MCP server entry point
│   │   ├── tools.py             # Tool implementations
│   │   └── auth.py              # MCP authentication
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── playbooks.py         # Playbook business logic
│   │   ├── evolution.py         # ACE wrapper for evolution
│   │   ├── llm_proxy.py         # Metered LLM client
│   │   ├── metering.py          # Usage tracking
│   │   └── billing.py           # Stripe integration
│   │
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py            # SQLAlchemy models
│   │   ├── session.py           # Database session management
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
│   ├── templates/               # If using Jinja2
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
├── .env.example
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── fly.toml
└── README.md
```

---

## Dependencies to Add

```toml
# pyproject.toml additions
[project.dependencies]
# Already listed in pyproject.toml:
# fastapi, uvicorn, sqlalchemy, alembic, psycopg2-binary, stripe, mcp, celery, redis

# Additional needed:
python-jose = "^3.3.0"        # JWT tokens
passlib = "^1.7.4"            # Password hashing
bcrypt = "^4.1.0"             # Bcrypt backend for passlib
python-multipart = "^0.0.6"   # Form data parsing
jinja2 = "^3.1.0"             # Templates (if using SSR)
httpx = "^0.26.0"             # Async HTTP client
```

---

## Key Integration Points

### ACE Core → Platform

The platform wraps `ace_core` through `platform/core/evolution.py`:

```python
from ace_core.ace.ace import ACE
from ace_core.ace.core.reflector import Reflector
from ace_core.ace.core.curator import Curator

class EvolutionService:
    def evolve_playbook(self, playbook_content: str, outcomes: list[Outcome]) -> EvolutionResult:
        # 1. Initialize Reflector with metered LLM client
        # 2. For each outcome, run reflection to tag bullets
        # 3. Initialize Curator with accumulated feedback
        # 4. Run curation to update playbook
        # 5. Return new playbook + token usage
```

### MCP → Database

MCP tools interact with the database through the core services:

```python
# platform/mcp/tools.py
from platform.core.playbooks import PlaybookService
from platform.db.session import get_db

@mcp.tool()
async def get_playbook(playbook_id: str, section: str = None):
    async with get_db() as db:
        service = PlaybookService(db)
        return await service.get_playbook(playbook_id, section)
```

---

## Success Criteria

By end of Week 4:

- [ ] User can register and log in via dashboard
- [ ] User can create/view/delete playbooks via dashboard
- [ ] MCP server responds to all four tool calls
- [ ] Outcomes are recorded and trigger evolution
- [ ] Evolution jobs process successfully
- [ ] Token usage is tracked and displayed
- [ ] Stripe subscription flow works
- [ ] Platform deployed and accessible
- [ ] Documentation complete

---

## Risk Mitigations

| Risk | Mitigation |
|------|------------|
| Token costs too high | Implement rate limiting; set minimum outcome batch size for evolution |
| MCP integration issues | Test early in Week 2; have REST API fallback ready |
| Evolution quality | Use existing ACE defaults; defer quality tuning to post-MVP |
| Scope creep | Strictly follow MVP scope; defer versioning, teams, sharing |

---

## Commands Reference

```bash
# Development
docker-compose up -d postgres redis    # Start services
alembic upgrade head                    # Run migrations
uvicorn platform.api.main:app --reload  # Start API server
python -m platform.mcp.server           # Start MCP server
celery -A platform.workers.celery_app worker --loglevel=info  # Start worker

# Testing
pytest tests/ -v                        # Run tests
pytest tests/test_mcp/ -v              # Run MCP tests only

# Production
fly deploy                              # Deploy to Fly.io
fly logs                                # View logs
```
