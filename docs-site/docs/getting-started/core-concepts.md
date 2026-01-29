---
sidebar_position: 2
---

# Core Concepts

Understanding the fundamental concepts behind ACE.

## Playbooks

A **playbook** is a structured set of instructions that guides an AI agent on how to perform a specific task. Think of it as a detailed standard operating procedure for your AI.

### Anatomy of a Playbook

```markdown
# Task Name

## Role
Define the agent's persona and expertise level.

## Context
Background information the agent needs.

## Guidelines
Step-by-step instructions or rules to follow.

## Output Format
How results should be structured.

## Examples (optional)
Sample inputs and outputs.
```

### Playbook Properties

| Property | Description |
|----------|-------------|
| `id` | Unique identifier (UUID) |
| `name` | Human-readable name |
| `description` | Brief summary of purpose |
| `content` | The actual playbook instructions (Markdown) |
| `current_version` | Active version number |
| `created_at` | Creation timestamp |
| `updated_at` | Last modification timestamp |

## Versions

Every playbook maintains a **version history**. Versions are created when:

1. You manually edit the playbook
2. The system evolves the playbook based on outcomes

### Version Properties

| Property | Description |
|----------|-------------|
| `version_number` | Sequential version identifier |
| `content` | Playbook content at this version |
| `change_summary` | Description of what changed |
| `created_at` | When this version was created |
| `is_evolution` | Whether this version came from evolution |

### Viewing Version History

From the dashboard, click on a playbook and navigate to the **Versions** tab to:

- See all historical versions
- Compare any two versions
- View evolution summaries
- Restore a previous version

## Outcomes

An **outcome** is a record of how a playbook performed on a specific task. Outcomes are the fuel for playbook evolution.

### Recording Effective Outcomes

Good outcomes include:

```json
{
  "playbook_id": "abc-123",
  "task_description": "Reviewed authentication refactor PR with 500+ line changes",
  "outcome": "success",
  "notes": "Identified race condition in token refresh logic. Suggested using mutex.",
  "reasoning_trace": "Analyzed auth flow, found concurrent access issue..."
}
```

### Outcome Fields

| Field | Required | Description |
|-------|----------|-------------|
| `playbook_id` | Yes | Which playbook was used |
| `task_description` | Yes | What task was performed |
| `outcome` | Yes | Result: "success", "partial", or "failure" |
| `notes` | No | Additional context or feedback |
| `reasoning_trace` | No | Agent's reasoning process |

### Outcome Values

- **success** - Task completed correctly
- **partial** - Task completed but with issues
- **failure** - Task did not complete or was incorrect

:::tip
Include detailed notes even for successful outcomes. They help the evolution process understand *why* something worked well.
:::

## Evolution

**Evolution** is the process by which ACE improves playbooks based on accumulated outcomes.

### How Evolution Works

```
Outcomes → Reflector → Insights → Curator → New Version
```

1. **Collect Outcomes** - System gathers unprocessed outcomes
2. **Reflect** - Reflector agent analyzes patterns and issues
3. **Generate Insights** - Identifies what's working and what isn't
4. **Curate** - Curator agent drafts improved playbook version
5. **Publish** - New version becomes active

### Evolution Triggers

Evolution happens:

- **Automatically** - After threshold outcomes are recorded (default: 5)
- **Manually** - When you trigger it from the dashboard or API

### Evolution Status

| Status | Description |
|--------|-------------|
| `pending` | Queued, waiting to start |
| `in_progress` | Currently processing |
| `completed` | Successfully created new version |
| `failed` | Error occurred during evolution |

## API Keys

**API keys** authenticate your requests to ACE.

### Scopes

Each key has specific permissions:

| Scope | Allows |
|-------|--------|
| `playbooks:read` | Read playbook content and versions |
| `playbooks:write` | Create, update, delete playbooks |
| `outcomes:read` | View recorded outcomes |
| `outcomes:write` | Record new outcomes |
| `evolution:read` | Check evolution status |
| `evolution:write` | Trigger manual evolution |
| `usage:read` | View usage statistics |

### Key Types

- **Full Access** - All scopes (for development/testing)
- **Read Only** - Only read scopes (for production agents)
- **Custom** - Choose specific scopes

:::warning
Never expose API keys with write scopes in client-side code or public repositories.
:::

## MCP (Model Context Protocol)

**MCP** is a protocol for connecting AI agents to external tools and data sources. ACE provides an MCP server that exposes playbooks as tools.

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `list_playbooks` | List all your playbooks |
| `get_playbook` | Get content of a specific playbook |
| `record_outcome` | Record a task outcome |
| `trigger_evolution` | Manually trigger evolution |
| `get_evolution_status` | Check evolution job status |

### MCP Endpoints

| Environment | URL |
|-------------|-----|
| Production | `https://aceagent.io/mcp/sse` |
| Staging | `https://ace-platform-staging.fly.dev/mcp/sse` |

## Subscriptions & Usage

ACE offers tiered subscriptions:

### Plans

| Plan | Playbooks | Evolutions/mo | Price |
|------|-----------|---------------|-------|
| Free | 3 | 10 | $0 |
| Pro | 25 | 100 | $29/mo |
| Team | Unlimited | Unlimited | $99/mo |

### Usage Tracking

Monitor your usage in the dashboard:

- Playbook count
- Evolution count this month
- Outcome recordings
- API calls

## Next Steps

Now that you understand the core concepts:

- [Create your first playbook](/docs/getting-started/quick-start)
- [Set up MCP integration](/docs/developer-guides/mcp-integration/overview)
- [Learn to record effective outcomes](/docs/developer-guides/recording-outcomes)
