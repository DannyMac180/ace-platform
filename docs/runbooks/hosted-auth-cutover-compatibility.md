# Hosted Auth Cutover Compatibility And Rollback

## Summary

This runbook defines the cutover-safe compatibility contract for hosted auth,
sessions, schema, and API keys while traffic moves between the current
`ace-platform` stack and the extracted hosted stack.

The goal is to preserve current hosted personal users end-to-end:

- no forced re-onboarding
- no OAuth callback or cookie regressions
- no API key invalidation
- no one-way schema trap that blocks rollback

## Architecture Context

- `docs/ACE_Product_Spec_Next_Iteration.md`
- `docs/next_iteration_working_stream.md`
- `docs/adr/0001-oss-core-vs-cloud-boundary.md`
- `docs/runbooks/hosted-personal-workspace-migration.md`

This is cloud-control-plane work. Hosted auth, sessions, OAuth, API keys, and
rollback orchestration stay on the hosted side of the OSS/core boundary.

## Compatibility Contract

The cutover keeps the existing hosted auth contract intact instead of
introducing a new token or API-key format:

- JWT access tokens remain bearer tokens signed with the existing JWT secret
  and still carry `sub`, `type`, `iat`, and `exp` claims.
- Refresh tokens remain JWT bearer tokens with the same `sub`/`type` contract.
- OAuth callbacks continue to redirect to
  `<frontend>/oauth/callback#access_token=...&refresh_token=...&is_new=...`.
- OAuth provider tokens stored in the database keep reading legacy plaintext
  rows while encrypting new writes with the `enc:v1:` envelope.
- Session cookies keep the existing hosted settings contract:
  `SESSION_SECRET_KEY`, `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_SAMESITE`, and
  `SESSION_COOKIE_DOMAIN` must stay compatible with the current cross-subdomain
  OAuth flow.
- API keys keep the existing `ace_` prefix, SHA-256 storage hash, `X-API-Key`
  header support, and `Authorization: Bearer <api-key>` compatibility.
- Empty API-key scope lists remain unrestricted for backward compatibility.

## Additive-First Schema Plan

1. Apply additive schema changes before traffic moves.
   Current hosted cutover depends on the existing additive workspace tenancy
   tables and OAuth account storage.
2. Backfill or repair hosted personal workspace rows before relying on
   workspace-scoped behavior:

Run the canonical migration dry-run and validation commands from `ace-private`
as documented in
[`docs/runbooks/hosted-personal-workspace-migration.md`](hosted-personal-workspace-migration.md).

3. Keep legacy user-level billing/auth rows available during the compatibility
   window. Do not remove or repurpose old auth/session/API-key fields during the
   cutover.
4. Auth entry points must repair legacy hosted personal workspace state on
   first authenticated access. Use
   `ensure_personal_workspace_for_user()` rather than bare workspace bootstrap
   so legacy billing projections are preserved if a user first returns via JWT,
   API key, or OAuth during cutover.
5. Do not treat `alembic downgrade` as the rollback plan after traffic has
   written workspace-era state. Post-cutover rollback is traffic reversal plus
   data-preserving verification, not destructive schema reversal.

## Required Validation Before Cutover

Run these checks against the release candidate before shifting traffic:

```bash
source venv/bin/activate && python -m pytest \
  tests/test_oauth_hosted_flow.py \
  tests/test_api_key_auth_resilience.py \
  tests/test_production_config.py \
  tests/test_hosted_personal_workspace_migration.py \
  tests/test_jwt_auth.py \
  tests/test_auth_middleware.py -q
```

Run the canonical hosted personal workspace validation command from
`ace-private` as documented in
[`docs/runbooks/hosted-personal-workspace-migration.md`](hosted-personal-workspace-migration.md).

Manual hosted checks:

1. Existing password user can log in and call `/v1/me` without re-registering.
2. Existing OAuth user can complete provider login and land on
   `/oauth/callback` with valid fragment tokens.
3. Existing API key authenticates through both `X-API-Key` and
   `Authorization: Bearer <api-key>`.
4. A hosted personal user with legacy billing fields resolves to a personal
   workspace with a projected `workspace_subscriptions` row.

## Rollback Triggers

Rollback immediately if any of these are observed after traffic moves:

- login or refresh requests fail because previously valid bearer tokens are
  rejected
- OAuth callback state/cookie validation starts failing for existing users
- existing API keys begin returning unexpected `401` or `403` responses
- hosted personal users authenticate successfully but lose paid/personal
  workspace behavior because subscription projection is missing
- migration validation reports `missing_workspace`, `missing_entitlements`, or
  `missing_subscription_projection` for users that were valid before cutover

## Owners

- Cutover commander: decides proceed / rollback based on the checks below
- App operator: flips traffic and verifies auth/API behavior
- Database operator: runs validation and confirms no destructive rollback step
  is needed

One person may hold multiple roles in a rehearsal, but each responsibility
must be explicitly assigned before the cutover window starts.

## Rollback Procedure

1. Freeze deploys and stop forwarding new traffic to the cutover stack.
2. Return traffic to the previous production stack.
3. Leave additive schema in place. Do not run `alembic downgrade` as an
   immediate response.
4. Re-run hosted personal workspace validation:

Re-run the canonical hosted personal workspace validation command from
`ace-private` as documented in
[`docs/runbooks/hosted-personal-workspace-migration.md`](hosted-personal-workspace-migration.md).

5. Verify that legacy user-level auth and billing state is still intact on the
   previous stack:
   - password login works
   - OAuth callback works
   - existing API keys work
   - paid users still resolve as paid
6. If validation reports repaired rows created during the cutover window, use
   the row-level rollback guidance in
   `docs/runbooks/hosted-personal-workspace-migration.md` instead of dropping
   the workspace schema.

## Rollback Verification

Rollback is complete only when all of these are true:

- `/v1/auth/login`, `/v1/auth/refresh`, and `/v1/me` succeed for existing users
- OAuth callback completes with the expected fragment tokens
- pre-cutover API keys authenticate successfully with unchanged scopes
- hosted personal workspace migration validation is green or any created repair
  rows have been reverted explicitly
- no destructive schema downgrade was needed to restore service
