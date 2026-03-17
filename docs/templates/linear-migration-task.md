# Summary

<Describe the migration slice and the system transition it enables.>

## Current State

<What exists today that needs to be moved, split, reclassified, or retired?>

## Target State

<What should the architecture or ownership look like after this migration?>

## Primary Context

- `docs/ACE_Product_Spec_Next_Iteration.md`
- `docs/next_iteration_working_stream.md`
- `docs/adr/0001-oss-core-vs-cloud-boundary.md`
- Additional migration context:
  - `<doc path>`
  - `<issue, ADR, or plan section>`

## Migration Scope

### In scope

- <code move, package split, interface extraction, data migration, etc.>
- <code move, package split, interface extraction, data migration, etc.>

### Out of scope

- <explicit non-goal>
- <explicit non-goal>

## Migration Plan

1. <step one>
2. <step two>
3. <step three>

## Branch / Rollout Strategy

- Working branch:
  - `<main or next-iteration>`
- Merge or rollout notes:
  - <forward-merge, feature gate, compatibility bridge, cleanup follow-up>

## Acceptance Criteria

- [ ] The current-state and target-state boundaries are explicit.
- [ ] The migration path preserves a safe, reviewable route from current state
      to target state.
- [ ] Any temporary compatibility layer or staging approach is documented.
- [ ] The work respects the OSS/core versus cloud boundary and branch policy.

## Validation

- [ ] Verify the current state before migration
- [ ] Validate the intermediate path, not just the end state
- [ ] Run targeted checks proving the migrated surface still works
- [ ] Confirm docs and ownership boundaries match the new state
- [ ] Record any follow-up cleanup work as separate issues

## Deliverables

- <migration doc or plan>
- <implementation slice>
- <follow-up issue(s) if needed>

## Dependencies

- Parent epic:
  - <Linear issue>
- Blocked by:
  - <issue or architectural decision>
- Related:
  - <issue or PR>

## Risks / Open Questions

- <migration risk>
- <rollback or compatibility concern>
