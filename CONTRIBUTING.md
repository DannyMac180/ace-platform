# Contributing to ACE

ACE is developed as a local-first open-source engine with private cloud
services layered on top. Before contributing, read
[`docs/adr/0001-oss-core-vs-cloud-boundary.md`](docs/adr/0001-oss-core-vs-cloud-boundary.md)
so changes stay aligned with the public OSS/core versus private cloud boundary.

## Scope and Boundary

- Contributions to the public repository should improve the OSS/core product:
  the local engine, local runtime, local tooling, public protocol contracts,
  import/export formats, public docs, and self-hosting assets.
- Do not introduce dependencies from OSS/core code into hosted-only concerns
  such as billing, entitlements, managed auth, cloud sync, usage metering, or
  other ACE-operated control-plane services.
- If a proposal depends on ACE running a private service for the feature to
  work, treat it as cloud-side scope and discuss it before opening an
  implementation PR.

## Licensing

- This repository is licensed under the
  [MIT License](LICENSE.txt).
- By submitting a pull request, issue patch, or other contribution intended for
  inclusion in this repository, you agree that your contribution is provided
  under the same MIT License, unless we explicitly agree otherwise in writing.
- Only contribute code, docs, assets, and examples that you have the right to
  license under MIT. Do not submit proprietary material, secrets, or third-
  party content with incompatible terms.

## Development Workflow

1. Create a feature branch instead of working on `main`.
2. Add or update tests for behavior changes.
3. Run the local quality gates before opening a PR:

```bash
source venv/bin/activate && ruff check ace_platform/ tests/
source venv/bin/activate && ruff format ace_platform/ tests/
source venv/bin/activate && pytest tests/ -v
```

If you touch `web/`, also run:

```bash
cd web
npm ci
npm run lint
npx vitest run
```

## Pull Requests

- Keep PRs focused and describe the user-visible or maintainer-visible impact.
- Include a short test plan in the PR body.
- For large architectural changes, open a draft PR early so the OSS/cloud
  boundary and rollout shape can be reviewed before the implementation expands.
