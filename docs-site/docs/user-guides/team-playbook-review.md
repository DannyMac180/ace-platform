---
sidebar_position: 2
---

# Team Playbook Review & Registry

Use this guide when your workspace shares playbooks across a team instead of
keeping every playbook strictly personal.

## How Team Playbooks Move Through Review

Every new playbook starts as a `draft`. That lets the author edit content,
create versions, and decide when it is ready for review without exposing it in
the shared team registry yet.

### Review States

| State | Meaning | Where you see it |
|-------|---------|------------------|
| `draft` | Private working copy | Playbook detail page and playbook cards |
| `proposed` | Submitted for review | Playbook detail page and playbook cards |
| `approved` | Marked as ready for team reuse | Playbook detail page and playbook cards |
| `archived` | Removed from active circulation | Playbook detail page and playbook cards |

### Review Actions

The playbook detail page shows the actions that are valid for the current
review state.

| Current state | Available actions | Result |
|---------------|-------------------|--------|
| `draft` | `Submit for Review`, `Archive` | Moves the playbook to `proposed` or `archived` |
| `proposed` | `Approve`, `Return to Draft`, `Archive` | Publishes it to `approved`, sends it back for edits, or archives it |
| `approved` | `Return to Draft`, `Archive` | Removes it from active approval so it can be revised or retired |
| `archived` | `Return to Draft` | Reopens the playbook for edits and future review |

## Activity History

Open a playbook and switch to the **Activity** tab to see its review history.
Each entry records:

- the action that happened, such as `Created draft`, `Submitted for review`,
  `Approved`, `Returned to draft`, or `Archived`
- the state transition, for example `draft -> proposed`
- who performed the action when an actor is available
- the timestamp for the change

This history is the easiest way to understand how a shared playbook reached its
current state and who last changed it.

## Shared Registry

The dashboard section is labeled **Approved team playbooks** and acts as the
shared registry for the workspace.

Today, the registry is populated from active team playbooks. The review state
is still useful metadata on the playbook itself, but the backend does not
currently enforce an `approved`-only filter for this list.

The registry helps members find reusable playbooks without searching through
each person's private drafts. Each card shows:

- the playbook name and description
- the owner or `You` when the shared playbook already belongs to you
- version count
- whether the playbook is ready to reuse or already in your library

If no active shared playbooks are available yet, the registry stays empty.

## Reusing a Shared Team Playbook

To reuse a playbook from the shared registry:

1. Open the dashboard in a team workspace.
2. Find the playbook in **Approved team playbooks**.
3. Click **Reuse**.

ACE copies that shared playbook into your own library so you can work from it
without editing the source playbook in place.

If the registry card says **In your library**, the current shared playbook is
already owned by you, so there is nothing new to copy.

## Typical Workflow

1. Create a playbook from the dashboard.
2. Refine the content until the draft is ready.
3. Open the playbook detail page and click **Submit for Review**.
4. Review the playbook content on its detail page and use **Approve** or
   **Return to Draft** when you want to change its review state again.
5. Open the dashboard's shared registry section to find active team playbooks.
6. Use **Reuse** to copy a shared playbook into your own library.

## Related Docs

- [Creating Playbooks](/docs/user-guides/creating-playbooks)
- [Core Concepts](/docs/getting-started/core-concepts)
