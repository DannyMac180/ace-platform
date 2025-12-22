# ACE Platform Architecture

## High-Level Overview

```mermaid
flowchart TB
    subgraph Clients["Clients"]
        Browser["Web Browser"]
        Claude["Claude Code / MCP Client"]
    end

    subgraph Platform["ace_platform"]
        subgraph API["FastAPI Application :8000"]
            Routes["API Routes"]
            Auth["JWT Auth"]
            MCPServer["MCP Server"]
            APIKeyAuth["API Key Auth"]
        end

        subgraph Core["Core Services"]
            PlaybookService["PlaybookService"]
            EvolutionService["EvolutionService"]
            MeteredLLM["MeteredLLMClient"]
            Metering["Metering"]
            Billing["Billing (optional)"]
        end

        subgraph Workers["Celery Workers"]
            EvolutionWorker["evolution_worker"]
            ScheduledTasks["Scheduled Tasks"]
        end
    end

    subgraph ACECore["ace_core (upstream)"]
        Generator["Generator Agent"]
        Reflector["Reflector Agent"]
        Curator["Curator Agent"]
    end

    subgraph Data["Data Stores"]
        Postgres[(PostgreSQL)]
        Redis[(Redis)]
    end

    subgraph External["External Services"]
        OpenAI["OpenAI API"]
        Stripe["Stripe (optional)"]
    end

    Browser -->|REST + JWT| Routes
    Claude -->|MCP + API Key| MCPServer

    Routes --> Auth
    MCPServer --> APIKeyAuth

    Auth --> PlaybookService
    APIKeyAuth --> PlaybookService

    PlaybookService --> Postgres
    EvolutionService --> MeteredLLM
    MeteredLLM --> OpenAI
    MeteredLLM --> Metering
    Metering --> Postgres

    Routes -->|Queue Job| Redis
    EvolutionWorker -->|Poll Jobs| Redis
    EvolutionWorker --> EvolutionService
    EvolutionService --> ACECore

    Billing -.->|If enabled| Stripe

    ScheduledTasks -->|Check thresholds| Postgres
    ScheduledTasks -->|Trigger evolution| Redis
```

## Data Model

```mermaid
erDiagram
    User ||--o{ Playbook : owns
    User ||--o{ ApiKey : has
    User ||--o{ UsageRecord : generates

    Playbook ||--o{ PlaybookVersion : has
    Playbook ||--o{ Outcome : receives
    Playbook ||--o{ EvolutionJob : triggers
    Playbook }o--|| PlaybookVersion : current_version

    PlaybookVersion }o--o| EvolutionJob : created_by

    EvolutionJob ||--o{ Outcome : processes
    EvolutionJob ||--o{ UsageRecord : generates

    User {
        uuid id PK
        string email UK
        string hashed_password
        bool is_active
        bool email_verified
        string stripe_customer_id
        datetime created_at
        datetime updated_at
    }

    Playbook {
        uuid id PK
        uuid user_id FK
        string name
        string description
        uuid current_version_id FK
        enum status "active|archived"
        enum source "starter|user_created|imported"
        datetime created_at
        datetime updated_at
    }

    PlaybookVersion {
        uuid id PK
        uuid playbook_id FK
        int version_number
        text content
        int bullet_count
        uuid created_by_job_id FK
        string diff_summary
        datetime created_at
    }

    Outcome {
        uuid id PK
        uuid playbook_id FK
        string task_description
        enum outcome_status "success|failure|partial"
        text reasoning_trace
        text notes
        jsonb reflection_data
        datetime processed_at
        uuid evolution_job_id FK
        datetime created_at
        datetime updated_at
    }

    EvolutionJob {
        uuid id PK
        uuid playbook_id FK
        enum status "queued|running|completed|failed"
        uuid from_version_id FK
        uuid to_version_id FK
        int outcomes_processed
        datetime started_at
        datetime completed_at
        text error_message
        jsonb token_totals
        string ace_core_version
        datetime created_at
    }

    UsageRecord {
        uuid id PK
        uuid user_id FK
        uuid playbook_id FK
        uuid evolution_job_id FK
        string operation
        string model
        int prompt_tokens
        int completion_tokens
        int total_tokens
        decimal cost_usd
        string request_id
        jsonb metadata
        datetime created_at
    }

    ApiKey {
        uuid id PK
        uuid user_id FK
        string name
        string key_prefix
        string hashed_key
        jsonb scopes
        datetime last_used_at
        datetime revoked_at
        datetime created_at
    }
```

## Request Flow: MCP Tool Call

```mermaid
sequenceDiagram
    participant Client as Claude Code
    participant MCP as MCP Server
    participant Auth as API Key Auth
    participant Service as PlaybookService
    participant DB as PostgreSQL
    participant Worker as Celery Worker
    participant Redis as Redis Queue

    Client->>MCP: report_outcome(playbook_id, outcome_data)
    MCP->>Auth: Validate API Key
    Auth->>DB: Lookup hashed key, check scopes
    DB-->>Auth: Key valid, scopes OK
    Auth->>DB: Update last_used_at
    Auth-->>MCP: User context

    MCP->>Service: create_outcome(user_id, playbook_id, data)
    Service->>DB: Verify playbook ownership
    Service->>DB: INSERT outcome
    Service->>DB: COUNT unprocessed outcomes
    DB-->>Service: count = 5

    alt Threshold reached
        Service->>DB: Check for existing queued/running job
        DB-->>Service: No active job
        Service->>DB: INSERT evolution_job (status=queued)
        Service->>Redis: Enqueue process_evolution(job_id)
    end

    Service-->>MCP: {outcome_id, status, pending_outcomes}
    MCP-->>Client: Tool result

    Note over Worker,Redis: Async processing
    Worker->>Redis: Poll for jobs
    Redis-->>Worker: job_id
    Worker->>DB: SELECT ... FOR UPDATE (lock playbook)
    Worker->>DB: Load outcomes, current version
    Worker->>Worker: Run ACE evolution
    Worker->>DB: BEGIN TRANSACTION
    Worker->>DB: INSERT new PlaybookVersion
    Worker->>DB: UPDATE Playbook.current_version_id
    Worker->>DB: UPDATE Outcomes (processed_at, job_id)
    Worker->>DB: UPDATE EvolutionJob (status=completed)
    Worker->>DB: INSERT UsageRecords
    Worker->>DB: COMMIT
```

## Evolution Concurrency Control

```mermaid
flowchart TD
    subgraph Trigger["trigger_evolution(playbook_id)"]
        A[Receive request] --> B{Check for active job}
        B -->|EXISTS queued/running| C[Return existing job_id]
        C --> D[is_new = false]
        B -->|No active job| E[Create new job]
        E --> F[Queue to Celery]
        F --> G[Return new job_id]
        G --> H[is_new = true]
    end

    subgraph Constraint["Database Constraint"]
        I["UNIQUE INDEX ON (playbook_id)<br/>WHERE status IN ('queued', 'running')"]
    end

    subgraph Worker["Evolution Worker"]
        J[Dequeue job] --> K[SELECT ... FOR UPDATE]
        K --> L[Lock playbook row]
        L --> M[Run evolution]
        M --> N{Success?}
        N -->|Yes| O[Create version + commit]
        N -->|No| P[Mark failed + retry]
    end

    Trigger -.->|Enforced by| Constraint
    Worker -.->|Enforced by| Constraint
```

## Authentication Flow

```mermaid
flowchart LR
    subgraph Web["Web Dashboard"]
        Login["/auth/login"] --> JWT["JWT Token"]
        JWT --> Access["Access Token<br/>(30 min)"]
        JWT --> Refresh["Refresh Token<br/>(7 days)"]
        Access --> Protected["Protected Routes"]
        Refresh --> RefreshEndpoint["/auth/refresh"]
        RefreshEndpoint --> Access
    end

    subgraph MCP["MCP Clients"]
        APIKey["API Key"] --> Hash["bcrypt hash lookup"]
        Hash --> Scopes["Check scopes"]
        Scopes --> MCPTools["MCP Tools"]
    end

    subgraph KeyMgmt["API Key Management"]
        Create["/auth/api-keys POST"] --> ShowOnce["Show full key ONCE"]
        List["/auth/api-keys GET"] --> PrefixOnly["Show prefix only"]
        Revoke["/auth/api-keys DELETE"] --> SetRevoked["Set revoked_at"]
    end
```

## Directory Structure

```
ace-platform/
├── ace_core/                    # Upstream ACE (Generator, Reflector, Curator)
│   ├── ace/
│   │   ├── core/
│   │   │   ├── generator.py
│   │   │   ├── reflector.py
│   │   │   └── curator.py
│   │   └── ace.py
│   ├── llm.py
│   └── playbook_utils.py
│
├── ace_platform/                # Hosted platform layer
│   ├── api/
│   │   ├── main.py              # FastAPI app entry
│   │   ├── deps.py              # Dependency injection
│   │   ├── middleware.py        # Logging, rate limiting, correlation IDs
│   │   ├── routes/
│   │   │   ├── auth.py          # JWT + API key endpoints
│   │   │   ├── playbooks.py     # CRUD + versions + outcomes
│   │   │   └── billing.py       # Stripe (optional)
│   │   └── schemas/             # Pydantic request/response models
│   │
│   ├── mcp/
│   │   ├── server.py            # MCP server entry
│   │   ├── tools.py             # 5 MCP tools
│   │   └── auth.py              # API key middleware
│   │
│   ├── core/
│   │   ├── playbooks.py         # Business logic
│   │   ├── evolution.py         # Wraps ace_core
│   │   ├── llm_proxy.py         # Metered OpenAI client
│   │   ├── metering.py          # Usage tracking
│   │   ├── billing.py           # Stripe (optional)
│   │   ├── security.py          # Rate limiting, validation
│   │   ├── logging.py           # Structured JSON logging
│   │   └── metrics.py           # Basic metrics
│   │
│   ├── db/
│   │   ├── models.py            # SQLAlchemy models
│   │   ├── session.py           # Async + Sync session factories
│   │   └── migrations/          # Alembic
│   │
│   ├── workers/
│   │   ├── celery_app.py        # Celery config
│   │   └── evolution_worker.py  # Background tasks
│   │
│   └── config.py                # Pydantic Settings
│
├── web/
│   ├── templates/               # Jinja2 templates
│   └── static/                  # CSS, JS
│
├── playbooks/                   # Starter playbooks
├── tests/
├── docs/
├── docker-compose.yml
├── Dockerfile
└── fly.toml
```

## Deployment Architecture

```mermaid
flowchart TB
    subgraph Internet
        Users["Users"]
    end

    subgraph Fly["Fly.io"]
        subgraph Web["Web Machines"]
            API1["API + MCP<br/>Instance 1"]
            API2["API + MCP<br/>Instance 2"]
        end

        subgraph Workers["Worker Machines"]
            W1["Celery Worker 1"]
            W2["Celery Worker 2"]
        end

        LB["Load Balancer"]
    end

    subgraph Managed["Managed Services"]
        FlyPG["Fly Postgres"]
        Upstash["Upstash Redis"]
    end

    subgraph External["External"]
        OpenAI["OpenAI API"]
        Stripe["Stripe"]
    end

    Users --> LB
    LB --> API1
    LB --> API2

    API1 --> FlyPG
    API2 --> FlyPG
    API1 --> Upstash
    API2 --> Upstash

    W1 --> FlyPG
    W2 --> FlyPG
    W1 --> Upstash
    W2 --> Upstash

    W1 --> OpenAI
    W2 --> OpenAI

    API1 -.-> Stripe
    API2 -.-> Stripe
```

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Web Framework | FastAPI | Async support, auto OpenAPI docs, Pydantic integration |
| Database | PostgreSQL | JSONB for flexible fields, partial indexes, transactions |
| Task Queue | Celery + Redis | Mature, reliable, good monitoring |
| Web Tier DB | AsyncSession (asyncpg) | High concurrency for I/O-bound API calls |
| Worker DB | Sync Session (psycopg2) | Simpler for CPU-bound evolution tasks |
| Web Auth | JWT (access + refresh) | Stateless, standard for web apps |
| MCP Auth | Hashed API Keys | Simple for programmatic access, revocable |
| Frontend | Jinja2 Templates | Faster MVP than React SPA |
| Versioning | Immutable PlaybookVersion | Full history, easy rollback, audit trail |
| Concurrency | Partial unique index | Database-enforced single active evolution |
| Billing | Feature-flagged | Optional for self-hosted deployments |
