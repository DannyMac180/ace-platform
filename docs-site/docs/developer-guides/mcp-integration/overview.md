---
sidebar_position: 1
---

# MCP Integration Overview

Connect your AI agents to ACE using the Model Context Protocol (MCP).

## What is MCP?

The **Model Context Protocol (MCP)** is an open protocol for connecting AI models to external tools and data sources. ACE provides an MCP server that exposes playbooks and evolution features as tools.

Benefits of MCP integration:
- **No code required** - Configure and use immediately
- **Bidirectional** - Read playbooks and record outcomes
- **Real-time** - Changes reflect immediately
- **Secure** - API key authentication

## MCP Server Endpoint

```
https://aceagent.io/mcp
```

## Available Tools

ACE's MCP server exposes these tools:

### list_playbooks

List all playbooks accessible with your API key.

**Returns:** Markdown-formatted list of playbooks with IDs and descriptions.

### find_playbook

Find the best matching playbook for a task using semantic similarity.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_description` | string | Yes | Task to match |

**Returns:** Best match with playbook ID, confidence score, and alternative match.

### get_playbook

Get the content of a specific playbook.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `playbook_id` | string | Yes | Playbook UUID |
| `version` | integer | No | Specific version (default: current) |
| `section` | string | No | Filter to section by heading |

**Returns:** Markdown-formatted playbook content including name, description, and version.

### create_playbook

Create a new playbook.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Playbook name |
| `description` | string | No | Brief description |
| `initial_content` | string | No | Markdown content for version 1 (automatically converted to ACE bullet format) |

**Returns:** Success message with playbook ID.

### create_version

Create a new version of an existing playbook.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `playbook_id` | string | Yes | Playbook UUID |
| `content` | string | Yes | New markdown content (automatically converted to ACE bullet format) |
| `diff_summary` | string | No | Description of changes |

**Returns:** Success message with version number.

### record_outcome

Record the outcome of a task performed with a playbook.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `playbook_id` | string | Yes | Playbook UUID |
| `task_description` | string | Yes | What task was performed |
| `outcome` | string | Yes | "success", "partial", or "failure" |
| `notes` | string | No | Additional context |
| `reasoning_trace` | string | No | Agent's reasoning process |

**Returns:** Success message confirming the outcome was recorded.

### trigger_evolution

Manually trigger playbook evolution.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `playbook_id` | string | Yes | Playbook UUID |

**Returns:** Job ID and status for tracking the evolution.

### get_evolution_status

Check the status of an evolution job.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `job_id` | string | Yes | Evolution job ID |

**Returns:** Job status, progress, timing, and any error information.

## Authentication

MCP requires API key authentication via the `X-API-Key` header:

```json
{
  "headers": {
    "X-API-Key": "YOUR_API_KEY"
  }
}
```

### Required Scopes

| Tool | Required Scope |
|------|----------------|
| `list_playbooks` | `playbooks:read` |
| `find_playbook` | `playbooks:read` |
| `get_playbook` | `playbooks:read` |
| `create_playbook` | `playbooks:write` |
| `create_version` | `playbooks:write` |
| `record_outcome` | `outcomes:write` (+ email verification) |
| `trigger_evolution` | `evolution:write` (+ email verification) |
| `get_evolution_status` | `evolution:read` |

## Connection

Connect via Streamable HTTP:

```
https://aceagent.io/mcp
```

Use HTTP transport in your MCP client.
Legacy SSE endpoints (`https://aceagent.io/mcp/sse` and `/mcp/messages`) remain available through **May 22, 2026**.

## Quick Setup

### Claude Desktop

```json
{
  "mcpServers": {
    "ace": {
      "type": "http",
      "url": "https://aceagent.io/mcp",
      "headers": {
        "X-API-Key": "YOUR_API_KEY"
      }
    }
  }
}
```

[Detailed Claude Desktop setup →](/docs/developer-guides/mcp-integration/claude-desktop)

### Claude Code

```json
{
  "mcpServers": {
    "ace": {
      "type": "http",
      "url": "https://aceagent.io/mcp",
      "headers": {
        "X-API-Key": "YOUR_API_KEY"
      }
    }
  }
}
```

[Detailed Claude Code setup →](/docs/developer-guides/mcp-integration/claude-code)

### Any MCP Client

Any MCP client that supports HTTP transport can connect to ACE:

```json
{
  "mcpServers": {
    "ace": {
      "type": "http",
      "url": "https://aceagent.io/mcp",
      "headers": {
        "X-API-Key": "YOUR_API_KEY"
      }
    }
  }
}
```

## Configuring Agent Instructions

After connecting the MCP server, you need to tell your agent *when* and *how* to use your playbooks. Add instructions to your agent's custom instructions file (e.g., `CLAUDE.md`, `AGENTS.md`, system prompt, or equivalent).

### Recommended Instructions Template

```markdown
## ACE Playbooks

This project uses ACE for self-improving AI instructions.
The ACE MCP server is configured and available.

### Workflow

For each new task (or when task intent changes materially):

1. **Discover relevant playbooks first (semantic search)**
   - Summarize the request as a concise task description
   - Prefer `find_playbook(task_description="<task description>")` to get the best match
   - If needed, use `list_playbooks(task="<task description>")` to review ranked alternatives
   - If no relevant playbook is found, continue normally and do not force playbook usage

2. **Load playbook instructions before doing the task (Generator step)**
   - Use `get_playbook(playbook_id="<selected id>")` for the selected playbook
   - Read the playbook content before starting execution
   - Apply those instructions during planning and implementation

3. **Execute the task using the playbook guidance**
   - Use one **primary** playbook for execution and outcome attribution
   - If multiple playbooks are relevant, keep additional playbooks as supporting context only

4. **Record outcomes automatically after task completion**
   - Call `record_outcome` exactly once per completed, playbook-guided task
   - Include all relevant fields:
     - `playbook_id`: ID of the primary playbook used
     - `task_description`: What was attempted, including scope and deliverable summary
     - `outcome`: `success`, `partial`, or `failure`
     - `notes`: What worked, what failed, key decisions, and blockers
     - `reasoning_trace`: Concise summary of reasoning and tradeoffs
   - If recording fails (permissions, validation, rate limit), report the error and continue helping the user

5. **Check for evolution when applicable**
   - If you manually call `trigger_evolution` and receive a Job ID, call `get_evolution_status(job_id=...)`
   - Do not call `get_evolution_status` without a known Job ID
```

### Where to Add Instructions

| Agent Type | Location |
|------------|----------|
| Claude Code | `CLAUDE.md` in project root |
| Codex | `AGENTS.md` in project root |
| Claude Desktop | Project instructions or conversation |
| Custom agents | System prompt or configuration file |
| LangChain/LlamaIndex | Agent system message |

### Tips for Effective Instructions

1. **Run discovery per task, not per message** - Reduces unnecessary calls while preserving relevance
2. **Load playbook content before execution** - Retrieval without applying content does not improve outcomes
3. **Use one primary playbook per task** - This keeps outcome attribution and evolution data clean
4. **Capture rich outcome details** - Better `notes` and `reasoning_trace` improve future evolution quality
5. **Keep it concise and explicit** - Short, direct instructions are more reliably followed

### Dynamic Playbook Discovery

The **Recommended Instructions Template** above already includes dynamic, semantic playbook discovery and follow-up workflow steps. Use that template as the single source of truth to avoid duplicated or drifting instructions.

## Usage Patterns

### Using a Playbook

```
1. Find best playbook match for the task
2. Get playbook content for the selected ID
3. Execute task with one primary playbook
4. Record one outcome after completion
```

### Evolution Workflow

```
1. Use playbooks and record outcomes
2. After enough outcomes, trigger evolution (or wait for auto-evolution every 5 outcomes)
3. Check evolution status only when you have a job ID
4. Get new version when complete
```

## Error Handling

MCP tools return plain-text responses. Most failures begin with `Error:` (plus a few actionable non-`Error:` messages).

Common error message patterns:

| Pattern | Meaning | Typical Action |
|------|-------------|-------------|
| `Error: No API key provided...` | Missing API key | Set `X-API-Key`, `Authorization: Bearer`, tool `api_key`, or `ACE_API_KEY` |
| `Error: Invalid or revoked API key` | Bad or revoked key | Regenerate key and retry |
| `Error: API key lacks '<scope>' scope` | Key missing required permission | Create/use a key with the needed scope |
| `Error: ... not found` | Resource missing or inaccessible | Verify IDs and ownership |
| `Error: Access denied - ... belongs to another user` | Resource exists but belongs to someone else | Use resources owned by the authenticated user |
| `Error: Invalid ... format` / `Error: Invalid outcome status ...` | Invalid input values | Fix parameter format/value and retry |
| `Error: ... is required ...` / `Error: ... exceeds maximum size ...` | Validation failure | Provide required fields and keep payloads within limits |
| `Error: Rate limit exceeded ...` | Throttle reached | Wait and retry after the window resets |
| `Error: Email verification required ...` | User email not verified | Verify email, then retry |
| `Error: Start your free trial or subscribe to continue.` (and related subscription errors) | Account/subscription state blocks tool use | Start trial, subscribe, or fix billing status |
| `Evolution blocked: A payment method is required ...` | Manual evolution blocked by payment method requirement | Add a card, then trigger evolution again |
| `No playbooks found. Create one in the dashboard first.` | Valid call but user has no playbooks yet | Create a playbook before discovery/retrieval |

## Best Practices

1. **Discover playbooks semantically per task** - Use `find_playbook` (or `list_playbooks(task=...)`) when task intent changes
2. **Load instructions before execution** - Fetch the selected playbook with `get_playbook` before planning and implementation
3. **Use one primary playbook per task** - Keep outcome attribution clean and evolution signals high quality
4. **Record one rich outcome per completed task** - Include `task_description`, `outcome`, `notes`, and `reasoning_trace`
5. **Cache with refresh triggers** - Reuse playbook content, but refresh when task intent or target version changes
6. **Retry selectively** - Retry transient/rate-limit failures; fix-and-retry auth, scope, validation, and subscription errors
7. **Adopt new versions deliberately** - Pin versions for stable workflows and review evolved versions before relying on them

## Troubleshooting

### Connection Refused

- Check the MCP server URL
- Verify network connectivity
- Ensure your MCP client is configured for HTTP transport to `https://aceagent.io/mcp`

### Authentication Failed

- Verify one authentication path is configured correctly:
  - `X-API-Key` header
  - `Authorization: Bearer <token>` header
  - tool `api_key` parameter
  - `ACE_API_KEY` environment variable
- Check API key has required scopes
- Ensure key isn't revoked

### Tool Not Found

- Refresh MCP client connection
- Check server version compatibility
- Verify your MCP client is connected to the ACE server and tools are loaded
- Confirm you are calling valid tool names (for example: `list_playbooks`, `find_playbook`, `get_playbook`, `record_outcome`, `trigger_evolution`, `get_evolution_status`)

### Access or Billing Blocked

- If you see `Error: Email verification required ...`, verify your account email and retry
- If you see `Error: Start your free trial or subscribe to continue.` (or related subscription errors), start a trial/subscribe or fix billing status
- If you see `Evolution blocked: A payment method is required ...`, add a payment method, then retry `trigger_evolution`
- If you see `No playbooks found. Create one in the dashboard first.`, create a playbook before running discovery/retrieval tools

## Next Steps

- [Set up Claude Desktop](/docs/developer-guides/mcp-integration/claude-desktop)
- [Set up Claude Code](/docs/developer-guides/mcp-integration/claude-code)
