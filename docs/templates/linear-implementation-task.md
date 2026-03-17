# Summary

<Describe the concrete implementation slice in one short paragraph.>

## Problem

<What specific gap is this task solving?>

## Desired Outcome

<What should exist or behave differently after this work lands?>

## Primary Context

- `docs/ACE_Product_Spec_Next_Iteration.md`
- `docs/next_iteration_working_stream.md`
- `docs/adr/0001-oss-core-vs-cloud-boundary.md`
- Additional implementation context:
  - `<doc path>`
  - `<ADR, spec section, or issue link>`

## Scope

### In scope

- <specific implementation change>
- <specific implementation change>

### Out of scope

- <non-goal>
- <non-goal>

## Implementation Notes

- Branch expectation:
  - `<main or next-iteration>`
- Affected surfaces:
  - `<package, service, CLI, MCP, web, docs>`
- Constraints:
  - <compatibility, rollout, migration, or dependency constraint>

## Acceptance Criteria

- [ ] The target behavior or artifact is implemented.
- [ ] The change follows the OSS/core versus cloud boundary described in the
      ADR.
- [ ] The selected branch strategy matches
      `docs/next_iteration_working_stream.md`.
- [ ] Required docs, tests, or migration notes are updated if the change
      affects them.

## Validation

- [ ] Reproduce the current gap before changing code
- [ ] Run targeted validation for the changed behavior
- [ ] Run required repo checks for the touched surface
- [ ] Confirm the result aligns with the ACE v2 spec and ADR
- [ ] Document any divergence from the referenced docs explicitly

## Deliverables

- <code path changed>
- <test or validation artifact>
- <doc update if required>

## Dependencies

- Parent epic:
  - <Linear issue>
- Blocked by:
  - <issue or decision>
- Related:
  - <issue or PR>

## Risks / Open Questions

- <risk or unresolved question>
- <risk or unresolved question>
