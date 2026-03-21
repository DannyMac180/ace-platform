# Product Analytics Taxonomy

This document defines the product analytics events used for Epic 9 / `DAN-58`.

The taxonomy is intentionally first-party and low-cardinality:

- web and backend events are written to `acquisition_events`
- CLI events are best-effort and do not block local workflows
- admin visibility comes from:
  - `GET /admin/funnel` for signup-to-paid conversion stages
  - `GET /admin/product-analytics` for activation and retention counts

## Required Behaviors

| Behavior | Event(s) | Trigger | Observation surface |
| --- | --- | --- | --- |
| Signup | `register_start`, `register_submit`, `register_success` | Hosted auth/register flows | Admin funnel + product analytics |
| Init | `cli_init_completed` | `ace init` succeeds | Admin product analytics |
| Seed | `cli_seed_completed` | `ace seed` succeeds | Admin product analytics |
| Benchmark | `cli_benchmark_completed` | `ace benchmark` succeeds | Admin product analytics |
| Upgrade | `trial_checkout_intent`, `trial_started`, `upgrade_completed` | Pricing/trial actions, Stripe webhook success, personal workspace -> team upgrade | Admin funnel + product analytics |
| Retention | `retention_active` | Authenticated user returns to the hosted app; emitted at most once per user per day | Admin product analytics |

## Event Notes

### `cli_init_completed`

- emitted after `ace init` writes `ace.toml`
- includes:
  - `project_name`
  - `default_profile`
  - `git_enabled`
  - `agent_mode`
  - `output_mode`

### `cli_seed_completed`

- emitted after `ace seed` finishes successfully
- includes created/overwritten/skipped counts and scanned input count

### `cli_benchmark_completed`

- emitted after `ace benchmark` produces a summary
- includes:
  - `benchmark_id`
  - `case_count`
  - `ace_wins`
  - `baseline_wins`
  - `ties`
  - `net_passed_delta`
  - `format`

### `upgrade_completed`

- emitted for completed upgrade actions
- current sources:
  - Stripe subscription activation/update (`upgrade_kind = "subscription"`)
  - personal workspace upgraded to team (`upgrade_kind = "workspace_plan"`)

### `retention_active`

- emitted from the authenticated app shell
- rate-limited client-side to once per user per UTC day
- includes:
  - current path
  - account age in days
  - subscription status/tier
  - trial state

## Boundary Notes

This ticket crosses hosted app and CLI surfaces, so it follows `docs/adr/0001-oss-core-vs-cloud-boundary.md`:

- CLI telemetry is best-effort only.
- Failed analytics delivery does not change command exit behavior.
- Local/self-managed users can point telemetry at their own ACE API by configuring the hosted profile API URL.
