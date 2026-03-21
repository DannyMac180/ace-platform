---
sidebar_position: 2
---

# Workspaces & Teams

Hosted ACE now uses one workspace model for both solo and collaborative users.

If you use the hosted product, you work inside a workspace. A solo hosted user belongs to a `personal` workspace. When you need collaboration, that same workspace can be upgraded to a `team` workspace.

## Understand The Two Layers

ACE Cloud has two separate concepts that often show up on the same screens:

| Layer | What it controls |
| --- | --- |
| Workspace plan | Whether the workspace is `personal`, `team`, or `enterprise`, plus collaboration features such as invites, shared workspace access, and roles |
| Billing subscription | Trial state, hosted access, and usage limits for the workspace |

This means a hosted user can have:

- a `personal` workspace with active hosted access
- a `team` workspace with the same hosted access plus collaboration features
- subscription changes without changing the underlying workspace model

## Personal Workspaces

A hosted `personal` workspace is the ACE Cloud shape for one user.

Current product behavior:

- every hosted user belongs to a workspace
- a `personal` workspace has exactly one seat
- the workspace owner is the only member
- invites and shared workspace features are off
- hosted cloud features such as sync, backups, and managed inference stay available through the hosted plan

This is the hosted equivalent of "solo ACE," but it now uses the same workspace model as team accounts.

## What Changed For Existing Hosted Solo Users

If you already used hosted ACE before the workspace rollout, your account is mapped into a hosted `personal` workspace.

What changes:

- your hosted solo account is now represented as a `personal` workspace
- the seat model is explicit: one user, one hosted workspace
- the upgrade path to team collaboration is now part of the same workspace model

What does not change:

- your existing hosted data stays with the same account
- your solo workflow does not require any team setup
- collaboration features stay off until you upgrade to a team workspace

## Team Workspaces

A `team` workspace is the same hosted workspace model with collaboration enabled.

Compared with a personal workspace, a team workspace adds:

- member invitations
- shared workspace access
- shared playbook review and approval features
- workspace roles
- audit-log support

Current workspace defaults and limits:

- team workspaces require at least 2 seats
- the current backend default is 5 seats when a personal workspace is upgraded without a custom seat count
- pending invitations count against the workspace seat limit until they are accepted or canceled

In the hosted app today, team workspace management primarily shows up in:

- **Usage** for the in-place upgrade action
- **Settings** → **Workspace Members** for invites, acceptance, pending invites, and member removal
- **Dashboard** for approved shared playbooks in a team workspace

## Upgrade A Personal Workspace To Team

The current hosted UI upgrades the workspace in place. It does not create a second workspace for you.

1. Open **Usage** in the hosted app.
2. Find the plan status card.
3. Click **Upgrade Workspace To Team**.
4. Wait for the workspace plan to update.

After the upgrade:

- your workspace plan changes from `personal` to `team`
- your existing hosted data stays in the same workspace
- collaboration features such as invites and shared workspace access turn on
- **Settings** → **Workspace Members** becomes the place to manage team membership

## Invite Teammates

Current hosted invite flow:

1. Open **Settings**.
2. Go to **Workspace Members**.
3. Choose the team workspace you want to manage.
4. Enter the teammate's email address.
5. Choose a role: `member`, `reviewer`, `admin`, or `owner`.
6. Click **Send invite**.

Important details:

- you cannot invite your own email address
- you must have available seats before ACE will create the invite
- an active invite for the same email blocks duplicate invites until the first invite is accepted or canceled

## Accept An Invite

The invite must be accepted by the account whose email matches the invited address.

1. Sign in with the invited email address.
2. Open **Settings**.
3. Go to **Workspace Members**.
4. Find **Pending invitations for you**.
5. Click **Accept**.

If you sign in with a different email address, ACE will not show that invitation as available for acceptance.

## Manage Members And Pending Invites

For team workspaces, the hosted Settings page shows:

- a **Members** list for each team workspace you belong to
- a **Pending invites** list for invitations that have not been accepted yet

Current hosted behavior:

- owners can send invites
- owners can cancel pending invites
- owners can remove other members
- you cannot remove yourself from the current Settings UI flow

## Workspace Roles

Hosted ACE currently uses four workspace roles:

| Role | What it is for |
| --- | --- |
| `owner` | Full workspace ownership. In the current hosted UI, owner is the role that sees invite, cancel, and member-removal controls. |
| `admin` | Administrative collaborator role. The workspace APIs treat admins as managers for workspace settings and seats. |
| `reviewer` | Review-focused collaborator role for shared playbook approval flows when approvals are enabled. |
| `member` | Standard collaborator role without workspace-management permissions. |

:::note
The current hosted Settings page exposes invite and member-management controls to owners. The workspace APIs also treat `admin` as a manager role for settings and seats, so API behavior is broader than the current Settings UI surface.
:::

## Personal vs Team At A Glance

| Capability | `personal` workspace | `team` workspace |
| --- | --- | --- |
| Seats | 1 | 2 or more |
| Shared members | No | Yes |
| Invitations | No | Yes |
| Shared workspace access | No | Yes |
| Workspace roles | Owner only in practice | Owner, admin, reviewer, member |
| Hosted solo workflow | Yes | Yes |
| Team collaboration | No | Yes |

## Related Guides

- See [Billing & Subscriptions](/docs/user-guides/billing-subscriptions) for subscription tiers, usage, and hosted billing state.
- See [Creating an Account](/docs/getting-started/creating-account) for hosted signup and verification.
- See [Core Concepts](/docs/getting-started/core-concepts#hosted-workspaces) for the high-level hosted workspace model.
