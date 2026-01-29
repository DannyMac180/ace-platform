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

## MCP Server Endpoints

| Environment | URL | Use Case |
|-------------|-----|----------|
| Production | `https://aceagent.io/mcp/sse` | Production agents |
| Staging | `https://ace-platform-staging.fly.dev/mcp/sse` | Testing |
| Local | `http://localhost:8000/mcp/sse` | Development |

## Available Tools

ACE's MCP server exposes these tools:

### list_playbooks

List all playbooks accessible with your API key.

**Returns:**
```json
{
  "playbooks": [
    {
      "id": "abc-123",
      "name": "Code Review Assistant",
      "description": "Reviews PRs for quality",
      "current_version": 3
    }
  ]
}
```

### get_playbook

Get the content of a specific playbook.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `playbook_id` | string | Yes | Playbook UUID |
| `version` | integer | No | Specific version (default: current) |
| `section` | string | No | Filter to section by heading |

**Returns:**
```json
{
  "name": "Code Review Assistant",
  "version": 3,
  "content": "# Code Review Assistant\n\n## Role\n..."
}
```

### create_playbook

Create a new playbook.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Playbook name |
| `content` | string | Yes | Markdown content |
| `description` | string | No | Brief description |

### create_version

Create a new version of an existing playbook.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `playbook_id` | string | Yes | Playbook UUID |
| `content` | string | Yes | New markdown content |
| `change_summary` | string | No | Description of changes |

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

### trigger_evolution

Manually trigger playbook evolution.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `playbook_id` | string | Yes | Playbook UUID |

**Returns:**
```json
{
  "job_id": "job-xyz-789",
  "status": "pending"
}
```

### get_evolution_status

Check the status of an evolution job.

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `job_id` | string | Yes | Evolution job ID |

**Returns:**
```json
{
  "job_id": "job-xyz-789",
  "status": "completed",
  "new_version": 4,
  "change_summary": "Added input validation guidelines..."
}
```

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
| `get_playbook` | `playbooks:read` |
| `create_playbook` | `playbooks:write` |
| `create_version` | `playbooks:write` |
| `record_outcome` | `outcomes:write` |
| `trigger_evolution` | `evolution:write` |
| `get_evolution_status` | `evolution:read` |

## Connection Methods

### SSE (Server-Sent Events)

The default transport for remote connections:

```
https://aceagent.io/mcp/sse
```

Use the native SSE configuration in your MCP client.

### Stdio

For local development, run the MCP server directly:

```bash
cd ace-platform
source venv/bin/activate
python -m ace_platform.mcp.server
```

Configure clients to use stdio transport.

## Quick Setup

### Claude Desktop

```json
{
  "mcpServers": {
    "ace": {
      "type": "sse",
      "url": "https://aceagent.io/mcp/sse",
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
      "type": "sse",
      "url": "https://aceagent.io/mcp/sse",
      "headers": {
        "X-API-Key": "YOUR_API_KEY"
      }
    }
  }
}
```

[Detailed Claude Code setup →](/docs/developer-guides/mcp-integration/claude-code)

### Any MCP Client

Any MCP client that supports SSE transport can connect to ACE:

```json
{
  "mcpServers": {
    "ace": {
      "type": "sse",
      "url": "https://aceagent.io/mcp/sse",
      "headers": {
        "X-API-Key": "YOUR_API_KEY"
      }
    }
  }
}
```

[Custom agent guide →](/docs/developer-guides/mcp-integration/custom-agents)

## Configuring Agent Instructions

After connecting the MCP server, you need to tell your agent *when* and *how* to use your playbooks. Add instructions to your agent's custom instructions file (e.g., `CLAUDE.md`, `AGENTS.md`, system prompt, or equivalent).

### Recommended Instructions Template

```markdown
## ACE Playbooks

This project uses ACE for self-improving AI instructions.
The ACE MCP server is configured and available.

### Available Playbooks

| Task | Playbook ID | When to Use |
|------|-------------|-------------|
| Code reviews | `abc-123-def` | Before reviewing any PR or code changes |
| Writing tests | `def-456-ghi` | When creating or updating test files |
| Documentation | `ghi-789-jkl` | When writing or updating documentation |

### Workflow

When performing tasks that have a matching playbook:

1. **Before starting**: Fetch the playbook using `get_playbook` with the appropriate ID
2. **During the task**: Follow the playbook instructions carefully
3. **After completing**: Record the outcome using `record_outcome` with:
   - `outcome`: "success", "partial", or "failure"
   - `task_description`: Brief description of what was done
   - `notes`: Any relevant feedback about what worked or didn't
4. **Check for evolution**: If an evolution was triggered, use `get_evolution_status` to report the results

### Example

For a code review task:
1. Call `get_playbook` with playbook_id `abc-123-def`
2. Review the code following the playbook guidelines
3. Call `record_outcome` with the results
```

### Where to Add Instructions

| Agent Type | Location |
|------------|----------|
| Claude Code | `CLAUDE.md` in project root |
| Claude Desktop | Project instructions or conversation |
| Custom agents | System prompt or configuration file |
| LangChain/LlamaIndex | Agent system message |
| AutoGPT/similar | Goals or directives configuration |

### Tips for Effective Instructions

1. **Be explicit about playbook IDs** - Agents can't guess which playbook to use
2. **Define triggers clearly** - Specify what tasks should use which playbooks
3. **Remind about outcomes** - Agents may forget to record outcomes without prompting
4. **Keep it concise** - Long instructions may be ignored or truncated

### Dynamic Playbook Discovery

If you have many playbooks or they change frequently, instruct your agent to discover them:

```markdown
## Using ACE Playbooks

Before starting any task, check for relevant playbooks:

1. **Discover playbooks** - Use the `list_playbooks` tool to see available playbooks
2. **Load relevant playbooks** - Use the `get_playbook` tool to fetch instructions for playbooks that match your current task
3. **Follow the guidelines** - Apply the playbook instructions as you work

After completing a task guided by a playbook:

1. **Record the outcome** - Use the `record_outcome` tool with:
   - `playbook_id`: The playbook you followed
   - `task_description`: What you accomplished
   - `outcome`: "success", "failure", or "partial"
   - `notes`: What worked well, what didn't, and lessons learned

2. **Check for evolution** - If an evolution was triggered, use `get_evolution_status` to report the results to the user
```

This approach is more flexible as it doesn't require maintaining a static list of playbook IDs.

## Usage Patterns

### Using a Playbook

```
1. List playbooks to find the right one
2. Get playbook content
3. Follow playbook instructions for task
4. Record outcome after completion
```

### Evolution Workflow

```
1. Use playbooks and record outcomes
2. After enough outcomes, trigger evolution (or wait for auto)
3. Check evolution status
4. Get new version when complete
```

## Error Handling

MCP tools return errors in a consistent format:

```json
{
  "error": {
    "code": "not_found",
    "message": "Playbook not found"
  }
}
```

Common error codes:

| Code | Description |
|------|-------------|
| `unauthorized` | Invalid or missing API key |
| `forbidden` | Insufficient scopes |
| `not_found` | Resource doesn't exist |
| `rate_limited` | Too many requests |
| `invalid_request` | Malformed parameters |

## Best Practices

1. **Cache playbook content** - Don't fetch before every use
2. **Record outcomes consistently** - Even for successes
3. **Handle errors gracefully** - Implement retries for transient failures
4. **Use specific versions** - Pin versions for production stability
5. **Monitor evolution** - Review new versions before relying on them

## Troubleshooting

### Connection Refused

- Check the MCP server URL
- Verify network connectivity
- Ensure API key is valid

### Authentication Failed

- Verify `AUTHORIZATION` env var format
- Check API key has required scopes
- Ensure key isn't revoked

### Tool Not Found

- Refresh MCP client connection
- Check server version compatibility
- Verify API key scopes include tool access

## Next Steps

- [Set up Claude Desktop](/docs/developer-guides/mcp-integration/claude-desktop)
- [Set up Claude Code](/docs/developer-guides/mcp-integration/claude-code)
- [Build custom agents](/docs/developer-guides/mcp-integration/custom-agents)
