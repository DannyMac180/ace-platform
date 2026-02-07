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

Evolution triggers automatically when:

- 5+ unprocessed outcomes exist
- Outcomes span multiple task types
- Sufficient time has passed since last evolution

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

```diff
## Guidelines

### Security Checks
- Verify authentication
- Check authorization
+ - Validate all user inputs
+ - Sanitize data before database queries
- Look for exposed secrets
```

### Change Summary

Each evolution includes a summary:

> **v2.0 Evolution Summary**
>
> Added input validation guidelines based on 3 outcomes where validation
> issues were missed. Clarified security section to include database
> query sanitization. Removed redundant "check for bugs" instruction
> that was too vague.

### Evolution Insights

View what the Reflector identified:

```json
{
  "patterns": [
    "Input validation missed in 3/7 reviews",
    "Security issues caught consistently"
  ],
  "recommendations": [
    "Add explicit input validation checklist",
    "Keep security focus - working well"
  ]
}
```

## Optimizing Evolution

### Record Rich Outcomes

More detail = better evolution:

```json
{
  "outcome": "failure",
  "task_description": "Reviewed user profile update PR",
  "notes": "Missed XSS vulnerability in display name field. Input wasn't sanitized before rendering in HTML context.",
  "reasoning_trace": "Focused on type safety and auth. Didn't check output encoding."
}
```

### Balance Outcome Types

Include various outcomes:

- ✅ Successes - What works well
- ⚠️ Partials - What needs refinement
- ❌ Failures - What to avoid

### Be Specific About Context

```json
{
  "task_description": "Reviewed 200-line TypeScript PR adding OAuth integration"
}
```

Not:

```json
{
  "task_description": "Reviewed code"
}
```

## Evolution Settings

Configure evolution behavior:

### Threshold

Set minimum outcomes before auto-evolution:

- **5** (default) - Evolves frequently
- **10** - More data before changes
- **20** - Significant data before evolution

### Aggressiveness

Control how much can change:

- **Conservative** - Small, incremental changes
- **Moderate** - Balanced updates
- **Aggressive** - Larger structural changes

## Reverting Evolution

If an evolution introduces issues:

1. Go to playbook **Versions** tab
2. Find the previous version
3. Click **Restore This Version**
4. Optionally record outcome noting the issue

This helps future evolutions avoid similar changes.

## Evolution Limits

Based on your plan:

| Plan | Evolutions/Month |
|------|------------------|
| Starter ($9) | 100 |
| Pro ($29) | 500 |
| Ultra ($79) | 2,000 |
| Enterprise | Unlimited |

## Best Practices

### 1. Record Outcomes Consistently

Don't just record failures. Success outcomes help preserve what works.

### 2. Include Reasoning

When available, include reasoning traces:

```json
{
  "reasoning_trace": "First checked auth flow, then reviewed data validation. Didn't consider rate limiting which was the actual issue."
}
```

### 3. Review Evolution Changes

Check each new version to ensure changes make sense. Revert if needed.

### 4. Start Specific, Then Generalize

Begin with specific playbooks, let evolution generalize based on outcomes.

## Troubleshooting

### Evolution Not Triggering

- Verify 5+ unprocessed outcomes exist
- Check API key has `evolution:write` scope
- Ensure you haven't hit monthly limit

### Poor Evolution Quality

- Record more detailed outcomes
- Include both successes and failures
- Add reasoning traces
- Check that outcomes are specific

### Evolution Taking Too Long

- Complex playbooks take longer
- Many outcomes require more processing
- Check status for actual progress

## Next Steps

- [Record effective outcomes](/docs/developer-guides/recording-outcomes)
- [MCP integration](/docs/developer-guides/mcp-integration/overview)
- [Manage billing](/docs/user-guides/billing-subscriptions)
