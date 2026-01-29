---
sidebar_position: 1
slug: /
---

# Introduction to ACE

ACE is a **Playbooks as a Service** solution that provides self-improving AI instructions for your agents. Built on the Agentic Context Engineer (ACE) architecture, the platform helps your AI agents get better at their tasks over time.

## What is ACE?

ACE stands for **Agentic Context Engineer**. It's a three-agent architecture that continuously improves playbooks based on real-world outcomes:

1. **Generator** - Produces outputs based on playbook instructions
2. **Reflector** - Analyzes outcomes to identify improvement opportunities
3. **Curator** - Synthesizes feedback into improved playbook versions

## What are Playbooks?

Playbooks are structured instructions that guide AI agents on how to perform specific tasks. Unlike static prompts, ACE playbooks:

- **Evolve automatically** based on recorded outcomes
- **Version controlled** so you can track changes over time
- **Accessible via MCP** for seamless integration with Claude and other agents

## Key Features

### Self-Improving Instructions

Record outcomes from your AI tasks, and ACE automatically improves the underlying playbooks. The more you use them, the better they get.

### MCP Integration

Access your playbooks directly from Claude Desktop, Claude Code, or any MCP-compatible agent. No API integration required.

### Version History

Every evolution creates a new version. Compare changes, understand improvements, and roll back if needed.

### Usage Analytics

Track how your playbooks are being used and monitor evolution progress through the dashboard.

## Quick Example

```python
# Record an outcome after using a playbook
from ace_platform import AceClient

client = AceClient(api_key="your-api-key")

# Record a successful outcome
client.record_outcome(
    playbook_id="abc123",
    task_description="Summarized quarterly earnings report",
    outcome="success",
    notes="Summary was accurate and well-structured"
)
```

After enough outcomes are recorded, ACE automatically evolves the playbook to incorporate lessons learned.

## Getting Started

Ready to try ACE? Here's the fastest path:

1. **[Create an account](/docs/getting-started/creating-account)** - Sign up and verify your email
2. **[Quick Start](/docs/getting-started/quick-start)** - Set up your first playbook in 5 minutes
3. **[Core Concepts](/docs/getting-started/core-concepts)** - Understand playbooks, outcomes, and evolution

## Use Cases

ACE is ideal for:

- **Code Review Agents** - Improve review quality based on feedback
- **Documentation Writers** - Learn from corrections and preferences
- **Data Analysis** - Refine analysis approaches from outcomes
- **Customer Support** - Enhance response quality over time
- **Content Generation** - Adapt to style and quality feedback

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                           ACE                                │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │Generator │───▶│Reflector │───▶│ Curator  │              │
│  └──────────┘    └──────────┘    └──────────┘              │
│       │                               │                     │
│       ▼                               ▼                     │
│  ┌──────────┐                   ┌──────────┐               │
│  │ Playbook │◀──────────────────│ Evolved  │               │
│  │  v1.0    │                   │  v2.0    │               │
│  └──────────┘                   └──────────┘               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Next Steps

- Explore the [Getting Started](/docs/getting-started/quick-start) guide
- Learn about [MCP Integration](/docs/developer-guides/mcp-integration/overview)
- Browse the [API Reference](/docs/api-reference/overview)
