---
sidebar_position: 2
---

# Understanding Evolution

Learn how ACE automatically improves your playbooks through evolution.

## What is Evolution?

Evolution is the core feature of ACE. It analyzes the outcomes of your playbook usage and automatically generates improved versions.

```
                    ┌─────────────┐
                    │  Outcomes   │
                    │  (5+ needed)│
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Reflector  │
                    │   Agent     │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   Curator   │
                    │   Agent     │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │ New Version │
                    │   (v2.0)    │
                    └─────────────┘
```

## How Evolution Works

### Step 1: Outcome Collection

As you use playbooks, record outcomes:

```json
{
  "outcome": "partial",
  "task_description": "Reviewed API endpoint PR",
  "notes": "Missed input validation issue that caused staging bug"
}
```

### Step 2: Reflection

The Reflector agent analyzes accumulated outcomes to identify:

- **Patterns** - Recurring successes or failures
- **Gaps** - Missing instructions that caused issues
- **Redundancies** - Instructions that don't add value
- **Ambiguities** - Unclear guidance causing inconsistent results

### Step 3: Curation

The Curator agent synthesizes insights into concrete improvements:

- Adds new guidelines based on failure patterns
- Clarifies ambiguous instructions
- Removes or refines ineffective sections
- Strengthens successful approaches

### Step 4: Version Creation

A new playbook version is created with:

- Updated content
- Change summary
- Diff from previous version
- Evolution metadata

## Triggering Evolution

### Automatic Triggers

Evolution triggers automatically when 5+ unprocessed outcomes exist for a playbook.

### Manual Triggers

Trigger evolution on-demand:

**Dashboard:**
1. Open your playbook
2. Go to the **Evolution** tab
3. Click **Trigger Evolution**

**MCP:**
```
Use the ace trigger_evolution tool with playbook_id "your-id"
```

## Evolution Status

Track evolution progress:

| Status | Description |
|--------|-------------|
| `queued` | Waiting to start |
| `running` | Currently processing outcomes |
| `completed` | New version created successfully |
| `failed` | Error occurred (check logs) |

### Checking Status

**Dashboard:** View real-time status on the Evolution tab

**MCP:**
```
Use the ace get_evolution_status tool with job_id "your-job-id"
```

## Viewing Evolution Results

### Version Diff

Compare what changed between versions:

> **Guidelines — Security Checks**
>
> - Verify authentication
> - Check authorization
> - **Validate all user inputs** *(added)*
> - **Sanitize data before database queries** *(added)*
> - Look for exposed secrets

### Change Summary

Each evolution creates a new version with a diff summary visible on the **Versions** tab. The summary lists what was added, removed, or modified:

> + Added: Validate all user inputs before processing...
>
> + Added: Sanitize data before database queries...
>
> - Removed: Check for bugs (too vague)...

## Tips for Better Evolution

Evolution quality depends on the outcomes you record. A few guidelines:

- **Be specific** — "Reviewed 200-line TypeScript PR adding OAuth integration" is far more useful than "Reviewed code"
- **Record all outcome types** — successes, partials, and failures all contribute. Don't just record failures.
- **Include reasoning traces** — these help the Reflector understand *why* something worked or didn't
- **Review new versions** — check each evolved version to ensure changes make sense

For detailed guidance on recording effective outcomes, see [Recording Outcomes](/docs/developer-guides/recording-outcomes).

## Evolution Limits

Hosted evals count against the hosted usage envelope for your current workspace.
If you are on a trial, feature access can stay on while the trial envelope still
uses the smaller effective `free` limits.

See [Hosted Plans, Billing, and Limits](/docs/user-guides/billing-subscriptions)
for the current hosted eval allowances, managed inference envelopes, storage
limits, and upgrade paths.

## Troubleshooting

### Evolution Not Triggering

- Verify 5+ unprocessed outcomes exist
- Check API key has `evolution:write` scope
- Ensure you haven't hit a hosted eval block or billing-state block

### Evolution Taking Too Long

- Complex playbooks take longer
- Many outcomes require more processing
- Check status for actual progress

## Next Steps

- [Record effective outcomes](/docs/developer-guides/recording-outcomes)
- [MCP integration](/docs/developer-guides/mcp-integration/overview)
- [Review hosted plans and limits](/docs/user-guides/billing-subscriptions)
