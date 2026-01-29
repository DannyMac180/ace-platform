---
sidebar_position: 1
---

# Quick Start

Get up and running with ACE in 5 minutes.

## Prerequisites

- An ACE account ([create one here](https://app.aceagent.io))
- Verified email address
- An API key with appropriate scopes

## Step 1: Create an API Key

1. Log in to your [ACE Dashboard](https://app.aceagent.io)
2. Navigate to **API Keys** in the sidebar
3. Click **Create API Key**
4. Select the scopes you need:
   - `playbooks:read` - Read playbook content
   - `playbooks:write` - Create and edit playbooks
   - `outcomes:write` - Record outcomes
   - `evolution:read` - Check evolution status
   - `evolution:write` - Trigger evolution manually
5. Copy your API key (you won't see it again!)

## Step 2: Create Your First Playbook

From the dashboard:

1. Click **New Playbook** in the sidebar
2. Give it a name (e.g., "Code Review Assistant")
3. Write your initial instructions in Markdown:

```markdown
# Code Review Assistant

## Role
You are an expert code reviewer focused on code quality and best practices.

## Guidelines
- Check for potential bugs and edge cases
- Suggest performance improvements
- Ensure consistent code style
- Look for security vulnerabilities

## Output Format
Provide feedback in sections:
1. **Critical Issues** - Must fix before merge
2. **Suggestions** - Recommended improvements
3. **Praise** - What was done well
```

4. Click **Save**

## Step 3: Connect via MCP

The fastest way to use your playbook is through MCP (Model Context Protocol).

### Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

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

### Claude Code

Add to your Claude Code settings (`.claude/settings.json`):

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

## Step 4: Use Your Playbook

Once connected, you can access your playbooks directly in Claude:

```
Use the ace get_playbook tool with playbook_id "your-playbook-id"
```

Claude will fetch the playbook content and follow the instructions.

## Step 5: Record Outcomes

After using your playbook, record the outcome to help it improve:

```
Use the ace record_outcome tool with:
- playbook_id: "your-playbook-id"
- task_description: "Reviewed PR #123 for authentication changes"
- outcome: "success"
- notes: "Caught a security issue with token storage"
```

## Step 6: Watch It Evolve

After recording enough outcomes, ACE automatically evolves your playbook. Check the **Evolution** tab in your dashboard to see:

- Evolution status
- New version diffs
- Improvement summaries

## What's Next?

- Learn about [Core Concepts](/docs/getting-started/core-concepts)
- Explore [MCP Integration](/docs/developer-guides/mcp-integration/overview) options
- Read about [Recording Outcomes](/docs/developer-guides/recording-outcomes) effectively

## Troubleshooting

### API Key Not Working

- Ensure your email is verified
- Check that the key has the required scopes
- Verify the key hasn't been revoked

### Playbook Not Found

- Confirm the playbook ID is correct
- Check your API key has `playbooks:read` scope
- Ensure you're the owner of the playbook

### Evolution Not Triggering

- You need at least 5 outcomes before automatic evolution
- Check that outcomes have enough detail
- Verify your API key has `outcomes:write` scope
