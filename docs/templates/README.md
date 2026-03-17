# Linear Issue Templates for ACE v2

These templates are the "internal equivalents" referenced in
`docs/ACE_Product_Spec_Next_Iteration.md` for Epic 0, Task 3.

Use them when creating ACE v2 work in Linear so humans and Symphony agents get
consistent context, acceptance criteria, and validation requirements.

## Templates

- `linear-epic.md`
- `linear-implementation-task.md`
- `linear-migration-task.md`

## How to use them

1. Create the Linear issue in the ACE v2 project.
2. Copy the template body into the issue description.
3. Fill in all placeholder sections before moving the issue to `Todo`.
4. Keep the `Primary Context` and `Validation` sections intact. Symphony copies
   those sections into its workpad and treats them as required input.

## Notes

- These templates are Linear-first on purpose. Symphony orchestrates from
  Linear, not GitHub Issues.
- For ACE v2 work, the default architecture references should remain:
  - `docs/ACE_Product_Spec_Next_Iteration.md`
  - `docs/next_iteration_working_stream.md`
  - `docs/adr/0001-oss-core-vs-cloud-boundary.md`
