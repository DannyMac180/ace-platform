---
sidebar_position: 5
---

# Evolution API

Trigger and monitor playbook evolution.

## Overview

Evolution is the process by which ACE improves playbooks based on recorded outcomes. The API lets you:

- Trigger evolution manually
- Check evolution status
- View evolution history

## Trigger Evolution

Start an evolution job for a playbook.

```
POST /api/playbooks/{playbook_id}/evolve
```

**Required scope:** `evolution:write`

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `playbook_id` | string | Playbook UUID |

### Example Request

```bash
curl -X POST https://aceagent.io/api/playbooks/550e8400-e29b-41d4-a716-446655440000/evolve \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### Response

```json
{
  "job_id": "evo_job_abc123",
  "playbook_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "created_at": "2024-01-20T15:00:00Z"
}
```

### Error: No Outcomes

```json
{
  "error": "insufficient_data",
  "message": "Not enough unprocessed outcomes to trigger evolution",
  "details": {
    "required": 5,
    "available": 2
  }
}
```

## Get Evolution Status

Check the status of an evolution job.

```
GET /api/evolution/{job_id}/status
```

**Required scope:** `evolution:read`

### Path Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `job_id` | string | Evolution job ID |

### Response: Pending

```json
{
  "job_id": "evo_job_abc123",
  "playbook_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "created_at": "2024-01-20T15:00:00Z",
  "started_at": null,
  "completed_at": null
}
```

### Response: In Progress

```json
{
  "job_id": "evo_job_abc123",
  "playbook_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "in_progress",
  "progress": {
    "phase": "reflecting",
    "outcomes_processed": 3,
    "outcomes_total": 7
  },
  "created_at": "2024-01-20T15:00:00Z",
  "started_at": "2024-01-20T15:00:05Z",
  "completed_at": null
}
```

### Response: Completed

```json
{
  "job_id": "evo_job_abc123",
  "playbook_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "new_version": 4,
  "change_summary": "Added input validation checklist based on 3 outcomes. Clarified security section. Removed redundant instructions.",
  "outcomes_processed": 7,
  "created_at": "2024-01-20T15:00:00Z",
  "started_at": "2024-01-20T15:00:05Z",
  "completed_at": "2024-01-20T15:02:30Z"
}
```

### Response: Failed

```json
{
  "job_id": "evo_job_abc123",
  "playbook_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "error": {
    "code": "evolution_error",
    "message": "Failed to generate improved playbook",
    "details": "Model returned invalid format"
  },
  "created_at": "2024-01-20T15:00:00Z",
  "started_at": "2024-01-20T15:00:05Z",
  "failed_at": "2024-01-20T15:01:15Z"
}
```

### Status Values

| Status | Description |
|--------|-------------|
| `pending` | Job queued, waiting to start |
| `in_progress` | Currently processing |
| `completed` | Successfully created new version |
| `failed` | Error occurred |

### Progress Phases

| Phase | Description |
|-------|-------------|
| `collecting` | Gathering unprocessed outcomes |
| `reflecting` | Reflector analyzing outcomes |
| `curating` | Curator generating improvements |
| `validating` | Validating new version |
| `publishing` | Creating new version |

## List Evolution Jobs

Get evolution history for a playbook.

```
GET /api/playbooks/{playbook_id}/evolutions
```

**Required scope:** `evolution:read`

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 20 | Items per page |
| `offset` | integer | 0 | Skip N items |
| `status` | string | - | Filter by status |

### Response

```json
{
  "items": [
    {
      "job_id": "evo_job_abc123",
      "status": "completed",
      "new_version": 4,
      "outcomes_processed": 7,
      "created_at": "2024-01-20T15:00:00Z",
      "completed_at": "2024-01-20T15:02:30Z"
    },
    {
      "job_id": "evo_job_xyz789",
      "status": "completed",
      "new_version": 3,
      "outcomes_processed": 5,
      "created_at": "2024-01-15T10:00:00Z",
      "completed_at": "2024-01-15T10:01:45Z"
    }
  ],
  "total": 2,
  "limit": 20,
  "offset": 0
}
```

## Get Evolution Details

Get detailed information about a completed evolution.

```
GET /api/evolution/{job_id}
```

**Required scope:** `evolution:read`

### Response

```json
{
  "job_id": "evo_job_abc123",
  "playbook_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "previous_version": 3,
  "new_version": 4,
  "change_summary": "Added input validation checklist based on 3 outcomes where validation issues were missed.",
  "insights": {
    "patterns_identified": [
      "Input validation missed in 3/7 reviews",
      "Security issues caught consistently"
    ],
    "improvements_made": [
      "Added explicit input validation checklist",
      "Clarified database query sanitization guidance"
    ],
    "preserved": [
      "Security review structure",
      "Output format guidelines"
    ]
  },
  "outcomes_processed": 7,
  "outcomes_by_type": {
    "success": 4,
    "partial": 2,
    "failure": 1
  },
  "created_at": "2024-01-20T15:00:00Z",
  "completed_at": "2024-01-20T15:02:30Z"
}
```

## Cancel Evolution

Cancel a pending or in-progress evolution job.

```
POST /api/evolution/{job_id}/cancel
```

**Required scope:** `evolution:write`

### Response

```json
{
  "job_id": "evo_job_abc123",
  "status": "cancelled",
  "message": "Evolution job cancelled"
}
```

:::note
Completed or failed jobs cannot be cancelled.
:::

## Automatic Evolution

Evolution triggers automatically when:

1. 5+ unprocessed outcomes exist
2. Outcomes span at least 24 hours
3. No evolution in the last 24 hours

### Disable Auto-Evolution

Update playbook settings:

```bash
curl -X PUT https://aceagent.io/api/playbooks/550e8400-e29b-41d4-a716-446655440000/settings \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "auto_evolution": false
  }'
```

## Evolution Limits

| Plan | Evolutions/Month |
|------|------------------|
| Free | 10 |
| Pro | 100 |
| Team | Unlimited |

### Check Remaining

```bash
curl https://aceagent.io/api/usage \
  -H "Authorization: Bearer YOUR_API_KEY"
```

Response includes:

```json
{
  "evolutions": {
    "used": 45,
    "limit": 100,
    "period_end": "2024-01-31T23:59:59Z"
  }
}
```

## Webhooks (Coming Soon)

Subscribe to evolution events:

- `evolution.started`
- `evolution.completed`
- `evolution.failed`

## Error Responses

### 404 Not Found

```json
{
  "error": "not_found",
  "message": "Evolution job not found"
}
```

### 409 Conflict

```json
{
  "error": "conflict",
  "message": "Evolution already in progress for this playbook"
}
```

### 429 Limit Reached

```json
{
  "error": "limit_reached",
  "message": "Monthly evolution limit reached",
  "details": {
    "used": 100,
    "limit": 100,
    "resets_at": "2024-02-01T00:00:00Z"
  }
}
```

## Example Workflow

### 1. Record Outcomes

```python
for task in completed_tasks:
    client.record_outcome(
        playbook_id="abc-123",
        task_description=task.description,
        outcome=task.result,
        notes=task.feedback
    )
```

### 2. Trigger Evolution

```python
job = client.trigger_evolution("abc-123")
print(f"Evolution started: {job['job_id']}")
```

### 3. Poll for Completion

```python
import time

while True:
    status = client.get_evolution_status(job["job_id"])

    if status["status"] == "completed":
        print(f"New version: {status['new_version']}")
        print(f"Changes: {status['change_summary']}")
        break
    elif status["status"] == "failed":
        print(f"Evolution failed: {status['error']}")
        break

    time.sleep(10)
```

### 4. Get Updated Playbook

```python
playbook = client.get_playbook("abc-123")
print(playbook["content"])  # Updated content
```

## Next Steps

- [Usage & Billing API](/docs/api-reference/usage-billing)
- [Understanding Evolution Guide](/docs/user-guides/understanding-evolution)
- [Recording Outcomes Guide](/docs/developer-guides/recording-outcomes)
