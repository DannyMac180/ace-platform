# Maintainer Workflow

Use this guide when making changes to the repo-maintainer starter project.

- Start with `README.md` before changing command flows or contributor-facing
  docs.
- Run pytest before proposing a release or merging a behavior change.
- Keep source logic in `src/maintainer_tools/` and regression coverage in
  `tests/` when the project grows.
- Prefer small, reviewable pull requests with a brief validation summary.
- Capture user-visible workflow changes in the changelog before handoff.
