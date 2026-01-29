---
sidebar_position: 4
---

# Outcomes API

Record and retrieve task outcomes for playbook evolution.

## Record Outcome

Record the outcome of a task performed using a playbook.

```
POST /api/outcomes
```

**Required scope:** `outcomes:write`

### Request Body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `playbook_id` | string | Yes | Playbook UUID |
| `task_description` | string | Yes | What task was performed (max 10KB) |
| `outcome` | string | Yes | Result: "success", "partial", or "failure" |
| `notes` | string | No | Additional context (max 2KB) |
| `reasoning_trace` | string | No | Agent's reasoning process (max 10KB) |

### Example Request

```bash
curl -X POST https://aceagent.io/api/outcomes \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "playbook_id": "550e8400-e29b-41d4-a716-446655440000",
    "task_description": "Reviewed authentication module PR with 300 lines of changes",
    "outcome": "success",
    "notes": "Caught SQL injection vulnerability in user lookup function",
    "reasoning_trace": "1. Analyzed auth flow starting from login endpoint..."
  }'
```

### Response

```json
{
  "id": "outcome_abc123",
  "playbook_id": "550e8400-e29b-41d4-a716-446655440000",
  "task_description": "Reviewed authentication module PR with 300 lines of changes",
  "outcome": "success",
  "notes": "Caught SQL injection vulnerability in user lookup function",
  "created_at": "2024-01-20T14:30:00Z"
}
```

### Outcome Values

| Value | Description |
|-------|-------------|
| `success` | Task completed correctly |
| `partial` | Task completed with issues |
| `failure` | Task failed or results were incorrect |

## List Outcomes

Get outcomes for a playbook.

```
GET /api/playbooks/{playbook_id}/outcomes
```

**Required scope:** `outcomes:read`

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 20 | Items per page (max 100) |
| `offset` | integer | 0 | Skip N items |
| `outcome` | string | - | Filter by outcome value |
| `after` | string | - | Filter outcomes after date (ISO 8601) |
| `before` | string | - | Filter outcomes before date (ISO 8601) |

### Example Request

```bash
curl "https://aceagent.io/api/playbooks/550e8400-e29b-41d4-a716-446655440000/outcomes?outcome=failure&limit=10" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### Response

```json
{
  "items": [
    {
      "id": "outcome_abc123",
      "playbook_id": "550e8400-e29b-41d4-a716-446655440000",
      "task_description": "Reviewed authentication module PR",
      "outcome": "failure",
      "notes": "Missed timing attack vulnerability",
      "created_at": "2024-01-20T14:30:00Z",
      "processed": false
    },
    {
      "id": "outcome_def456",
      "playbook_id": "550e8400-e29b-41d4-a716-446655440000",
      "task_description": "Reviewed payment processing PR",
      "outcome": "failure",
      "notes": "Did not check for race conditions",
      "created_at": "2024-01-19T10:15:00Z",
      "processed": true
    }
  ],
  "total": 2,
  "limit": 10,
  "offset": 0
}
```

## Get Outcome

Get a specific outcome by ID.

```
GET /api/outcomes/{outcome_id}
```

**Required scope:** `outcomes:read`

### Response

```json
{
  "id": "outcome_abc123",
  "playbook_id": "550e8400-e29b-41d4-a716-446655440000",
  "task_description": "Reviewed authentication module PR with 300 lines of changes",
  "outcome": "success",
  "notes": "Caught SQL injection vulnerability in user lookup function",
  "reasoning_trace": "1. Analyzed auth flow starting from login endpoint...",
  "created_at": "2024-01-20T14:30:00Z",
  "processed": false,
  "processed_at": null
}
```

### Outcome Fields

| Field | Description |
|-------|-------------|
| `id` | Unique outcome identifier |
| `playbook_id` | Associated playbook |
| `task_description` | What was performed |
| `outcome` | Result value |
| `notes` | Additional context |
| `reasoning_trace` | Agent's reasoning (if provided) |
| `created_at` | When recorded |
| `processed` | Whether used in evolution |
| `processed_at` | When used in evolution |

## Delete Outcome

Delete a specific outcome.

```
DELETE /api/outcomes/{outcome_id}
```

**Required scope:** `outcomes:write`

### Response

```json
{
  "message": "Outcome deleted successfully"
}
```

:::note
Deleting outcomes may affect evolution quality. Only delete if recorded in error.
:::

## Outcome Statistics

Get aggregated outcome statistics for a playbook.

```
GET /api/playbooks/{playbook_id}/outcomes/stats
```

**Required scope:** `outcomes:read`

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `period` | string | Time period: "week", "month", "year", "all" |

### Response

```json
{
  "playbook_id": "550e8400-e29b-41d4-a716-446655440000",
  "period": "month",
  "total": 45,
  "by_outcome": {
    "success": 32,
    "partial": 8,
    "failure": 5
  },
  "unprocessed": 12,
  "success_rate": 0.711
}
```

## Bulk Record Outcomes

Record multiple outcomes at once.

```
POST /api/outcomes/bulk
```

**Required scope:** `outcomes:write`

### Request Body

```json
{
  "outcomes": [
    {
      "playbook_id": "550e8400-e29b-41d4-a716-446655440000",
      "task_description": "Task 1",
      "outcome": "success"
    },
    {
      "playbook_id": "550e8400-e29b-41d4-a716-446655440000",
      "task_description": "Task 2",
      "outcome": "partial",
      "notes": "Minor issues"
    }
  ]
}
```

### Response

```json
{
  "created": 2,
  "outcomes": [
    {"id": "outcome_abc123", "status": "created"},
    {"id": "outcome_def456", "status": "created"}
  ]
}
```

### Limits

- Maximum 50 outcomes per bulk request

## Error Responses

### 404 Not Found

```json
{
  "error": "not_found",
  "message": "Playbook not found"
}
```

### 422 Validation Error

```json
{
  "error": "validation_error",
  "message": "Validation failed",
  "details": {
    "outcome": "Must be one of: success, partial, failure",
    "task_description": "Required field"
  }
}
```

### 413 Payload Too Large

```json
{
  "error": "payload_too_large",
  "message": "Content exceeds maximum size",
  "details": {
    "field": "reasoning_trace",
    "max_size": "10KB",
    "actual_size": "15KB"
  }
}
```

## Best Practices

### 1. Be Descriptive

```json
{
  "task_description": "Reviewed user authentication PR #234 adding OAuth2 support with 500 lines of TypeScript",
  "notes": "Caught race condition in token refresh. Suggested mutex pattern."
}
```

### 2. Include Failures

Failure outcomes are valuable for evolution:

```json
{
  "outcome": "failure",
  "notes": "Missed XSS vulnerability in user profile display. Need to add output encoding checks to playbook."
}
```

### 3. Add Reasoning Traces

```json
{
  "reasoning_trace": "1. Reviewed auth flow: login → token generation → storage\n2. Checked token security: ✓ random, ✓ expiry\n3. Missed: session fixation check"
}
```

## Size Limits

| Field | Max Size |
|-------|----------|
| `task_description` | 10 KB |
| `notes` | 2 KB |
| `reasoning_trace` | 10 KB |

## Retention

Outcome retention depends on your plan:

| Plan | Retention |
|------|-----------|
| Free | 30 days |
| Pro | 1 year |
| Team | Unlimited |

## Next Steps

- [Evolution API](/docs/api-reference/evolution)
- [Recording Outcomes Guide](/docs/developer-guides/recording-outcomes)
- [Understanding Evolution](/docs/user-guides/understanding-evolution)
