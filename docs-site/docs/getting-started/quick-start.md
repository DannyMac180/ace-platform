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

Add the ACE MCP server to your client's config with the endpoint `https://aceagent.io/mcp` and your API key:
Legacy SSE compatibility is still available at `https://aceagent.io/mcp/sse` through **May 22, 2026**.

- [Claude Desktop setup](/docs/developer-guides/mcp-integration/claude-desktop)
- [Claude Code setup](/docs/developer-guides/mcp-integration/claude-code)

See the [MCP Integration Overview](/docs/developer-guides/mcp-integration/overview) for full configuration details.

## Step 4: Configure Your Agent

Copy and paste these instructions into your agent's configuration file (`CLAUDE.md`, `AGENTS.md`, or Custom Instructions).

If these instructions are followed correctly, your agent should perform the next workflow steps automatically as you use it (playbook discovery, loading instructions, applying guidance, and recording outcomes).

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

For more configuration patterns, see the [MCP Integration Overview](/docs/developer-guides/mcp-integration/overview#configuring-agent-instructions).

## Step 5: Use Your Playbook

With Step 4 configured, your agent should do this automatically during normal usage.
If you want to test tool calls directly, you can still prompt it like this:

```
Use the ace get_playbook tool with playbook_id "your-playbook-id"
```

Your agent will fetch the playbook content and follow the instructions.

## Step 6: Record Outcomes

With Step 4 configured, your agent should record outcomes automatically after playbook-guided tasks.
If you want to record one manually, use:

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
