# ACE Cloud Plans Release Notes And Migration Guide

March 2026

ACE now has a clearer product split:

- `ACE OSS` remains the local-first, self-managed runtime for users who want full control.
- `ACE Cloud Personal` is the hosted plan for one user who wants convenience without self-hosting.
- `ACE Cloud Team` is the hosted plan for shared workspaces, invites, and collaboration.
- `ACE Enterprise` adds governance, compliance, and private deployment options for organizations that need them.

This update makes the hosted line easier to understand without weakening the OSS product.

## What Changed

Before this release, hosted ACE could read like a single solo product with team capabilities added later. The new plan model makes the customer path explicit:

- solo hosted customers belong in `ACE Cloud Personal`
- collaborative work belongs in `ACE Cloud Team`
- governance-heavy or private deployment needs belong in `ACE Enterprise`

The architecture rule behind this release is unchanged: `ACE OSS` stays genuinely useful on its own, while hosted value comes from ACE-operated services such as sync, backups, managed jobs, and team governance.

## Why The New Plans Help

| Plan | Who it is for | Main benefit |
| --- | --- | --- |
| `ACE OSS` | A single user who wants local or self-managed ACE | Full control, BYO infrastructure, and no ACE-operated cloud dependency |
| `ACE Cloud Personal` | A single user who wants hosted ACE | Less setup work, hosted sync, backups, dashboard access, and managed background execution |
| `ACE Cloud Team` | Teams that need to share one ACE workspace | Collaboration, invites, shared playbooks, approvals, and workspace visibility |
| `ACE Enterprise` | Organizations with governance or deployment requirements | Compliance controls, auditability, support, and private deployment options |

## Migration Guidance For Current Hosted Solo Users

If you already use hosted ACE as a solo customer, the target model is a `personal` workspace.

The intended migration outcome is:

- you keep your existing data
- you keep access to the hosted product
- your core solo workflow stays intact
- your workspace maps cleanly to the new hosted plan structure

What changes for you:

- your hosted solo account is represented as `ACE Cloud Personal`
- the seat model is explicit: one user, one hosted workspace
- collaboration features stay off until you decide to upgrade to `ACE Cloud Team`
- the upgrade path to a team workspace becomes clearer when you need invites or shared workflows

What does not change:

- `ACE OSS` is still a valid option for users who prefer self-managed ACE
- hosted convenience remains a first-class product for solo users
- team-only features are additive; they are not required to keep using hosted ACE as an individual

## How To Choose The Right Path

Choose `ACE OSS` if you want local control, self-managed storage, and your own model credentials.

Choose `ACE Cloud Personal` if you want ACE-hosted convenience for one user, including hosted sync, backups, and managed jobs.

Choose `ACE Cloud Team` if multiple people need shared playbooks, invitations, approvals, or team-level visibility.

Choose `ACE Enterprise` if procurement, compliance, auditability, or private deployment terms are part of the buying decision.

## Where To Go Next

- Read [ACE Product Split](./PRODUCT_SPLIT.md) for the detailed OSS versus hosted comparison.
- Start with [Quick Start](./QUICKSTART.md) if you want the hosted path.
- Start with [ACE OSS Overview](./oss-overview.md) if you want the self-managed path.
- Use [Self-Hosted Deployment Guide](./SELF_HOSTED_DEPLOYMENT.md) if you want to run the full stack yourself.
