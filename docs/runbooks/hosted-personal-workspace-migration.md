# Hosted Solo To Personal Workspace Migration

## Summary

This migration backfills existing hosted solo users into hosted `personal`
workspaces, which is the ACE v2 tenancy model required by
`docs/ACE_Product_Spec_Next_Iteration.md` Decision 2 and Epic 9 / E9-T1.

## Architecture Context

- `docs/ACE_Product_Spec_Next_Iteration.md`
- `docs/next_iteration_working_stream.md`
- `docs/adr/0001-oss-core-vs-cloud-boundary.md`

This is cloud-control-plane work. It creates or repairs hosted workspace rows
without moving user-owned playbooks, API keys, or other OSS/runtime artifacts.

## Scope

The script targets active hosted users who are still in the legacy solo shape:

- zero workspaces: create a hosted `personal` workspace
- exactly one hosted `personal` workspace: repair missing owner membership,
  entitlements, or legacy billing projection
- any other shape: skip and report for manual review

## Commands

Dry-run:

```bash
source venv/bin/activate && python scripts/migrate_hosted_solo_users_to_personal_workspaces.py migrate --dry-run
```

Scoped dry-run:

```bash
source venv/bin/activate && python scripts/migrate_hosted_solo_users_to_personal_workspaces.py migrate --dry-run --email dan@example.com
```

Apply:

```bash
source venv/bin/activate && python scripts/migrate_hosted_solo_users_to_personal_workspaces.py migrate
```

Validate:

```bash
source venv/bin/activate && python scripts/migrate_hosted_solo_users_to_personal_workspaces.py validate
```

## Validation Checks

The validation command fails if an eligible hosted solo user has any of these
problems:

- missing hosted `personal` workspace
- missing owner membership on that workspace
- missing workspace entitlements row
- missing legacy billing projection when user-level billing state exists
- mismatched projected Stripe/customer/subscription timestamps or status

## Rollback Plan

The migration only writes these tables:

- `workspaces`
- `workspace_memberships`
- `workspace_entitlements`
- `workspace_subscriptions`

Rollback is transaction-safe if done from the same run window and migration
output:

1. Identify the rows created or repaired from the script JSON output.
2. For `action = created`, delete rows in this order inside one transaction:
   - `workspace_subscriptions`
   - `workspace_entitlements`
   - `workspace_memberships`
   - `workspaces`
3. For `action = repaired`, revert only the recorded change set:
   - if `membership_role_updated_from` is set, restore that role
   - if `subscription_created = true`, delete the created
     `workspace_subscriptions` row
   - if `entitlements_created = true`, delete the created
     `workspace_entitlements` row
4. Re-run the `validate` command to confirm the pre-migration state is restored
   or that the intended repair rows are gone.

Example rollback skeleton:

```sql
BEGIN;
DELETE FROM workspace_subscriptions WHERE workspace_id = '<workspace-id>';
DELETE FROM workspace_entitlements WHERE workspace_id = '<workspace-id>';
DELETE FROM workspace_memberships WHERE workspace_id = '<workspace-id>';
DELETE FROM workspaces WHERE id = '<workspace-id>';
COMMIT;
```
