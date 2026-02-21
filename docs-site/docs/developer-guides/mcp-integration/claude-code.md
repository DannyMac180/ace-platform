---
sidebar_position: 3
---

# Claude Code Setup

Integrate ACE with Claude Code for AI-assisted development with self-improving playbooks.

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed
- ACE account with verified email
- API key with appropriate scopes

## Configuration

### Step 1: Create an API Key

1. Go to [app.aceagent.io](https://app.aceagent.io)
2. Navigate to **API Keys**
3. Create a key with all scopes enabled:
   - `playbooks:read` - List and read playbooks
   - `playbooks:write` - Create playbooks and versions
   - `outcomes:write` - Record task outcomes
   - `evolution:write` - Trigger evolution
   - `evolution:read` - Check evolution status

### Step 2: Add the MCP Server

The fastest way to add ACE is with the `claude mcp add` command:

```bash
claude mcp add --transport http ace https://aceagent.io/mcp \
  --header "X-API-Key: YOUR_API_KEY"
```

Legacy SSE compatibility remains available through **May 22, 2026** at `https://aceagent.io/mcp/sse`.

This adds the server to your **local** scope (current project only) by default.

**To make it available across all projects**, use `--scope user`:

```bash
claude mcp add --transport http --scope user ace https://aceagent.io/mcp \
  --header "X-API-Key: YOUR_API_KEY"
```

**To share it with your team**, use `--scope project` (adds to `.mcp.json` in your project root):

```bash
claude mcp add --transport http --scope project ace https://aceagent.io/mcp \
  --header "X-API-Key: YOUR_API_KEY"
```

### Step 3: Verify Setup

Start Claude Code and check the MCP server is connected:

```
> /mcp
```

This shows all connected MCP servers and their status. Then test it:

```
> "List my ACE playbooks"
```

## Using ACE with Claude Code

### Development Workflows

**Code Review:**
```
You: "Get my code-review playbook and review the changes in this PR"
Claude: [Fetches playbook, reviews code following guidelines]
```

**Documentation:**
```
You: "Using my documentation playbook, document the API in src/api/"
Claude: [Follows playbook instructions to create docs]
```

### Recording Outcomes

After Claude completes a task:

```
You: "Record an outcome for the code-review playbook:
- Task: Reviewed authentication module PR
- Outcome: success
- Notes: Caught SQL injection vulnerability in user lookup"
```

### Triggering Evolution

When you want to improve a playbook:

```
You: "Trigger evolution for my code-review playbook"
Claude: [Triggers evolution job]

You: "Check the evolution status for job xyz-123"
Claude: [Reports evolution progress/completion]
```

## Project-Specific Playbooks

Store playbook IDs in your project's `CLAUDE.md` for quick reference:

```markdown
## ACE Playbooks

| Task | Playbook ID | When to Use |
|------|-------------|-------------|
| Code reviews | `abc-123-def` | All PR reviews |
| Documentation | `ghi-456-jkl` | API and README updates |
```

Then reference them in conversations:

> "Using playbook abc-123-def, review the changes in src/"

## Using Environment Variables

Keep API keys out of shared config files using environment variable expansion in `.mcp.json`:

```json
{
  "mcpServers": {
    "ace": {
      "type": "http",
      "url": "https://aceagent.io/mcp",
      "headers": {
        "X-API-Key": "${ACE_API_KEY}"
      }
    }
  }
}
```

Set in your shell profile:

```bash
export ACE_API_KEY="ace_..."
```

## Troubleshooting

### MCP Server Not Loading

1. Check server status with `/mcp` inside Claude Code
2. Verify the server was added:
   ```bash
   claude mcp list
   ```
3. Verify the URL is correct: `https://aceagent.io/mcp`
4. Try removing and re-adding:
   ```bash
   claude mcp remove ace
   claude mcp add --transport http ace https://aceagent.io/mcp \
     --header "X-API-Key: YOUR_API_KEY"
   ```

### Authentication Errors

- Verify API key is correct in dashboard
- Check key has required scopes
- Try regenerating the key

### Slow Tool Responses

- First MCP call establishes the connection (slower)
- Subsequent calls should be faster
- Check your network connection to the MCP server

### Tools Not Found

- Run `/mcp` to check server status
- Verify API key scopes include tool access
- Try restarting Claude Code

## Next Steps

- [Recording effective outcomes](/docs/developer-guides/recording-outcomes)
- [Managing API keys](/docs/user-guides/managing-api-keys)
