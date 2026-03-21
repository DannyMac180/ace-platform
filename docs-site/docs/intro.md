---
sidebar_position: 1
slug: /
---

# Introduction to ACE

ACE is a platform for self-improving AI instructions. You can use it as a
hosted cloud product or through a local-first OSS path, depending on whether
you want managed convenience or self-managed control.

## What is ACE?

ACE stands for **Agentic Context Engineer**. It's a three-agent architecture that continuously improves playbooks based on real-world outcomes:

1. **Generator** - Produces outputs based on playbook instructions
2. **Reflector** - Analyzes outcomes to identify improvement opportunities
3. **Curator** - Synthesizes feedback into improved playbook versions

## What are Playbooks?

Playbooks are structured instructions that guide AI agents on how to perform specific tasks. Unlike static prompts, ACE playbooks:

- **Evolve automatically** based on recorded outcomes
- **Version controlled** so you can track changes over time
- **Accessible via MCP** for seamless integration with AI agents that support MCP

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

```
Use the ace record_outcome tool with:
- playbook_id: "abc123"
- task_description: "Summarized quarterly earnings report"
- outcome: "success"
- notes: "Summary was accurate and well-structured"
```

After enough outcomes are recorded, ACE automatically evolves the playbook to incorporate lessons learned.

## Getting Started

Ready to try ACE? Choose the path that matches how you want to run it:

1. **[ACE Cloud Quick Start](/docs/getting-started/quick-start)** - Start with the hosted dashboard, API keys, and managed MCP flow
2. **[OSS Overview](/docs/getting-started/oss-overview)** - Understand what is public OSS, what stays hosted, and which local path fits
3. **[Local Quickstart](/docs/getting-started/local-quickstart)** - Run the extracted OSS package or the self-managed local runtime
4. **[Core Concepts](/docs/getting-started/core-concepts)** - Understand playbooks, outcomes, and evolution

## Choose Your Path

| Path | Best for | Start here |
| --- | --- | --- |
| Hosted ACE | Fastest setup, hosted auth, sync, and dashboard workflows | [ACE Cloud Quick Start](/docs/getting-started/quick-start) |
| ACE OSS package | Embedding the ACE engine inside your own Python workflow | [OSS Overview](/docs/getting-started/oss-overview) |
| Self-managed local runtime | Running ACE's API, CLI, and MCP server on your own infrastructure | [Local Quickstart](/docs/getting-started/local-quickstart) |

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
- Explore the [OSS and local setup path](/docs/getting-started/oss-overview)
- Learn about [MCP Integration](/docs/developer-guides/mcp-integration/overview)
- Learn how to [record outcomes](/docs/developer-guides/recording-outcomes)
