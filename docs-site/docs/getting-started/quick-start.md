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

### Option 1: Via Your AI Agent (Recommended)

Once connected via MCP, ask your AI agent to create a playbook:

```
Create an ACE playbook called "Code Review Assistant" with guidelines
for reviewing code quality, security, and best practices.
```

Your agent will use the `create_playbook` tool to generate well-structured instructions automatically.

### Option 2: Via the Dashboard

1. Log in to your [ACE Dashboard](https://app.aceagent.io)
2. Click **New Playbook** in the sidebar
3. Give it a name (e.g., "Code Review Assistant")
4. Optionally add initial content, or leave it blank to start—the playbook will evolve as you record outcomes
5. Click **Save**

## Step 3: Connect via MCP

The fastest way to use your playbook is through MCP (Model Context Protocol).

### Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

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

### Claude Code

Add to your Claude Code settings (`.claude/settings.json`):

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

### Any MCP Client

Any MCP client that supports SSE transport can connect using the same configuration format above.

## Step 4: Configure Your Agent

Add these instructions to your agent's configuration file (`CLAUDE.md`, `AGENTS.md`, or Custom Instructions) to enable automatic playbook usage:

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

This ensures your agent automatically leverages playbooks and contributes to their improvement.

## Step 5: Use Your Playbook

Once connected, you can access your playbooks directly in your agent:

```
Use the ace get_playbook tool with playbook_id "your-playbook-id"
```

Your agent will fetch the playbook content and follow the instructions.

## Step 6: Record Outcomes

After using your playbook, record the outcome to help it improve:

```
Use the ace record_outcome tool with:
- playbook_id: "your-playbook-id"
- task_description: "Reviewed PR #123 for authentication changes"
- outcome: "success"
- notes: "Caught a security issue with token storage"
```

## Step 7: Watch It Evolve

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
