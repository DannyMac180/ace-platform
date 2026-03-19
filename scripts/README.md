# ACE Platform Scripts

Utility scripts for development, testing, and operations.

## Symphony

### run-symphony.sh

Start the vendored Symphony runtime with the repo-local virtualenv launcher and a local
`WORKFLOW.md`.

#### Prerequisites

```bash
source venv/bin/activate && pip install -e .
source venv/bin/activate && symphony setup
cp WORKFLOW.example.md WORKFLOW.md
```

Before running, edit `WORKFLOW.md` to set:

- your Linear `project_slug`
- your preferred Symphony workspace root
- the repo clone URL Symphony should use for ticket workspaces

You also need:

- `LINEAR_API_KEY` in your shell
- `codex` on your `PATH`
- `mise` installed
- a Linear token that resolves to workspace `danmac` and a project attached to team `DAN`

#### Usage

```bash
./scripts/run-symphony.sh
```

The script starts the dashboard at `http://127.0.0.1:4000/` by default.
Before launch, it validates that `LINEAR_API_KEY` points at the expected Linear
workspace and that the configured workflow project belongs to the expected team.
By default this repo expects workspace URL key `danmac` and team key `DAN`.

Override the port with:

```bash
SYMPHONY_PORT=4001 ./scripts/run-symphony.sh
```

If you intentionally need to repoint the guard for another workspace or team:

```bash
SYMPHONY_LINEAR_WORKSPACE_URL_KEY=your-workspace \
SYMPHONY_LINEAR_TEAM_KEY=ENG \
./scripts/run-symphony.sh
```

### launch-app

Runtime validation wrapper for app-touching Symphony tasks.

The wrapper can start the local backend and frontend, wait for them to become
reachable, fetch one or more frontend routes, and write a manifest plus captured
artifacts under `.artifacts/launch-app/`.

Example:

```bash
./scripts/launch-app \
  --start-backend \
  --start-frontend \
  --replace-frontend \
  --route / \
  --route /pricing \
  --issue DAN-35
```

Notes:

- Artifacts always include `manifest.json`.
- If a headless Chrome/Chromium executable is available, the wrapper also saves
  PNG screenshots for each route.
- If no browser executable is available, the wrapper still saves HTML/JSON/text
  snapshots and records the screenshot limitation in the manifest.

### github-pr-media

Upload runtime artifacts to the associated Linear issue and link them from the
current PR.

The wrapper:

1. reads the artifacts from `.artifacts/launch-app/`
2. uploads them to Linear private storage using `LINEAR_API_KEY`
3. creates issue attachments and a Linear issue comment summarizing the files
4. posts a GitHub PR comment linking back to the Linear issue/comment and the
   uploaded asset URLs

Example:

```bash
LINEAR_API_KEY=lin_api_xxx ./scripts/github-pr-media \
  --issue DAN-35 \
  --pr 243 \
  --summary "Validated the updated usage page locally."
```

Notes:

- By default the wrapper infers the Linear issue from the current Symphony
  workspace path or branch name.
- Linear asset URLs require Linear authentication outside the Linear app, so the
  PR comment links both the Linear issue and the uploaded files.

## Load Testing

### load_test_mcp.py

Load testing script for the ACE Platform MCP server and API endpoints.

#### Prerequisites

```bash
pip install httpx
```

#### Usage

```bash
# Basic test (10 concurrent users, 100 requests)
python scripts/load_test_mcp.py

# Custom concurrent users and requests
python scripts/load_test_mcp.py --users 50 --requests 500

# Test against production
python scripts/load_test_mcp.py --host https://your-ace-platform.fly.dev

# Run specific test
python scripts/load_test_mcp.py --test health
python scripts/load_test_mcp.py --test list_playbooks
python scripts/load_test_mcp.py --test ramp_up

# Ramp-up test to find breaking point
python scripts/load_test_mcp.py --test ramp_up --ramp-max-users 100
```

#### Options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `http://localhost:8001` | MCP server URL |
| `--api-key` | `$API_KEY` | API key for authentication |
| `--users` | `10` | Number of concurrent users |
| `--requests` | `100` | Total number of requests |
| `--test` | `all` | Test to run: `health`, `list_playbooks`, `ramp_up`, `all` |
| `--ramp-max-users` | `50` | Maximum users for ramp-up test |

#### Output Metrics

The script reports:

- **Success Rate**: Percentage of successful requests
- **Requests/second**: Throughput
- **Response Times**: Average, median (p50), p95, p99, min, max

#### Example Output

```
============================================================
Load Test Results: Health Check
============================================================
Total Requests:     100
Successful:         100
Failed:             0
Success Rate:       100.0%
Total Duration:     2.45s
Requests/second:    40.8

Response Times:
  Average:          24.5ms
  Median (p50):     22.1ms
  95th percentile:  38.7ms
  99th percentile:  45.2ms
  Min:              18.3ms
  Max:              52.1ms
============================================================
```

#### Interpreting Results

| Metric | Good | Warning | Critical |
|--------|------|---------|----------|
| Success Rate | > 99% | 95-99% | < 95% |
| p95 Response Time | < 100ms | 100-500ms | > 500ms |
| Requests/second | > 100 | 50-100 | < 50 |

#### Running Before Deployment

Before deploying to production, run load tests to ensure:

1. **Health check works under load**:
   ```bash
   python scripts/load_test_mcp.py --test health --users 50 --requests 500
   ```

2. **API endpoints handle concurrent users**:
   ```bash
   python scripts/load_test_mcp.py --test list_playbooks --users 20 --requests 200
   ```

3. **Find breaking point with ramp-up**:
   ```bash
   python scripts/load_test_mcp.py --test ramp_up --ramp-max-users 100
   ```

## Sentry Project Audit

### sentry_project_audit.py

Generate an authenticated audit snapshot of Sentry project controls used by the ACE
platform observability runbook.

The script checks:

- Project lookup by org/project slug
- DSN key availability
- Inbound filter data is visible
- Alert rules
- Ownership rules

Required environment variables:

- `SENTRY_AUTH_TOKEN` (Sentry API token with project read access)
- `SENTRY_ORG` (organization slug)
- `SENTRY_PROJECT` (project slug)

Example:

```bash
export SENTRY_AUTH_TOKEN="sntrys_xxx"
export SENTRY_ORG="aceplatform"
export SENTRY_PROJECT="ace-platform"

python scripts/sentry_project_audit.py --require-alert-rules --strict
```

Non-zero exit codes indicate required controls are missing.
