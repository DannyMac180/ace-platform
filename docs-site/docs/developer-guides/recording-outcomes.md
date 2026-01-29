---
sidebar_position: 6
---

# Recording Outcomes

Learn how to record effective outcomes that improve your playbooks over time.

## Why Record Outcomes?

Outcomes are the fuel for playbook evolution. They tell ACE:

- What works well (preserve it)
- What doesn't work (fix it)
- What's missing (add it)
- What's confusing (clarify it)

**More outcomes = better evolution = smarter playbooks**

## Recording via MCP

Using Claude Desktop or Claude Code:

```
"Record an outcome for playbook abc-123:
- Task: Reviewed authentication PR with 300 lines of changes
- Outcome: success
- Notes: Caught SQL injection in user lookup, suggested parameterized query"
```

Or explicitly:

```
"Use the ACE record_outcome tool with:
playbook_id: abc-123
task_description: Reviewed authentication PR with 300 lines of changes
outcome: success
notes: Caught SQL injection in user lookup, suggested parameterized query"
```

## Recording via API

### Python

```python
from ace_platform import AceClient

client = AceClient(api_key="your_api_key")

client.record_outcome(
    playbook_id="abc-123",
    task_description="Reviewed authentication PR with 300 lines of changes",
    outcome="success",
    notes="Caught SQL injection in user lookup, suggested parameterized query",
    reasoning_trace="First analyzed auth flow, then checked data validation..."
)
```

### cURL

```bash
curl -X POST https://aceagent.io/api/outcomes \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "playbook_id": "abc-123",
    "task_description": "Reviewed authentication PR with 300 lines of changes",
    "outcome": "success",
    "notes": "Caught SQL injection in user lookup",
    "reasoning_trace": "First analyzed auth flow..."
  }'
```

## Outcome Fields

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `playbook_id` | string | UUID of the playbook used |
| `task_description` | string | What task was performed |
| `outcome` | string | Result: "success", "partial", "failure" |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `notes` | string | Additional context (max 2KB) |
| `reasoning_trace` | string | Agent's reasoning process (max 10KB) |

## Outcome Values

### success

The task completed correctly with good results.

```json
{
  "outcome": "success",
  "notes": "Review was thorough, caught 2 bugs, provided clear explanations"
}
```

### partial

The task completed but with some issues.

```json
{
  "outcome": "partial",
  "notes": "Found formatting issues but missed the race condition that caused a bug later"
}
```

### failure

The task did not complete or results were wrong.

```json
{
  "outcome": "failure",
  "notes": "Completely missed the authentication bypass vulnerability"
}
```

## Writing Effective Outcomes

### Task Description

**Be specific about what was done:**

❌ "Reviewed code"
❌ "Did a review"

✅ "Reviewed user authentication module PR (#234) with 300 lines of TypeScript changes"
✅ "Analyzed customer dataset with 50,000 records for churn prediction"

### Notes

**Include actionable details:**

❌ "It went well"
❌ "Good review"

✅ "Caught SQL injection in user lookup function. Suggested parameterized queries. Missed rate limiting issue that was found later."
✅ "Generated accurate predictions but model explanation was unclear to stakeholders"

### Reasoning Trace

When available, include the agent's thought process:

```json
{
  "reasoning_trace": "1. Reviewed auth flow starting from login endpoint. 2. Checked token generation - uses secure random. 3. Analyzed token storage - found localStorage usage (flagged). 4. Examined session handling - looked correct. 5. Tested logout flow - tokens properly invalidated."
}
```

## Outcome Patterns

### Code Review

```json
{
  "playbook_id": "code-review-security",
  "task_description": "Security review of payment processing PR #567",
  "outcome": "success",
  "notes": "Identified 2 critical issues: 1) Credit card number logged in plaintext, 2) Missing input validation on amount field. Both fixed before merge.",
  "reasoning_trace": "Focused on PCI compliance areas: data handling, logging, input validation..."
}
```

### Documentation

```json
{
  "playbook_id": "api-documentation",
  "task_description": "Generated API docs for /users endpoint",
  "outcome": "partial",
  "notes": "Covered all endpoints and parameters. Missing: rate limit documentation, error response examples for edge cases.",
  "reasoning_trace": "Generated from OpenAPI spec, added examples for common cases..."
}
```

### Data Analysis

```json
{
  "playbook_id": "data-analysis",
  "task_description": "Analyzed Q3 sales data for regional patterns",
  "outcome": "success",
  "notes": "Identified 3 key insights: 1) West region 23% above target, 2) Product C underperforming in urban areas, 3) Seasonal trend starting earlier than previous year."
}
```

### Failure Example

```json
{
  "playbook_id": "code-review-security",
  "task_description": "Security review of authentication refactor PR #789",
  "outcome": "failure",
  "notes": "Completely missed the timing attack vulnerability in password comparison. Issue discovered in production 2 days after merge. Need to add constant-time comparison to security checklist.",
  "reasoning_trace": "Checked for SQL injection, XSS, CSRF. Did not consider timing attacks."
}
```

## Best Practices

### 1. Record All Outcomes

Not just failures - successes help preserve what works.

### 2. Be Honest

Partial and failure outcomes are valuable. They drive improvements.

### 3. Include Context

What type of task? How complex? What was the environment?

### 4. Note What Was Missed

Even for successes, mention anything that could have been done better.

### 5. Add Reasoning Traces

When possible, include how the agent approached the task.

### 6. Be Timely

Record outcomes soon after task completion while details are fresh.

## Outcome Lifecycle

```
1. Use playbook for task
         │
         ▼
2. Evaluate results
         │
         ▼
3. Record outcome
         │
         ▼
4. Outcomes accumulate
         │
         ▼
5. Evolution triggers (5+ outcomes)
         │
         ▼
6. New playbook version created
         │
         ▼
7. Cycle continues with improved playbook
```

## Viewing Outcomes

### Dashboard

1. Navigate to your playbook
2. Click the **Outcomes** tab
3. View all recorded outcomes
4. Filter by outcome type

### API

```bash
curl https://aceagent.io/api/playbooks/abc-123/outcomes \
  -H "Authorization: Bearer YOUR_API_KEY"
```

## Size Limits

| Field | Max Size |
|-------|----------|
| `task_description` | 10 KB |
| `notes` | 2 KB |
| `reasoning_trace` | 10 KB |

Truncate longer content or summarize key points.

## Troubleshooting

### "Playbook not found"

- Verify playbook_id is correct
- Check API key has access to this playbook

### "Invalid outcome value"

- Must be exactly: "success", "partial", or "failure"
- Check for typos or extra whitespace

### "Content too large"

- Truncate notes or reasoning_trace
- Summarize key points instead of full content

## Next Steps

- [Understanding evolution](/docs/user-guides/understanding-evolution)
- [API reference for outcomes](/docs/api-reference/outcomes)
- [MCP integration](/docs/developer-guides/mcp-integration/overview)
