# Repo Maintainer Starter

This sample project is a tiny open-source repository for demonstrating ACE's
local-first workflow. It is intentionally small, readable, and fully runnable
with files committed under `examples/`.

## What it demonstrates

- `ace seed` can read a README, maintainer docs, and example files to generate
  starter playbooks without any hosted dependency
- `ace benchmark` can show a measurable improvement between a weak baseline and
  an ACE-assisted answer using a local benchmark JSON file
- curated playbook packs can live alongside a sample project without becoming a
  cloud-only feature

## Quick demo

From the repo root:

```bash
source venv/bin/activate
python -m ace_platform.cli seed --path examples/repo-maintainer-starter
python -m ace_platform.cli benchmark \
  --input examples/repo-maintainer-starter/benchmark/repo-maintainer-benchmark.json
```

`ace seed` writes generated playbooks into `.ace/playbooks/` because this sample
keeps generated content separate from the committed example assets.

## Project shape

- `docs/maintainer_workflow.md`: the core maintainer rules for code changes and
  review
- `docs/release_checklist.md`: release-specific guidance that should surface in
  seeded playbooks
- `examples/`: reference patterns for new commands and issue triage
- `benchmark/repo-maintainer-benchmark.json`: a local benchmark file for
  head-to-head comparison

## Why this stays OSS-only

Everything here is file-based and portable:

- no hosted auth
- no workspace membership requirements
- no managed inference
- no server-side entitlements

That keeps the example aligned with ACE OSS and the server-boundary rules in
the architecture docs.
