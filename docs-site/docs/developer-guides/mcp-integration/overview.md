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

MCP requires API key authentication via the `AUTHORIZATION` environment variable:

```json
{
  "env": {
    "AUTHORIZATION": "Bearer YOUR_API_KEY"
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

Used with `mcp-remote` or similar SSE clients.

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
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://aceagent.io/mcp/sse"],
      "env": {
        "AUTHORIZATION": "Bearer YOUR_API_KEY"
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
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://aceagent.io/mcp/sse"],
      "env": {
        "AUTHORIZATION": "Bearer YOUR_API_KEY"
      }
    }
  }
}
```

[Detailed Claude Code setup →](/docs/developer-guides/mcp-integration/claude-code)

### Custom Agents

Build your own MCP client:

```python
from mcp import ClientSession, StdioServerParameters

async with ClientSession(
    StdioServerParameters(command="npx", args=["-y", "mcp-remote", url])
) as session:
    result = await session.call_tool("get_playbook", {"playbook_id": "abc-123"})
```

[Custom agent guide →](/docs/developer-guides/mcp-integration/custom-agents)

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
