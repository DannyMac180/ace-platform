# Hosted Solo To Personal Workspace Migration

This runbook is now a redirect.

Hosted solo-user to personal-workspace migration is cloud-control-plane work,
and the canonical script plus rollback procedure now live in `ace-private`.

Use the private repo for:

- migration dry-runs and applies
- validation against hosted personal workspace state
- rollback procedures for hosted workspace tenancy repairs

The public script at
`scripts/migrate_hosted_solo_users_to_personal_workspaces.py` is intentionally
kept only as a compatibility shim that points operators at `ace-private`.

## Compatibility shim lifecycle

- Owner: `ace-private` hosted control-plane maintainers.
- Cleanup note: delete the public shim after all operator docs and automation
  have been updated to call the private canonical migration entrypoint
  directly.
