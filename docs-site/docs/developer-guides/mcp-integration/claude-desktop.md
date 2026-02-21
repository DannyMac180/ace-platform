---
sidebar_position: 2
---

# Claude Desktop Setup

Connect Claude Desktop to ACE to access your playbooks directly in conversations.

## Prerequisites

- [Claude Desktop](https://claude.ai/download) installed (macOS or Windows)
- ACE account with verified email
- API key with `playbooks:read` scope (minimum)

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

### Step 2: Open Config File

1. Open Claude Desktop
2. Click the **Settings** icon
3. Select the **Developer** tab
4. Click **Edit Config**

This opens `claude_desktop_config.json` in your default editor.

### Step 3: Add MCP Server

Add the ACE MCP server to the config file:

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

Replace `YOUR_API_KEY` with your actual API key.
Legacy SSE compatibility remains available through **May 22, 2026** at `https://aceagent.io/mcp/sse`.

### Step 4: Restart Claude Desktop

1. Quit Claude Desktop completely
2. Reopen the application
3. The ACE tools should now be available

## Verifying Connection

### Check Available Tools

In Claude Desktop, ask:

> "What ACE tools are available?"

Claude should list the available tools:
- `list_playbooks` / `find_playbook`
- `get_playbook`
- `create_playbook` / `create_version`
- `record_outcome`
- `trigger_evolution` / `get_evolution_status`

### Test a Tool

Try listing your playbooks:

> "List my ACE playbooks"

## Using ACE in Claude Desktop

### Retrieve a Playbook

> "Get my code review playbook using ACE"

Claude will use `get_playbook` and display the content.

### Follow Playbook Instructions

> "Using my code review playbook, review this code: [paste code]"

Claude will fetch the playbook, follow the instructions, and provide a review.

### Record an Outcome

After a task:

> "Record an outcome for the code review playbook. It was successful and caught a security issue."

Claude will use `record_outcome` with your feedback.

## Workflow Examples

### Code Review Workflow

```
You: "Get my TypeScript code review playbook"
Claude: [Fetches playbook content]

You: "Review this PR: [paste diff]"
Claude: [Follows playbook, provides review]

You: "Record this as a successful outcome - the review caught an injection bug."
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

## Tips

### Provide Detailed Outcomes

When recording outcomes, include specifics so evolution has good data to work with:

- "Record a successful outcome. The review caught 3 bugs and provided clear improvement suggestions."
- "Record this as partial - the structure was good but it missed edge cases in the error handling."

Vague feedback like "it went well" won't help evolution improve the playbook.

### Use Playbook Sections

Request specific sections for focused tasks:

> "Get just the Security section from my code review playbook"

## Troubleshooting

### Tools Not Appearing

1. **Check config file** - Open via Settings > Developer > Edit Config
2. **Validate JSON syntax** - Use a JSON validator
3. **Verify URL is correct** - `https://aceagent.io/mcp`
4. **Restart Claude Desktop** - Full quit, not just close window

### Authentication Errors

- **"Unauthorized"** - Check API key is correct
- **"Forbidden"** - Verify key has required scopes
- **"Invalid token"** - Verify API key format is correct

### Slow Response

- First MCP request may take 2-3 seconds to establish the connection
- Subsequent requests should be faster

## Security Considerations

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
4. Delete old key

## Next Steps

- [Set up Claude Code](/docs/developer-guides/mcp-integration/claude-code)
- [Learn about recording outcomes](/docs/developer-guides/recording-outcomes)
- [Understanding evolution](/docs/user-guides/understanding-evolution)
