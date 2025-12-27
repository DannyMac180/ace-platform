# MCP Integration Guide

This guide explains how to integrate the ACE Platform MCP server with LLM clients like Claude Desktop and Claude Code.

## Overview

The ACE Platform exposes a Model Context Protocol (MCP) server that allows LLM agents to:
- List and retrieve playbooks
- Record task outcomes
- Trigger and monitor playbook evolution

## Prerequisites

1. **ACE Platform Account**: Register at the platform and create at least one playbook
2. **API Key**: Generate an API key with appropriate scopes via the API

### Generating an API Key

```bash
# First, login to get an access token
curl -X POST https://your-ace-platform.fly.dev/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "your-password"}'

# Create an API key with the required scopes
curl -X POST https://your-ace-platform.fly.dev/auth/api-keys \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Claude Desktop",
    "scopes": ["playbooks:read", "outcomes:write", "evolution:read", "evolution:write"]
  }'
```

Save the returned API key securely - it won't be shown again.

## Available Tools

### get_playbook
Retrieve a playbook's content by ID.

**Parameters:**
- `playbook_id` (required): UUID of the playbook
- `api_key` (required): Your API key
- `version` (optional): Specific version number
- `section` (optional): Filter to a specific section

**Required Scope:** `playbooks:read`

### list_playbooks
List all playbooks for the authenticated user.

**Parameters:**
- `api_key` (required): Your API key

**Required Scope:** `playbooks:read`

### record_outcome
Record a task outcome for playbook evolution.

**Parameters:**
- `playbook_id` (required): UUID of the playbook
- `task_description` (required): Description of the task attempted
- `outcome` (required): Status - 'success', 'failure', or 'partial'
- `api_key` (required): Your API key
- `notes` (optional): Additional notes
- `reasoning_trace` (optional): Reasoning trace/log

**Required Scope:** `outcomes:write`

### trigger_evolution
Manually trigger playbook evolution.

**Parameters:**
- `playbook_id` (required): UUID of the playbook
- `api_key` (required): Your API key

**Required Scope:** `evolution:write`

### get_evolution_status
Check the status of an evolution job.

**Parameters:**
- `job_id` (required): UUID of the evolution job
- `api_key` (required): Your API key

**Required Scope:** `evolution:read`

## Claude Desktop Configuration

Add the ACE Platform MCP server to your Claude Desktop configuration.

### Local Development (stdio transport)

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "ace-platform": {
      "command": "python",
      "args": ["-m", "ace_platform.mcp.server", "stdio"],
      "env": {
        "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/ace_platform",
        "REDIS_URL": "redis://localhost:6379/0"
      }
    }
  }
}
```

### Using uvx (recommended for development)

```json
{
  "mcpServers": {
    "ace-platform": {
      "command": "uvx",
      "args": ["--from", "/path/to/ace-platform", "python", "-m", "ace_platform.mcp.server", "stdio"],
      "env": {
        "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/ace_platform"
      }
    }
  }
}
```

### Production (SSE transport)

For production deployments, the MCP server runs with SSE transport. Configure your client to connect via HTTP:

```json
{
  "mcpServers": {
    "ace-platform": {
      "transport": "sse",
      "url": "https://your-ace-platform.fly.dev:8001/sse"
    }
  }
}
```

## Claude Code Configuration

Add the MCP server to your Claude Code settings:

```json
{
  "mcpServers": {
    "ace-platform": {
      "command": "python",
      "args": ["-m", "ace_platform.mcp.server"],
      "cwd": "/path/to/ace-platform",
      "env": {
        "DATABASE_URL": "postgresql://postgres:postgres@localhost:5432/ace_platform",
        "REDIS_URL": "redis://localhost:6379/0"
      }
    }
  }
}
```

## Example Workflow

Here's a typical workflow for using ACE Platform with an LLM agent:

### 1. List Available Playbooks

```
User: List my playbooks

Claude: [Calls list_playbooks tool with api_key]

Response:
# Your Playbooks

- **Coding Agent** (`550e8400-e29b-41d4-a716-446655440000`)
  A playbook for software development tasks...
```

### 2. Get Playbook Content

```
User: Show me the Coding Agent playbook

Claude: [Calls get_playbook tool with playbook_id and api_key]

Response:
# Coding Agent (v3)

A playbook for software development tasks.

---

## Core Principles
- Write clean, maintainable code
- Test before committing
...
```

### 3. Record an Outcome

```
User: I successfully completed a refactoring task using the playbook

Claude: [Calls record_outcome tool]

Response:
Outcome recorded successfully (ID: abc123). Status: success
```

### 4. Trigger Evolution (Optional)

```
User: Evolve the playbook with the new learnings

Claude: [Calls trigger_evolution tool]

Response:
Evolution job queued (Job ID: def456). Check back later for results.
```

### 5. Check Evolution Status

```
User: What's the status of the evolution?

Claude: [Calls get_evolution_status tool]

Response:
# Evolution Job Status

**Job ID:** def456
**Status:** completed
**Outcomes Processed:** 5

## Versions
- **From Version:** v3
- **To Version:** v4
```

## API Key Scopes

| Scope | Description |
|-------|-------------|
| `playbooks:read` | Read playbook content and list playbooks |
| `playbooks:write` | Create and update playbooks |
| `outcomes:read` | Read outcome records |
| `outcomes:write` | Create outcome records |
| `evolution:read` | Read evolution job status |
| `evolution:write` | Trigger evolution jobs |

## Environment Variables

The MCP server uses these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MCP_SERVER_HOST` | `0.0.0.0` | Server bind host |
| `MCP_SERVER_PORT` | `8001` | Server port |
| `DATABASE_URL` | - | PostgreSQL connection string |
| `REDIS_URL` | - | Redis connection string (for Celery) |

## Troubleshooting

### Connection Issues

1. **Check server is running:**
   ```bash
   python -m ace_platform.mcp.server stdio
   ```

2. **Verify database connection:**
   ```bash
   psql $DATABASE_URL -c "SELECT 1"
   ```

3. **Check logs:**
   ```bash
   # Local
   python -m ace_platform.mcp.server 2>&1 | tee mcp.log

   # Fly.io
   fly logs -a ace-platform -p mcp
   ```

### Authentication Errors

- Ensure API key is valid and not revoked
- Check that API key has required scopes for the operation
- Verify API key belongs to user who owns the playbook

### Evolution Not Working

- Check Redis is running (`redis-cli ping`)
- Verify Celery worker is running
- Check for pending outcomes: need at least 1 unprocessed outcome

## Security Considerations

1. **API Key Storage**: Store API keys securely, never commit to version control
2. **Scope Limitation**: Only request scopes you need
3. **Key Rotation**: Periodically rotate API keys
4. **Revocation**: Revoke unused or compromised keys immediately

## Further Resources

- [MCP Protocol Specification](https://modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [ACE Platform API Documentation](/docs)
