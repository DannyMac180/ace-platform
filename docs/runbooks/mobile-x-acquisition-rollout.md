# Mobile X Acquisition Rollout Runbook

## Purpose
This runbook covers safe rollout of the mobile/X acquisition optimization work across tracking, landing pages, mobile auth, and trial-disclosure experiment changes.

## Scope
This runbook validates:
- first-party attribution + analytics ingestion
- X-focused landing pages (`/x`) on backend and SPA
- mobile auth UX improvements and OAuth fallback guidance
- hero video loading optimizations
- trial disclosure copy experiment and funnel cohort filtering

## Flags and Controls
Backend flags:
- `ACQUISITION_TRACKING_ENABLED`
- `X_LANDING_ENABLED`

Frontend flags:
- `VITE_X_LANDING_ENABLED`
- `VITE_EXPERIMENT_TRIAL_DISCLOSURE_ENABLED`

## Pre-Deployment Checklist
1. Confirm DB migration is applied: `alembic upgrade head`.
2. Confirm backend and web deploys use matching commit set.
3. Confirm social card exists and serves:
- `GET /ace-social-card.png` returns `200`.
4. Confirm analytics route is reachable:
- `POST /analytics/events` returns `202` for valid payload.
5. Confirm admin access to funnel panel before rollout.

## Stage 1: Tracking + Funnel Only
Objective: turn on data collection before UX shifts.

1. Backend settings:
- `ACQUISITION_TRACKING_ENABLED=true`
- `X_LANDING_ENABLED=false`
2. Frontend settings:
- `VITE_X_LANDING_ENABLED=false`
- `VITE_EXPERIMENT_TRIAL_DISCLOSURE_ENABLED=false`
3. Validate ingestion:
- Open landing and auth pages on desktop/mobile.
- Confirm `landing_view`, `register_start`, `register_submit`, `register_success` events are stored.
4. Validate `/admin/funnel`:
- baseline values present for `landing_views`, `register_starts`, `register_completes`, `signups`.
- filter `source=x` returns data subset without API errors.

Exit criteria:
- ingestion success rate is stable
- no elevated 4xx/5xx on `/analytics/events`

## Stage 2: X Landing + Metadata + Video
Objective: enable acquisition entry path while keeping auth experiment off.

1. Backend settings:
- `X_LANDING_ENABLED=true`
2. Frontend settings:
- `VITE_X_LANDING_ENABLED=true`
3. Validate both `/x` surfaces:
- backend `https://aceagent.io/x`
- SPA route `/x` on app domain
4. Validate OG/Twitter metadata:
- inspect source for `og:title`, `og:description`, `og:image`, `og:url`, `og:site_name`
- inspect source for `twitter:card`, `twitter:title`, `twitter:description`, `twitter:image`
5. Validate hero media behavior:
- mobile: poster first, no eager autoplay, tap-to-play works
- desktop: intersection-triggered lazy load/play
- reduced-motion/save-data respected

Exit criteria:
- `/x` loads successfully on iOS/Android
- no significant regression in landing performance metrics

## Stage 3: Mobile Auth + Trial Disclosure Experiment
Objective: activate conversion UX changes progressively.

1. Keep:
- `ACQUISITION_TRACKING_ENABLED=true`
- `X_LANDING_ENABLED=true`
- `VITE_X_LANDING_ENABLED=true`
2. Enable experiment:
- `VITE_EXPERIMENT_TRIAL_DISCLOSURE_ENABLED=true`
3. Progressive rollout:
- start at 10% traffic
- increase to 50%
- increase to 100% when stable
4. Mobile QA focus:
- two-step register flow on `<=900px`
- keyboard behavior with sticky submit area and top bar
- OAuth fallback hint in X in-app browser

Exit criteria:
- no material auth drop-off regression
- no sustained increase in OAuth initiation errors

## QA Matrix (Manual)
Browsers/devices:
- iOS Safari
- iOS X in-app browser
- Android Chrome
- Android X in-app browser

Scenarios:
1. Open `/x` and click CTA to `/register`.
2. Complete email/password registration.
3. Attempt OAuth and validate fallback messaging behavior.
4. Trigger trial checkout intent and return via billing success.
5. Create first playbook.
6. Validate admin funnel filtering with `source=x` and variant filters.

## Success Metrics (30-Day Window)
Track globally and with filters `source=x` + experiment variant:
1. `landing_views -> register_starts`
2. `register_starts -> register_completes`
3. `register_completes -> trial_checkout_intent`
4. `trial_checkout_intent -> trial_started`
5. `trial_started -> first_playbook_created`

## Monitoring and Alerting
Monitor:
- `/analytics/events` request rate, 429 rate, 5xx rate
- auth registration errors
- OAuth initiation/callback error counts
- admin funnel query errors

Investigate quickly when:
- sudden conversion drop >15% between adjacent funnel stages
- sustained 429s on analytics ingestion for normal traffic
- OAuth fallback usage spikes unexpectedly

## Rollback Plan
Fast rollback toggles:
1. Disable experiment: `VITE_EXPERIMENT_TRIAL_DISCLOSURE_ENABLED=false`
2. Disable `/x`: `VITE_X_LANDING_ENABLED=false` and `X_LANDING_ENABLED=false`
3. Disable tracking ingestion: `ACQUISITION_TRACKING_ENABLED=false`

Notes:
- rollbacks are copy/route/ingestion toggles only
- no billing-logic rollback required for this rollout

## Post-Rollout Review
1. Compare funnel deltas by stage and by source/variant.
2. Capture findings and ship copy/UX iteration follow-ups.
3. Keep event taxonomy stable for at least one full measurement window.
