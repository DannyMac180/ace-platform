# Sentry Audit Report - ACE Platform (Production + Staging)

Date: 2026-02-12 UTC  
Audit ID: `sentry-audit-20260212T194104Z`  
Branch: `codex/sentry-audit-implementation`

## 1. Scope and Method

This audit executed the requested end-to-end scope across:
- Code instrumentation and context propagation
- Deployment/runtime configuration on Fly.io (`ace-platform`, `ace-platform-staging`)
- Controlled synthetic probes in production and staging
- Reliability and observability behavior under probe conditions

## 2. Rubric and Score

Weights:
- Instrumentation coverage: 25
- Context/privacy safety: 20
- Signal quality/grouping: 20
- Alerting/on-call readiness: 20
- Deployment/release hygiene: 15

Score:
- Instrumentation coverage: 17 / 25
- Context/privacy safety: 18 / 20
- Signal quality/grouping: 10 / 20
- Alerting/on-call readiness: 4 / 20
- Deployment/release hygiene: 9 / 15

Total: **58 / 100**

Verdict gate:
- Ready: no P0/P1 and 100% critical probe pass
- Partially Ready: no P0 and only P1/P2 gaps
- Not Ready: any P0 or failed critical capture path

## 3. Final Verdict

**Verdict: Not Ready**

Reason:
- A critical capture/readiness path failed in staging during runtime verification (API health became critical and unstable before later recovery), and there are unresolved P1 gaps.

## 4. Evidence Summary

### 4.1 Static Integration Evidence

Confirmed Sentry initialization points:
- API init: `ace_platform/api/main.py:50`
- Worker init: `ace_platform/workers/celery_app.py:34`

Confirmed capture points/context helpers:
- API generic exception capture: `ace_platform/api/main.py:339`, `ace_platform/api/main.py:349`
- Worker exception capture: `ace_platform/workers/evolution_task.py:126`, `ace_platform/workers/evolution_task.py:259`
- User/job context helpers: `ace_platform/core/sentry_context.py:49`, `ace_platform/core/sentry_context.py:114`

Known gap:
- Standalone MCP server has no Sentry init path (`ace_platform/mcp/server.py` has no `sentry_sdk` usage).

Privacy/redaction evidence:
- Header redaction helper: `ace_platform/core/sentry_context.py:167`
- Redaction test passing: `tests/test_api_app.py:168`

### 4.2 Deployment/Config Evidence

Fly secrets (`ace-platform`, `ace-platform-staging`):
- `SENTRY_DSN` is present in both environments.
- `SENTRY_TRACES_SAMPLE_RATE` and `SENTRY_PROFILES_SAMPLE_RATE` are not explicitly set as Fly secrets.

Release configuration:
- Release value hardcoded in API and worker: `ace_platform/api/main.py:53`, `ace_platform/workers/celery_app.py:37`

Frontend:
- No Sentry SDK dependency in `web/package.json`.

### 4.3 Runtime Probe Evidence

Successful probes:
- Production API process probe:
  - env=`production`, release=`ace-platform@0.1.0`, traces=0.1, profiles=0.1
  - event_id=`a62c8eeff7a541c6928e1f9fcb01bb96`
- Production worker process probe:
  - env=`production`, release=`ace-platform@0.1.0`, traces=0.05, profiles=`None`
  - event_id=`a73ad5f173374ecc88cca047d9cda8e5`
- Staging worker process probe:
  - env=`staging`, release=`ace-platform@0.1.0`, traces=0.05, profiles=`None`
  - event_id=`7612071b47fa420cb864aae50378a8fb`
- Celery failure-path probe (synthetic failing task):
  - Production worker: state=`FAILURE`
  - Staging worker: state=`FAILURE`

Production MCP endpoint evidence:
- `GET https://aceagent.io/mcp/health` returned 200.
- `GET https://aceagent.io/mcp/sse` returned event-stream endpoint payload.

Staging critical failure evidence:
- Fly check became critical during audit window (`servicecheck-00-http-8000` timing out), then temporarily recovered after machine restart.
- Health status continued to flap between passing and critical during final verification window.
- Logs show repeated Sentry envelope retries with SSL EOF errors to Sentry ingestion endpoint.
- Logs show severe request latency warnings.
- Logs show OOM kill of uvicorn process on staging API machine, followed by restart.

## 5. Findings

### P1 - Staging API reliability degradation during Sentry transport retries

- Impact: critical health check failures and unstable API responsiveness in staging.
- Evidence: repeated SSL EOF retry logs, slow request warnings, OOM kill/restart, failed Fly health check.
- Tracking issue: `ace-platform-46q`

### P1 - Standalone MCP process not instrumented with Sentry

- Impact: if MCP runs in standalone mode (`python -m ace_platform.mcp.server`), exceptions are not sent to Sentry.
- Evidence: no Sentry init in MCP server code; runtime module import probe reported no active Sentry DSN.
- Tracking issue: `ace-platform-bav`

### P2 - Hardcoded release prevents accurate release health and regression mapping

- Impact: weaker issue-to-deploy traceability.
- Evidence: static `release="ace-platform@0.1.0"` in API and worker init paths.
- Tracking issue: `ace-platform-rxw`

### P2 - Sampling behavior is implicit and uneven across surfaces

- Impact: observability behavior is harder to reason about and tune.
- Evidence: only `SENTRY_DSN` explicit in Fly secrets; worker profiling disabled while API profiling enabled by default.
- Tracking issue: `ace-platform-ii2`

### P2 - Project-level controls not verifiable via current automation

- Impact: alerting/routing/scrubbing posture cannot be continuously validated from this environment.
- Evidence: no authenticated Sentry project-settings audit path available in current tooling.
- Tracking issue: `ace-platform-ec9`

### P3 - Frontend telemetry gap

- Impact: browser-side errors/perf issues may be invisible.
- Evidence: no Sentry frontend dependency/config in web app.
- Tracking issue: `ace-platform-0r2`

## 6. Test Cases vs Result

- API capture probe (backend, env/release tags): **Pass (production)**
- Worker capture probe (env/release tags): **Pass (production + staging)**
- Celery failure path probe: **Pass (synthetic task failure observed)**
- MCP path coverage: **Partial** (production endpoint healthy; standalone MCP instrumentation gap)
- API->worker trace linkage continuity: **Not verified end-to-end** (requires Sentry project event inspection)
- Privacy/redaction: **Pass** (unit tests and redaction helper)
- Alert routing trigger validation: **Blocked/Not verified** (no authenticated Sentry settings/event routing check)
- Grouping/noise validation: **Blocked/Not verified** (requires Sentry issue stream access)

## 7. Immediate Actions (24-48h)

1. Stabilize staging API and resolve Sentry transport retry/OOM behavior (`ace-platform-46q`).
2. Add Sentry init for standalone MCP mode (`ace-platform-bav`).
3. Move release value to deploy-derived metadata (`ace-platform-rxw`).

## 8. Notes and Constraints

- This audit executed synthetic probes in production as approved, using explicit audit tags and minimal volume.
- Sentry project-level controls (alert rules, ownership, inbound filters, scrubbing policies, quota posture) could not be fully verified without an authenticated Sentry administrative API/UI verification flow.
