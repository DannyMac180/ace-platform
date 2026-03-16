# Next Iteration Working Stream

This document defines how ACE will isolate "next iteration" architecture work for
the platform split while keeping `main` releasable.

## Decision

ACE will use a dedicated long-lived integration branch named
`next-iteration`.

- `main` remains the source of truth for releases, hotfixes, and routine
  product work.
- `next-iteration` holds architecture work for the platform split that would
  create churn, partial migrations, or reviewer confusion on `main`.
- Runtime feature flags are optional inside `next-iteration` when a new code
  path must coexist with the current stack, but the branch boundary is the
  primary gate for this effort.

Create or refresh the working stream from the latest stable baseline with:

```bash
git fetch origin --prune
git checkout -B next-iteration origin/main
```

## Branch Roles

| Branch | Purpose | Merge policy |
| --- | --- | --- |
| `main` | Stable shipping line for production fixes, docs, and routine feature work | Merge only reviewed, releasable work |
| `next-iteration` | Integration stream for the platform split and architecture reshaping | Forward-merge `origin/main` regularly; do not treat it as the default release branch |
| `feature/*` from `main` | Bug fixes and non-split improvements | Merge to `main` first, then merge or cherry-pick into `next-iteration` when needed |
| `feature/*` from `next-iteration` | Split-specific refactors, moves, and experiments | Merge into `next-iteration`; do not target `main` until the slice is stabilized or explicitly feature-gated |

## Working Agreement

Use the current repository layout as the routing guide for new work:

- `ace_core/` stays aligned with the upstream core library and should avoid
  split-only churn unless the change is required by both branches.
- `ace_platform/`, `web/`, and `docs-site/` are the primary surfaces for
  platform-split work and can evolve more aggressively inside
  `next-iteration`.
- `tests/` should follow the branch that owns the behavior change so validation
  stays close to the new architecture.
- `README.md`, `docs/`, and release notes should describe the branch model so
  contributors know where to open follow-up work.

When a change affects both the shipping product and the new architecture:

1. Land the production-safe portion on `main`.
2. Merge `origin/main` into `next-iteration`.
3. Continue the split-only work from `next-iteration`.

This keeps urgent fixes flowing to production without forcing partially migrated
architecture onto `main`.

## Migration Draft

### Phase 1: Bootstrap the stream

- Cut `next-iteration` from the latest `origin/main`.
- Keep deployments and routine roadmap work on `main`.
- Treat this document as the source of truth for where split-specific work
  should land.

### Phase 2: Route new architecture work

- Start new split-specific branches from `next-iteration`.
- Keep file moves, package boundary experiments, and integration-layer rewrites
  on `next-iteration` until the shape is stable.
- If a task is required for both branches, land the smallest safe slice on
  `main` first and then bring it forward.

### Phase 3: Keep the streams aligned

- Merge `origin/main` into `next-iteration` on a regular cadence and before
  large refactors land.
- Resolve conflicts in favor of preserving production behavior on `main` and
  staging unfinished architecture only on `next-iteration`.
- Update `CHANGELOG.md` and root docs when the branch policy changes.

### Phase 4: Graduate stabilized slices

- Promote work back to `main` only when the slice is reviewable, validated, and
  either complete or safely gated.
- Prefer small PRs from `next-iteration` into `main` over a single large
  catch-up merge.
- Once the platform split becomes the default architecture, retire the branch or
  rename it to match the new steady-state release model.

## Exit Criteria

The working stream is doing its job when:

- contributors can tell whether a task should start from `main` or
  `next-iteration` without extra clarification,
- `main` stays deployable while structural changes continue elsewhere, and
- merge-forward discipline keeps the split stream close enough to production to
  validate incrementally.
