# ACE Product Split

ACE is offered in four distinct ways:

- `ACE OSS`: local-first, self-managed ACE for a single user
- `ACE Cloud Personal`: ACE-hosted convenience for one user
- `ACE Cloud Team`: ACE-hosted collaboration for multi-user teams
- `ACE Enterprise`: governance, compliance, and private deployment options

This page explains the difference so users can quickly pick the right path.

## The Short Version

ACE separates two ideas that are easy to blur together:

- `deployment mode`: local/self-managed vs ACE-hosted vs private deployment
- `workspace plan`: personal vs team vs enterprise

That means:

- you do not need a team to pay for hosted ACE
- the OSS product is not a crippled demo
- enterprise is not just "more seats"; it adds governance and deployment control

## Offer Comparison

| Offer | Who runs it | Who it is for | What you get | What you do not get |
| --- | --- | --- | --- | --- |
| `ACE OSS` | You | A single user who wants full control or self-hosting | Local runtime, local API/CLI/MCP, local storage, BYO model keys, import/export, self-managed deployment | ACE-hosted sync, backups, managed inference wallet, hosted eval workers, shared team workspace |
| `ACE Cloud Personal` | ACE | A single user who wants hosted convenience | One-user hosted workspace, cloud sync across devices, backups, hosted evals/background jobs, optional managed inference wallet, less setup work | Team workspace, member invites, shared team registry, approvals, team admin workflows |
| `ACE Cloud Team` | ACE | A team that needs shared workflows | Everything in Cloud Personal plus team workspace, member invites, shared playbook registry, reviews/approvals, permissions, team accountability | Enterprise-grade identity/compliance commitments and private deployment terms |
| `ACE Enterprise` | ACE or private deployment under commercial terms | Organizations with governance, compliance, or procurement requirements | Everything in Cloud Team plus advanced governance, auditability, contractual support, and private deployment options | A lighter-weight setup; this is for organizations with control requirements, not just basic collaboration |

## How To Choose

### Choose `ACE OSS` if:

- you want to run ACE locally or on your own infrastructure
- you are comfortable managing storage, backups, and model credentials
- you primarily need a powerful single-user runtime

### Choose `ACE Cloud Personal` if:

- you are a solo user who wants ACE to work without self-hosting overhead
- you want your workspace to follow you across machines
- you want hosted backups, sync, and managed background execution

### Choose `ACE Cloud Team` if:

- multiple people need to use the same ACE workspace
- you need shared playbooks, invitations, reviews, or ownership controls
- collaboration matters more than just hosted convenience

### Choose `ACE Enterprise` if:

- your organization needs governance, compliance, or audit controls
- procurement or security policy requires private deployment or contractual support
- identity management and admin controls matter as much as the product itself

## Important Boundaries

The product split follows the ACE v2 architecture decisions:

- `ACE OSS` must remain genuinely useful without ACE-operated cloud services
- `Cloud Personal` adds hosted convenience for one user rather than weakening OSS
- `Cloud Team` adds collaboration and shared workspace behavior
- `Enterprise` adds governance and deployment control on top of the team model

In practice, that means premium value comes from private services ACE operates, not from hiding core functionality behind local license checks.

## Common Misunderstandings

### "If I pay for hosted ACE, do I need a team?"

No. `ACE Cloud Personal` is a real hosted product for one user.

### "Do I need hosted OAuth to use ACE?"

No. Hosted OAuth is a convenience option for ACE-hosted environments, not the
only way to onboard. ACE should keep provider-neutral paths available through
local or password-based auth plus API-key access, and `ACE OSS` continues to
support self-managed local/BYO workflows without ACE-operated identity.

### "Is self-hosting the same thing as Enterprise?"

No. `ACE OSS` can be self-managed by an individual. `Enterprise` is the commercial/governance layer for organizations that need stronger controls or private deployment terms.

### "Is Team just a billing wrapper around Personal?"

No. `Cloud Team` exists because shared workspaces, invites, reviews, permissions, and governance are different product needs from solo hosted convenience.

## Related Docs

- [Cloud Plans Release Notes And Migration Guide](./RELEASE_NOTES_CLOUD_PLANS.md)
- [README](../README.md)
- [Quick Start](./QUICKSTART.md)
- [Self-Hosted Deployment Guide](./SELF_HOSTED_DEPLOYMENT.md)
- [ADR 0001: OSS/Core Versus Cloud Boundary](./adr/0001-oss-core-vs-cloud-boundary.md)
