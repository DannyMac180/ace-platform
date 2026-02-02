---
sidebar_position: 3
---

# Claude Code Setup

Integrate ACE with Claude Code (Anthropic's CLI) for AI-assisted development with self-improving playbooks.

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed
- ACE account with verified email
- API key with appropriate scopes

## Configuration

### Step 1: Create an API Key

1. Go to [app.aceagent.io](https://app.aceagent.io)
2. Navigate to **API Keys**
3. Create a key with scopes:
   - `playbooks:read` - Required
   - `playbooks:write` - For creating/editing playbooks
   - `outcomes:write` - For recording outcomes
   - `evolution:write` - For triggering evolution

### Step 2: Configure MCP Server

Add ACE to your Claude Code MCP settings.

**Global settings** (`~/.claude/settings.json`):

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

**Project settings** (`.claude/settings.json` in project root):

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

### Step 3: Verify Setup

Start Claude Code and check MCP servers:

```bash
claude
```

Then ask:

> "List my ACE playbooks"

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

**Refactoring:**
```
You: "Get my refactoring playbook and suggest improvements for utils.ts"
Claude: [Analyzes code using playbook guidelines]
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

Store playbook IDs in your project's CLAUDE.md for quick reference:

```markdown
# Project Playbooks

## Code Review
Playbook ID: `abc-123-def`
Use for: All PR reviews

## Documentation
Playbook ID: `ghi-456-jkl`
Use for: API and README updates
```

Then reference them in conversations:

> "Using playbook abc-123-def, review the changes in src/"

## Automation with Hooks

Claude Code supports hooks that can automate ACE workflows.

### Post-Task Outcome Recording

Create a hook that prompts for outcome recording:

```json
{
  "hooks": {
    "post_task": {
      "prompt": "If you used an ACE playbook for this task, offer to record an outcome."
    }
  }
}
```

### Pre-Review Playbook Fetch

```json
{
  "hooks": {
    "code_review": {
      "prompt": "First fetch the appropriate code review playbook from ACE before reviewing."
    }
  }
}
```

## Using Environment Variables

Keep API keys out of config files by using environment variable substitution:

```json
{
  "mcpServers": {
    "ace": {
      "type": "sse",
      "url": "https://aceagent.io/mcp/sse",
      "headers": {
        "X-API-Key": "${ACE_API_KEY}"
      }
    }
  }
}
```

Set in your shell profile:

```bash
export ACE_API_KEY="ace_live_..."
```

## Best Practices

### 1. Use Playbooks for Repetitive Tasks

Good candidates:
- Code reviews
- Documentation generation
- Test writing
- API design
- Security audits

### 2. Record Outcomes Consistently

After every playbook-guided task:

```
You: "Record outcome: success, task was reviewing auth module,
caught timing attack vulnerability"
```

### 3. Review Evolution Changes

When evolution completes:

```
You: "Get playbook abc-123 and compare to version 2"
```

### 4. Create Task-Specific Playbooks

Instead of one generic playbook, create focused ones:
- `code-review-security`
- `code-review-performance`
- `code-review-typescript`

## Troubleshooting

### MCP Server Not Loading

1. Check settings file syntax:
   ```bash
   cat ~/.claude/settings.json | jq .
   ```

2. Verify the URL is correct: `https://aceagent.io/mcp/sse`

3. Check your API key is set in the `headers` section

### Authentication Errors

- Verify API key is correct in dashboard
- Check key has required scopes
- Try regenerating the key

### Slow Tool Responses

- First MCP call establishes connection (slower)
- Subsequent calls should be faster
- Consider local MCP server for development

### Tools Not Found

- Restart Claude Code
- Check MCP server is properly configured
- Verify API key scopes include tool access

## Integration with Git Workflows

### Pre-Commit Review

```bash
# In your pre-commit hook
claude "Using my code-review playbook, review the staged changes"
```

### PR Description Generation

```bash
claude "Using my documentation playbook, generate a PR description for these changes"
```

## Next Steps

- [Build custom MCP agents](/docs/developer-guides/mcp-integration/custom-agents)
- [Recording effective outcomes](/docs/developer-guides/recording-outcomes)
- [Managing API keys](/docs/user-guides/managing-api-keys)
