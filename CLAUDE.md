# ACE Platform

A hosted "Playbooks as a Service" platform built on the ACE (Autonomous Capability Enhancement) three-agent architecture.

## Architecture Overview

- **ace_core/**: Core ACE implementation (Generator, Reflector, Curator agents)
- **platform/**: Hosted platform layer (FastAPI API, MCP server, Celery workers)
- **web/**: Dashboard frontend
- **playbooks/**: Starter playbook templates

## Development Setup

### Prerequisites

- Python 3.10+
- Docker & Docker Compose (for PostgreSQL and Redis)
- OpenAI API key

### Quick Start

```bash
# 1. Clone and enter the project
cd ace-platform

# 2. Start infrastructure services
docker-compose up -d postgres redis

# 3. Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 4. Install dependencies
pip install -e ".[dev]"

# 5. Set up environment variables
cp .env.example .env
# Edit .env with your API keys and database URLs

# 6. Run database migrations
alembic upgrade head

# 7. Start the development servers (in separate terminals)
uvicorn platform.api.main:app --reload          # API server (port 8000)
python -m platform.mcp.server                    # MCP server
celery -A platform.workers.celery_app worker -l info  # Background worker
```

### Environment Variables

Required in `.env`:
```
DATABASE_URL=postgresql://user:pass@localhost:5432/ace_platform
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=sk-...
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
JWT_SECRET_KEY=your-secret-key
```

### Running ACE Core Standalone

The `ace_core/` module can run independently for testing:

```bash
cd ace_core
source venv/bin/activate
python -m finance.run --task_name finer --mode offline --save_path results
```

### Testing

All new code written should have accompanying unit and integration tests.

```bash
# Run all tests
pytest tests/ -v

# Run specific test suites
pytest tests/test_api/ -v      # API tests
pytest tests/test_mcp/ -v      # MCP server tests
pytest tests/test_evolution/ -v # Evolution logic tests

# With coverage
pytest --cov=platform tests/
```

### Code Quality

```bash
# Linting
ruff check .

# Format
ruff format .
```

## Key Commands

| Command | Description |
|---------|-------------|
| `docker-compose up -d` | Start PostgreSQL and Redis |
| `alembic upgrade head` | Run database migrations |
| `alembic revision --autogenerate -m "msg"` | Create new migration |
| `uvicorn platform.api.main:app --reload` | Start API server |
| `python -m platform.mcp.server` | Start MCP server |
| `celery -A platform.workers.celery_app worker -l info` | Start Celery worker |
| `pytest tests/ -v` | Run tests |

---

# Project Management

This project uses the beads CLI 'bd' for issue and project tracking.

1. File/update issues for remaining work

Agents should proactively create issues for discovered bugs, TODOs, and follow-up tasks
Close completed issues and update status for in-progress work
2. Run quality gates (if applicable)

Tests, linters, builds - only if code changes were made
File P0 issues if builds are broken
3. Sync the issue tracker carefully

Work methodically to ensure local and remote issues merge safely
Handle git conflicts thoughtfully (sometimes accepting remote and re-importing)
Goal: clean reconciliation where no issues are lost
4. Verify clean state

All changes committed and pushed
No untracked files remain
5. Choose next work

Provide a formatted prompt for the next session with context.

## Context management

You are a LLM and therefore don't always have up to date knowledge in your internal knowledge. Due to this, always gather context about specific libraries, frameworks, technologies or coding patterns before generating files or writing code. This allows your output to be much more accurate and higher quality. Use the context7 MCP to do this when possible and use web search when context7 doesn't have the info you need.