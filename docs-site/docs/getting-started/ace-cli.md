---
sidebar_position: 2
---

# ACE CLI

The ACE CLI is the public OSS/core path for local and agent-friendly onboarding.
Use it when you want to bootstrap a repository, validate a self-managed setup,
generate starter playbooks, benchmark whether ACE improves results, or move
playbook artifacts between hosted and local contexts.

This guide covers the shipped CLI commands in the current runtime:

- `ace init`
- `ace doctor`
- `ace seed`
- `ace benchmark`
- `ace export`
- `ace import`

If you want the hosted dashboard path first, use the
[Quick Start](/docs/getting-started/quick-start). If you want the local-first
path, start here and then connect your agent through MCP.

## Typical Flows

### Bootstrap a local project

Use this flow when you want to stand up ACE in a repository and hand the setup
to a developer or coding agent.

```bash
ace init --path .
ace doctor --path .
ace seed --path .
ace benchmark --input benchmarks/starter.json
```

If you need deterministic, machine-readable setup output for an agent, start
with:

```bash
ace init --path . --agent
```

### Move playbooks between hosted and local contexts

Use this flow when you want a local backup of hosted playbooks, want to migrate
artifacts into a self-managed environment, or want to restore a bundle into a
hosted workspace.

```bash
export ACE_API_URL=https://aceagent.io
export ACE_TOKEN=your-token

ace export --output ace-bundle.json
ace import --input ace-bundle.json
```

`ace export` writes a portable bundle to a local JSON file. `ace import` reads
that bundle and uploads it into the hosted ACE API.

## `ace init`

Use `ace init` when you are starting ACE in a repository for the first time.
It writes `ace.toml` with both local and hosted profiles so a project has a
single starting point for self-managed and cloud-connected workflows.

When to use it:

- A repo does not have `ace.toml` yet.
- You want a standard local profile that launches the MCP server over stdio.
- You want an agent to bootstrap config deterministically with `--agent`.

Example:

```bash
ace init --path . --default-profile local
```

Agent-friendly example:

```bash
ace init --path . --agent
```

What it gives you:

- a project config with local and hosted profiles
- a default MCP stdio command for `python -m ace_platform.mcp.server stdio`
- recommended follow-up commands: `ace doctor`, `ace seed`, `ace benchmark`

## `ace doctor`

Use `ace doctor` right after `ace init`, before handing a repo to another
developer or agent, or whenever a local ACE setup stops behaving the way you
expect.

When to use it:

- You want to verify Python, config schema, and project paths.
- You want to catch missing Git or MCP dependencies before setup fails later.
- You changed `ace.toml`, environment variables, or local runtime settings.

Example:

```bash
ace doctor --path .
```

What it checks:

- Python 3.10+ is available
- `ace.toml` parses and matches the expected schema
- local and hosted profile settings are valid
- stdio MCP commands or hosted MCP URLs are configured correctly

## `ace seed`

Use `ace seed` when a repository already has useful context in its README,
docs, and examples, and you want starter playbooks without writing them from
scratch.

When to use it:

- You just initialized ACE in an existing repository.
- You want starter playbooks based on current docs and example files.
- You need to refresh generated playbooks after major documentation changes.

Example:

```bash
ace seed --path .
```

Overwrite generated playbooks when you intentionally want to replace prior
generated output:

```bash
ace seed --path . --force
```

What it produces:

- starter playbooks in the configured playbooks directory
- generated guidance based on repository structure, docs, and examples

## `ace benchmark`

Use `ace benchmark` when you need evidence that ACE-assisted behavior is better
than a baseline response or process.

When to use it:

- You want a measurable activation moment after setup.
- You are comparing a weak baseline against an ACE-assisted output.
- You want to show improvement before adopting a playbook more broadly.

Example:

```bash
ace benchmark --input benchmarks/starter.json
```

Minimal benchmark input:

```json
{
  "id": "starter-benchmark",
  "metric": "exact_match",
  "cases": [
    {
      "id": "case-1",
      "prompt": "Summarize the release notes",
      "expected_output": "ready",
      "baseline_output": "draft",
      "ace_output": "ready"
    }
  ]
}
```

The CLI compares baseline and ACE-assisted outputs case by case and reports the
net improvement.

## `ace export`

Use `ace export` when you want to pull hosted playbooks and traces into a local
portable bundle.

When to use it:

- You want a local backup of hosted playbooks.
- You want to inspect or version a portable bundle in your own environment.
- You want to move hosted artifacts into a self-managed workflow.

Example:

```bash
ace export \
  --api-url https://aceagent.io \
  --token "$ACE_TOKEN" \
  --output ace-bundle.json
```

You can also set `ACE_API_URL` and `ACE_TOKEN` in the shell and omit the flags.

What it produces:

- a portable JSON bundle of hosted playbooks and traces
- a file you can archive locally or hand to `ace import`

## `ace import`

Use `ace import` when you want to upload a portable bundle into a hosted ACE
workspace.

When to use it:

- You exported playbooks and want to restore them later.
- You want to move artifacts from a local or backup bundle into hosted ACE.
- You want a repeatable handoff format between environments.

Example:

```bash
ace import \
  --api-url https://aceagent.io \
  --token "$ACE_TOKEN" \
  --input ace-bundle.json
```

What it does:

- reads a local portable bundle file
- posts the bundle into the hosted ACE API
- reports how many playbooks were imported

## How The CLI Fits The Product Boundary

The ACE v2 architecture treats local bootstrap, validation, benchmarking, and
portability as public OSS/core capabilities. That is why these commands live in
the local runtime path and are suitable for self-managed onboarding.

Use the CLI when you want:

- local-first setup
- agent-friendly repository bootstrap
- portable artifact movement between local and hosted contexts

Use the hosted dashboard when you want:

- managed auth and sessions
- billing and workspace administration
- hosted convenience after local setup is complete

## Related Docs

- [Quick Start](/docs/getting-started/quick-start)
- [MCP Integration Overview](/docs/developer-guides/mcp-integration/overview)
- [Create an account](/docs/getting-started/creating-account)
