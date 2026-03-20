# ACE OSS Examples

These examples are for the local-first, open-source ACE experience. They avoid
hosted auth, billing, and other ACE-operated cloud services so you can
demonstrate value quickly with files in this repository alone.

## Fastest local demo

Use the sample project in `examples/repo-maintainer-starter/`:

```bash
source venv/bin/activate
python -m ace_platform.cli seed --path examples/repo-maintainer-starter
python -m ace_platform.cli benchmark \
  --input examples/repo-maintainer-starter/benchmark/repo-maintainer-benchmark.json
```

That flow shows two things immediately:

- `ace seed` turns the sample repo's README, docs, and examples into starter
  playbooks under `examples/repo-maintainer-starter/.ace/playbooks/`
- `ace benchmark` shows how an ACE-assisted response beats the sample baseline
  on repo-maintainer tasks without calling any hosted service

## Included assets

- `repo-maintainer-starter/`: a runnable sample project with local docs,
  examples, and a benchmark suite
- `playbook-packs/repo-maintainer/`: a small curated playbook pack you can copy
  into another local ACE project as a starting point

## Boundary reminder

These examples are intentionally OSS-only. If you want hosted sync, managed
inference, team workflows, or billing-backed entitlements, use the cloud
product instead of these local examples.
