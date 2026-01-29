---
sidebar_position: 2
---

# Claude Desktop Setup

Connect Claude Desktop to ACE to access your playbooks directly in conversations.

## Prerequisites

- [Claude Desktop](https://claude.ai/download) installed
- ACE account with verified email
- API key with `playbooks:read` scope (minimum)

## Configuration

### Step 1: Create an API Key

1. Go to [app.aceagent.io](https://app.aceagent.io)
2. Navigate to **API Keys**
3. Create a key with these scopes:
   - `playbooks:read` - Required
   - `outcomes:write` - Recommended
   - `evolution:read` - Optional

### Step 2: Locate Config File

Find your Claude Desktop configuration file:

**macOS:**
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Windows:**
```
%APPDATA%\Claude\claude_desktop_config.json
```

**Linux:**
```
~/.config/Claude/claude_desktop_config.json
```

### Step 3: Add MCP Server

Edit the config file to add the ACE MCP server:

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

Replace `YOUR_API_KEY` with your actual API key.

### Step 4: Restart Claude Desktop

1. Quit Claude Desktop completely
2. Reopen the application
3. The ACE tools should now be available

## Verifying Connection

### Check Available Tools

In Claude Desktop, ask:

> "What ACE tools are available?"

Claude should list the available tools:
- `list_playbooks`
- `get_playbook`
- `record_outcome`
- etc.

### Test a Tool

Try listing your playbooks:

> "Use the ACE list_playbooks tool to show my playbooks"

## Using ACE in Claude Desktop

### Retrieve a Playbook

> "Get my code review playbook using ACE"

Claude will use `get_playbook` and display the content.

### Follow Playbook Instructions

> "Using my code review playbook, review this code: [paste code]"

Claude will:
1. Fetch the playbook
2. Follow the instructions
3. Provide a review

### Record an Outcome

After a task:

> "Record an outcome for the code review playbook. It was successful and caught a security issue."

Claude will use `record_outcome` with your feedback.

## Multiple Environments

Configure different environments by using multiple MCP servers:

```json
{
  "mcpServers": {
    "ace-prod": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://aceagent.io/mcp/sse"],
      "env": {
        "AUTHORIZATION": "Bearer PROD_API_KEY"
      }
    },
    "ace-staging": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://ace-platform-staging.fly.dev/mcp/sse"],
      "env": {
        "AUTHORIZATION": "Bearer STAGING_API_KEY"
      }
    }
  }
}
```

## Workflow Examples

### Code Review Workflow

```
You: "Get my TypeScript code review playbook"
Claude: [Fetches playbook content]

You: "Review this PR: [paste diff]"
Claude: [Follows playbook, provides review]

You: "That was great, the review caught an injection bug. Record this as a successful outcome."
Claude: [Records outcome with your notes]
```

### Documentation Workflow

```
You: "Get my API documentation playbook"
Claude: [Fetches playbook]

You: "Document this function: [paste code]"
Claude: [Creates documentation following playbook]

You: "Record this as partial success - good structure but missed error cases"
Claude: [Records partial outcome]
```

## Tips for Claude Desktop

### Be Explicit About Tools

Claude may not automatically use MCP tools. Be direct:

✅ "Use the ACE get_playbook tool..."
✅ "Record an outcome using ACE..."

❌ "Get my playbook" (may not trigger tool use)

### Provide Context

When recording outcomes, include details:

✅ "Record a successful outcome. The review caught 3 bugs and provided clear improvement suggestions."

❌ "It went well" (too vague for evolution)

### Use Playbook Sections

Request specific sections for focused tasks:

> "Get just the Security section from my code review playbook"

## Troubleshooting

### Tools Not Appearing

1. **Check config file location** - Ensure it's the correct path
2. **Validate JSON syntax** - Use a JSON validator
3. **Verify npx is available** - Run `npx --version` in terminal
4. **Restart Claude Desktop** - Full quit, not just close

### Authentication Errors

- **"Unauthorized"** - Check API key is correct
- **"Forbidden"** - Verify key has required scopes
- **"Invalid token"** - Ensure `Bearer ` prefix is included

### Connection Issues

```json
{
  "env": {
    "AUTHORIZATION": "Bearer YOUR_KEY",
    "DEBUG": "mcp:*"
  }
}
```

Check Claude Desktop logs for debug output.

### Slow Response

MCP uses SSE which can have latency:
- First request may take 2-3 seconds
- Subsequent requests should be faster
- Consider caching playbook content in conversation

## Security Considerations

### Protect Your Config File

The config file contains your API key:

```bash
# macOS/Linux
chmod 600 ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

### Use Minimum Scopes

For read-only use, only grant:
- `playbooks:read`

For full workflow:
- `playbooks:read`
- `outcomes:write`

### Rotate Keys Regularly

1. Create new key in dashboard
2. Update config file
3. Restart Claude Desktop
4. Revoke old key

## Next Steps

- [Set up Claude Code](/docs/developer-guides/mcp-integration/claude-code)
- [Learn about recording outcomes](/docs/developer-guides/recording-outcomes)
- [Understanding evolution](/docs/user-guides/understanding-evolution)
