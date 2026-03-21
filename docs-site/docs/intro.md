---
sidebar_position: 1
slug: /
---

# Choose Your ACE Path

ACE is a local-first playbook engine with hosted cloud options for convenience, collaboration, and governance. Use this page to choose the right starting point before you dive into setup details.

## The Four ACE Offers

| Offer | Best for | Start here |
| --- | --- | --- |
| `ACE OSS` | A single user who wants local control or self-managed infrastructure | [ACE OSS & Local Start](/docs/getting-started/oss-local-start) |
| `ACE Cloud Personal` | A solo user who wants ACE-hosted convenience | [ACE Cloud Quick Start](/docs/getting-started/quick-start) |
| `ACE Cloud Team` | A team that needs shared workspaces, invites, and collaboration | [ACE Cloud Plans & Subscriptions](/docs/user-guides/billing-subscriptions#ace-cloud-team) |
| `ACE Enterprise` | An organization that needs governance, compliance, or private deployment options | [ACE Cloud Plans & Subscriptions](/docs/user-guides/billing-subscriptions#ace-enterprise) |

## The Short Version

ACE separates two ideas that are easy to blur together:

- deployment mode: local/self-managed, ACE-hosted cloud, or private deployment
- workspace plan: personal, team, or enterprise

That means:

- `ACE OSS` is a real product, not a crippled trial
- `ACE Cloud Personal` is for one hosted user and does not require a team
- `ACE Cloud Team` adds shared workflows and team administration
- `ACE Enterprise` adds governance, compliance, and deployment control

## Start With The Right Guide

### Start with `ACE OSS` if:

- you want local control or self-managed infrastructure
- you are comfortable managing your own model keys, storage, and backups
- you want the ACE engine without ACE-operated cloud services

Start here: [ACE OSS & Local Start](/docs/getting-started/oss-local-start)

### Start with `ACE Cloud Personal` if:

- you are a solo user who wants hosted convenience
- you want cloud sync, backups, and managed background execution
- you do not need shared team workflows yet

Start here: [ACE Cloud Quick Start](/docs/getting-started/quick-start)

### Start with `ACE Cloud Team` if:

- multiple people need the same ACE workspace
- you need invites, shared playbooks, reviews, or team visibility
- collaboration matters more than simple solo hosting

Start here: [ACE Cloud Plans & Subscriptions](/docs/user-guides/billing-subscriptions#ace-cloud-team)

### Start with `ACE Enterprise` if:

- your organization needs governance, compliance, or audit controls
- procurement requires private deployment or contractual support
- identity management and admin controls are part of the buying decision

Start here: [ACE Cloud Plans & Subscriptions](/docs/user-guides/billing-subscriptions#ace-enterprise)

## Getting Started

1. **[Create an account](/docs/getting-started/creating-account)** - Sign up and verify your email
2. **[Quick Start](/docs/getting-started/quick-start)** - Set up your first playbook in 5 minutes
3. **[ACE CLI](/docs/getting-started/ace-cli)** - Bootstrap a local or agent-friendly setup with the shipped CLI commands
4. **[Core Concepts](/docs/getting-started/core-concepts)** - Understand playbooks, outcomes, and evolution

## Why The Split Matters

The ACE v2 architecture keeps the boundary clear:

- `ACE OSS` stays genuinely useful without ACE-operated services
- hosted value comes from private cloud services such as sync, backups, managed jobs, and team governance
- team and enterprise features build on top of the hosted individual experience instead of replacing it

## What ACE Is

ACE stands for **Agentic Context Engineer**. It uses a three-agent architecture that continuously improves playbooks based on real-world outcomes:

1. **Generator**: produces outputs based on playbook instructions
2. **Reflector**: analyzes outcomes to identify improvement opportunities
3. **Curator**: synthesizes feedback into improved playbook versions

Playbooks are structured instructions for AI agents. Unlike static prompts, ACE playbooks evolve from recorded outcomes, keep version history, and stay accessible through MCP and related tooling.

## Next Steps

- Explore the [Getting Started](/docs/getting-started/quick-start) guide
- Explore the [ACE CLI](/docs/getting-started/ace-cli) guide for local-first onboarding
- Compare paths above, then start with either [ACE OSS & Local Start](/docs/getting-started/oss-local-start) or [ACE Cloud Quick Start](/docs/getting-started/quick-start)
- Learn the shared model in [Core Concepts](/docs/getting-started/core-concepts)
- Learn about [MCP Integration](/docs/developer-guides/mcp-integration/overview)
- Learn how to [record outcomes](/docs/developer-guides/recording-outcomes)
