<p align="center">
  <img src="web/public/ace-favicon.svg" alt="ACE logo" width="72" />
</p>

<h1 align="center">ACE</h1>

<p align="center">
  <strong>Your AI workflow gets better after every task.</strong>
</p>

<p align="center">
  ACE turns one-off prompts into evolving playbooks. It captures what worked, what failed, and what to improve so your assistant becomes more reliable with real use.
</p>

<p align="center">
  <a href="https://aceagent.io">Hosted Agent</a>
  ·
  <a href="https://app.aceagent.io">Dashboard</a>
  ·
  <a href="https://docs.aceagent.io">Docs</a>
  ·
  <a href="docs/SELF_HOSTED_DEPLOYMENT.md">Self-Host Guide</a>
  ·
  <a href="https://buy.stripe.com/5kQ4gz3b460X8zsh1g8so00">Support ACE Open-Source</a>
</p>

<p align="center">
  <a href="https://github.com/DannyMac180/ace-platform/actions/workflows/ci.yml"><img src="https://github.com/DannyMac180/ace-platform/actions/workflows/ci.yml/badge.svg" alt="CI status" /></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-1f3b5c" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/license-Apache%202.0-b8860b" alt="Apache 2.0 license" />
</p>

![ACE social card](web/public/ace-social-card.png)

## What ACE Does

ACE is the open-source platform for self-improving AI agents.

Instead of treating prompts like disposable text, ACE treats instructions as living playbooks:

- Create structured playbooks for coding, research, writing, analysis, and operations
- Connect those playbooks to MCP-compatible tools like Claude Code, Codex, and custom clients
- Record outcomes from real work so useful patterns are not lost
- Automatically evolve playbooks into better versions over time

The result is simple: less prompt drift, fewer repeated mistakes, and better first-pass output.

## Why People Use ACE

- **Capture wins permanently**: turn a good run into reusable guidance instead of hoping the next session goes the same way
- **Learn from failure**: record misses, edge cases, and postmortems directly into the system that guides future work
- **Improve with real usage**: evolve playbooks from actual execution history rather than abstract best-practice docs
- **Stay tool-agnostic**: use ACE anywhere MCP fits into your workflow

ACE is also available as a hosted agent at [aceagent.io](https://aceagent.io), with the dashboard at [app.aceagent.io](https://app.aceagent.io) and documentation at [docs.aceagent.io](https://docs.aceagent.io).

## Start Here

ACE currently supports two clear starting paths:

- **Use ACE Cloud** if you want the fastest hosted path with no local infrastructure.
- **Use ACE OSS / self-managed ACE** if you want the local engine, local API/MCP runtime, or your own deployment.

### Hosted ACE Cloud

If you want to use ACE right away, the fastest path is the hosted service:

1. Create an account at [app.aceagent.io](https://app.aceagent.io).
2. Generate an API key with the scopes you need.
3. Connect ACE to your agent over MCP.

Example for Claude Code:

```bash
claude mcp add --transport http ace https://aceagent.io/mcp \
  --header "X-API-Key: YOUR_API_KEY"
```

Legacy SSE compatibility remains available at `https://aceagent.io/mcp/sse` through **May 22, 2026**.

Helpful links:

- [Hosted quick start](docs/QUICKSTART.md)
- [Docs site quick start](https://docs.aceagent.io/docs/getting-started/quick-start/)
- [Claude Code setup](https://docs.aceagent.io/docs/developer-guides/mcp-integration/claude-code/)
- [MCP integration guide](docs/MCP_INTEGRATION.md)

### ACE OSS And Self-Managed Start

If you want the open-source path, start with these docs in this order:

1. [OSS overview](docs/oss-overview.md) for what is public OSS versus hosted/private cloud value.
2. [Local quickstart](docs/local-quickstart.md) for the fastest self-managed setup.
3. [Self-hosted deployment guide](docs/SELF_HOSTED_DEPLOYMENT.md) if you want the full ACE platform stack on your own infrastructure.

## OSS Versus Hosted

ACE is being split into a genuinely useful OSS core plus hosted cloud services.
The rule from the product spec and ADR is simple: local single-user capability
must remain usable without ACE-operated services, while premium hosted value
comes from server-side services ACE runs.

| Offer | What you get |
| --- | --- |
| **ACE OSS** | Local playbook engine, local/self-managed runtime, BYO model keys, self-managed storage and operations |
| **ACE Cloud Personal** | Hosted convenience for one user: managed runtime, cloud sync, backups, hosted evals, managed inference |
| **ACE Cloud Team** | Shared workspaces, invites, approvals, team governance, and collaboration workflows |
| **ACE Enterprise** | Private deployment options, governance controls, and enterprise operations/support |

The full boundary and current extraction state are documented in
[docs/oss-overview.md](docs/oss-overview.md) and
[docs/adr/0001-oss-core-vs-cloud-boundary.md](docs/adr/0001-oss-core-vs-cloud-boundary.md).

## Repository Layout Today

This repository is still the transition workspace for the OSS/core versus cloud
split. Some public-runtime and cloud-only code still live side by side, so the
supported boundary is defined by capability, not only by folder name.

| Path | Current role |
| --- | --- |
| `packages/ace-core/` | Extracted public OSS package for the ACE engine and shared domain logic |
| `ace_core/` | Legacy public core tree retained during extraction and compatibility work |
| `ace_platform/` | Transitional runtime/control-plane workspace: includes local CLI/API/MCP entrypoints plus cloud-oriented services that are still being separated |
| `web/` | Cloud dashboard frontend and hosted web UX |
| `playbooks/` | Public starter playbooks and portability assets |
| `docs/` | Public docs, install docs, and architecture/boundary references |

Target package layout from the next-iteration product spec:

```text
packages/
  ace-core/
  ace-cli/
  ace-local-server/
  ace-mcp/
  ace-protocol/
  ace-provider-openai/
  ace-provider-anthropic/
examples/
  starter-project/
  benchmark-demo/
docs/
  oss-overview.md
  local-quickstart.md
```

## Symphony

Symphony is repo development tooling for ACE contributors and operators. It is
not the primary entry point for external OSS users evaluating the product split
or the initial local install path.

This repo now vendors the official OpenAI Elixir Symphony implementation under `vendor/symphony-elixir/`.
Use the existing `symphony` command as a thin launcher for that runtime.

Prerequisites:

- `LINEAR_API_KEY` set in your shell
- Codex MCP server named `ace` configured for the same shell user that runs Symphony
- `codex` available in your `PATH`
- [`mise`](https://mise.jdx.dev/) installed for the Elixir/Erlang toolchain
- a Linear token that resolves to workspace `danmac` for this repo's default Symphony setup

Local setup:

```bash
source venv/bin/activate && pip install -e .
source venv/bin/activate && symphony setup
export ACE_API_KEY=your_ace_api_key
codex mcp add ace --url https://aceagent.io/mcp --bearer-token-env-var ACE_API_KEY
cp WORKFLOW.example.md WORKFLOW.local.md
# Edit WORKFLOW.local.md for your Linear project, workspace root, and repo clone URL
./scripts/run-symphony.sh
```

Use [WORKFLOW.example.md](WORKFLOW.example.md) as the committed template for your local
`WORKFLOW.local.md`. The local workflow files are intentionally gitignored so each developer can point
Symphony at their own Linear project, workspace root, and fork or clone URL without losing those settings
on pulls or merges. The launcher script builds a runtime workflow by combining the tracked
`WORKFLOW.example.md` with your local frontmatter overrides, so shared workflow logic changes still
flow through after a pull while machine-specific settings stay local.

Notes:

- `WORKFLOW.example.md` includes the fields you must customize before your first run.
- `WORKFLOW.example.md` now requires ACE on every ticket run: Symphony must call `ace.find_playbook`,
  `ace.get_playbook`, and `ace.record_outcome` instead of treating ACE as optional.
- Keep your machine-specific Symphony config in `WORKFLOW.local.md`, not by editing the tracked example.
- `WORKFLOW.local.md` should be treated as local frontmatter overrides for the tracked example workflow.
- The tracked example includes a `before_run` repair hook that normalizes partially initialized
  workspaces before Codex starts, including nested `repo/` checkouts and checkout-free directories
  that only contain a `venv`.
- `scripts/run-symphony.sh` uses the repo-local `venv/bin/symphony` launcher directly instead of relying on shell activation.
- `scripts/run-symphony.sh` fails fast unless both `LINEAR_API_KEY` and `ACE_API_KEY` are set, and `codex mcp list`
  shows a server named `ace`.
- `scripts/run-symphony.sh` also validates that `LINEAR_API_KEY` resolves to the expected Linear workspace and that
  the configured workflow project belongs to the expected team before Symphony starts.
- The script starts the observability dashboard on `http://127.0.0.1:4000/`.
- Override the dashboard port with `SYMPHONY_PORT=4001 ./scripts/run-symphony.sh` if needed.
- Override the workspace/team guard only if you are intentionally repointing the setup:
  `SYMPHONY_LINEAR_WORKSPACE_URL_KEY=your-workspace SYMPHONY_LINEAR_TEAM_KEY=ENG ./scripts/run-symphony.sh`.
- Local open-source Symphony development currently expects a Linear project and `LINEAR_API_KEY`.
- The hosted ACE setup above expects `ACE_API_KEY` in the shell before Codex starts. ACE accepts both
  `X-API-Key` and `Authorization: Bearer`; Codex's HTTP MCP configuration uses the bearer-token path.
- If you prefer a local ACE server instead of `https://aceagent.io/mcp`, configure Codex with
  `codex mcp add ace --env ACE_API_KEY=$ACE_API_KEY --env DATABASE_URL=postgresql://... --env REDIS_URL=redis://... -- python -m ace_platform.mcp.server stdio`.
- If you want Symphony-created branches or PRs to push to your fork, make sure the clone URL in
  `WORKFLOW.local.md` and your local git auth are configured for that fork.
- If you add SSH worker hosts later, repeat the `codex mcp add ace ...` setup on every worker host.

## Full Self-Managed Platform Setup

```bash
git clone https://github.com/DannyMac180/ace-platform.git
cd ace-platform
cp .env.example .env

# Set at minimum:
# OPENAI_API_KEY=...
# JWT_SECRET_KEY=...

docker compose --profile full up -d
curl http://localhost:8000/health
```

That starts PostgreSQL, Redis, migrations, the FastAPI API, the MCP server, Celery workers, and the scheduler.

## Local Runtime Development Setup

```bash
git clone https://github.com/DannyMac180/ace-platform.git
cd ace-platform

python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
docker compose up -d postgres redis
alembic upgrade head

uvicorn ace_platform.api.main:app --reload
python -m ace_platform.mcp.server
celery -A ace_platform.workers.celery_app worker -l info
```

For the frontend:

```bash
lsof -ti :3000 | xargs kill -9 2>/dev/null
cd web
npm ci
npm run dev -- --port 3000
```

More deployment detail:

- [Self-hosted deployment guide](docs/SELF_HOSTED_DEPLOYMENT.md)
- [Environment variable reference](docs/ENVIRONMENT_VARIABLES.md)
- [Architecture overview](docs/ARCHITECTURE.md)
- [Next iteration working stream](docs/next_iteration_working_stream.md)

## Required Environment Variables

These are the minimum settings most self-hosted installations need:

| Variable | Required | What it is for |
| --- | --- | --- |
| `DATABASE_URL` | Yes | PostgreSQL connection string for workers and sync operations |
| `REDIS_URL` | Yes | Redis connection for Celery and rate limiting |
| `OPENAI_API_KEY` | Yes | Model access for playbook evolution and related LLM features |
| `JWT_SECRET_KEY` | Yes | Signing key for authentication tokens |
| `DATABASE_URL_ASYNC` | No | Async DB URL for API/MCP; auto-derived if omitted |
| `CORS_ORIGINS` | Recommended | Allowed browser origins for your frontend |
| `FRONTEND_URL` | Recommended | Public frontend URL for redirects and app links |
| `OAUTH_REDIRECT_BASE_URL` | Recommended | Base URL for OAuth callback handling |
| `SESSION_SECRET_KEY` | Recommended | Separate secret for OAuth/session cookies |

Common optional integrations:

| Variable | When you need it |
| --- | --- |
| `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` | Google login |
| `GITHUB_OAUTH_CLIENT_ID` / `GITHUB_OAUTH_CLIENT_SECRET` | GitHub login |
| `BILLING_ENABLED`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | Stripe billing |
| `SENTRY_DSN` | Error monitoring |
| `RESEND_API_KEY` | Transactional email |

Start from [.env.example](.env.example) for the full list.

## How ACE Is Organized

| Path | Purpose |
| --- | --- |
| `ace_core/` | Core ACE logic and adaptation primitives |
| `ace_platform/` | Hosted platform backend, API, MCP server, workers, and DB layer |
| `web/` | React/Vite dashboard frontend |
| `docs-site/` | Documentation website source |
| `playbooks/` | Starter playbook templates |
| `tests/` | Backend and platform test suite |

## Contributing

Contributions are welcome. If you want to improve ACE, the best path is a focused PR with a clear test plan.

1. Create a feature branch instead of working on `main`.
2. Add tests for new behavior.
3. Run the local quality gates before opening a PR:

```bash
source venv/bin/activate && ruff check ace_platform/ tests/
source venv/bin/activate && ruff format ace_platform/ tests/
source venv/bin/activate && pytest tests/ -v
```

If you touch the frontend, also run:

```bash
cd web
npm ci
npm run lint
npx vitest run
```

For larger changes, start with a small draft PR so we can align early.

## About Dan McAteer

ACE Platform is built and maintained by [Dan McAteer](https://github.com/DannyMac180).

Dan is focused on making AI systems more durable, compounding, and useful in real workflows, not just impressive in a single demo. If you want to contribute, collaborate, or help push ACE forward, opening a PR is the best place to start.

## Learn More

- [ACE docs](https://docs.aceagent.io)
- [API reference](docs/API_REFERENCE.md)
- [Next iteration working stream](docs/next_iteration_working_stream.md)
- [Changelog](CHANGELOG.md)
- [Troubleshooting guide](docs/TROUBLESHOOTING.md)
- [ACE core README](ace_core/README.md)
- [Apache 2.0 license](LICENSE.txt)
