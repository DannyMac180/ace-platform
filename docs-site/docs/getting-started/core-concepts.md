---
sidebar_position: 2
---

# Core Concepts

Understanding the fundamental concepts behind ACE.

## Playbooks

A **playbook** is a structured set of instructions that guides an AI agent on how to perform a specific task. Think of it as a detailed standard operating procedure for your AI.

### Anatomy of a Playbook

Playbooks use the **ACE bullet format**—structured instructions optimized for AI agents and evolution tracking.

<div className="playbook-example" style={{background: 'var(--ifm-color-emphasis-100)', padding: '1.5rem', borderRadius: '8px', marginBottom: '1rem'}}>

#### Code Review Assistant

Guidelines for reviewing code quality, security, and best practices.

**STRATEGIES & INSIGHTS**

- `[check-context-first]` helpful=5 harmful=0 :: Read the PR description and linked issues before reviewing code to understand the intent and scope of changes.
- `[security-mindset]` helpful=4 harmful=0 :: Look for common vulnerabilities: SQL injection, XSS, hardcoded secrets, and improper input validation.

**COMMON MISTAKES TO AVOID**

- `[avoid-nitpicking]` helpful=3 harmful=0 :: Focus on substantive issues over style preferences. Save formatting debates for linter configuration.
- `[explain-why]` helpful=3 harmful=0 :: Don't just say "this is wrong"—explain why and suggest a better approach.

**PROBLEM-SOLVING HEURISTICS**

- `[test-coverage]` helpful=2 harmful=0 :: Check if new code paths have corresponding tests, especially for edge cases and error handling.

</div>

### Bullet Format

Each instruction follows this structure:

```
[semantic-slug] helpful=N harmful=N :: Actionable instruction
```

| Component | Description |
|-----------|-------------|
| `[semantic-slug]` | 2-4 word kebab-case identifier for tracking |
| `helpful=N` | Count of positive outcomes from this instruction |
| `harmful=N` | Count of negative outcomes from this instruction |
| `::` | Separator between metadata and content |
| Instruction | Actionable, imperative guidance (1-2 sentences) |

The `helpful` and `harmful` counters start at 0 and are updated during evolution based on recorded outcomes. Instructions with high harmful scores may be removed or revised.

### Playbook Properties

| Property | Description |
|----------|-------------|
| `id` | Unique identifier (UUID) |
| `name` | Human-readable name |
| `description` | Brief summary of purpose |
| `status` | Playbook status: `active`, `paused`, or `archived` |
| `source` | Origin: `starter`, `user_created`, or `imported` |
| `current_version` | Reference to the active version |
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
| `content` | Playbook content at this version (Markdown) |
| `bullet_count` | Number of ACE-format bullets in this version |
| `diff_summary` | Description of what changed |
| `created_by_job_id` | Evolution job ID if created by evolution (null for manual edits) |
| `created_at` | When this version was created |

### Viewing Version History

From the dashboard, click on a playbook and navigate to the **Versions** tab to:

- See all historical versions
- View evolution summaries
- Compare versions to see what changed

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
- **Manually** - When you trigger it from the dashboard or MCP

### Evolution Status

| Status | Description |
|--------|-------------|
| `queued` | Waiting to start |
| `running` | Currently processing |
| `completed` | Successfully created new version |
| `failed` | Error occurred during evolution |

## API Keys

**API keys** authenticate your MCP tool access to ACE.

### Scopes

Each key has specific permissions:

| Scope | Allows |
|-------|--------|
| `playbooks:read` | Read playbook content and metadata |
| `playbooks:write` | Create and update playbooks |
| `outcomes:read` | Read task outcomes |
| `outcomes:write` | Record task outcomes |
| `evolution:read` | Read evolution job status |
| `evolution:write` | Trigger playbook evolution |
| `*` | Full access to all operations |

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
| `create_playbook` | Create a new playbook |
| `create_version` | Create a new version of a playbook |
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
| Starter | 5 | 100 | $9/mo |
| Pro | 20 | 500 | $29/mo |
| Ultra | 100 | 2,000 | $79/mo |

### Usage Tracking

Monitor your usage in the dashboard:

- Playbook count
- Evolution count this month
- Monthly spending

## Next Steps

Now that you understand the core concepts:

- [Create your first playbook](/docs/getting-started/quick-start)
- [Set up MCP integration](/docs/developer-guides/mcp-integration/overview)
- [Learn to record effective outcomes](/docs/developer-guides/recording-outcomes)
