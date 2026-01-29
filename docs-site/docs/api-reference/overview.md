---
sidebar_position: 1
---

# API Overview

The ACE REST API for programmatic access to playbooks, outcomes, and evolution.

## Base URLs

| Environment | Base URL |
|-------------|----------|
| Production | `https://aceagent.io/api` |
| Staging | `https://ace-platform-staging.fly.dev/api` |
| Local | `http://localhost:8000/api` |

## Authentication

All API requests require authentication via API key:

```bash
curl https://aceagent.io/api/playbooks \
  -H "Authorization: Bearer YOUR_API_KEY"
```

See [Authentication](/docs/api-reference/authentication) for details.

## Request Format

### Content Type

All POST/PUT requests should use JSON:

```
Content-Type: application/json
```

### Request Body

```bash
curl -X POST https://aceagent.io/api/playbooks \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Playbook",
    "content": "# Instructions..."
  }'
```

## Response Format

All responses are JSON:

```json
{
  "id": "abc-123",
  "name": "My Playbook",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### Timestamps

All timestamps are ISO 8601 format in UTC:

```
2024-01-15T10:30:00Z
```

### IDs

All resource IDs are UUIDs:

```
550e8400-e29b-41d4-a716-446655440000
```

## Error Responses

Errors follow a consistent format:

```json
{
  "error": "error_code",
  "message": "Human-readable description",
  "details": {}
}
```

### HTTP Status Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request - Invalid parameters |
| 401 | Unauthorized - Invalid/missing API key |
| 403 | Forbidden - Insufficient permissions |
| 404 | Not Found - Resource doesn't exist |
| 422 | Unprocessable Entity - Validation error |
| 429 | Too Many Requests - Rate limited |
| 500 | Internal Server Error |

### Error Codes

| Code | Description |
|------|-------------|
| `invalid_request` | Malformed request body |
| `validation_error` | Field validation failed |
| `unauthorized` | Invalid API key |
| `forbidden` | Missing required scope |
| `not_found` | Resource not found |
| `rate_limit_exceeded` | Too many requests |
| `internal_error` | Server error |

## Rate Limiting

Requests are rate limited based on plan:

| Plan | Requests/Minute | Requests/Day |
|------|-----------------|--------------|
| Free | 60 | 1,000 |
| Pro | 300 | 10,000 |
| Team | 1,000 | Unlimited |

### Rate Limit Headers

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1704067200
```

### When Rate Limited

```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests",
  "retry_after": 60
}
```

## Pagination

List endpoints support pagination:

```bash
GET /api/playbooks?limit=20&offset=0
```

### Parameters

| Parameter | Default | Max | Description |
|-----------|---------|-----|-------------|
| `limit` | 20 | 100 | Items per page |
| `offset` | 0 | - | Skip N items |

### Response

```json
{
  "items": [...],
  "total": 45,
  "limit": 20,
  "offset": 0
}
```

## Filtering

Some endpoints support filtering:

```bash
GET /api/outcomes?outcome=success&after=2024-01-01
```

See individual endpoint docs for available filters.

## API Endpoints

### Playbooks

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/playbooks` | List playbooks |
| POST | `/playbooks` | Create playbook |
| GET | `/playbooks/{id}` | Get playbook |
| PUT | `/playbooks/{id}` | Update playbook |
| DELETE | `/playbooks/{id}` | Delete playbook |
| GET | `/playbooks/{id}/versions` | List versions |
| GET | `/playbooks/{id}/versions/{version}` | Get version |

### Outcomes

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/outcomes` | Record outcome |
| GET | `/playbooks/{id}/outcomes` | List outcomes |

### Evolution

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/playbooks/{id}/evolve` | Trigger evolution |
| GET | `/evolution/{job_id}/status` | Get job status |

### Usage & Billing

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/usage` | Get usage stats |
| GET | `/subscription` | Get subscription info |

## SDK Libraries

### Python

```bash
pip install ace-platform
```

```python
from ace_platform import AceClient

client = AceClient(api_key="your_key")
playbooks = client.list_playbooks()
```

### TypeScript/JavaScript

```bash
npm install @ace-platform/sdk
```

```typescript
import { AceClient } from "@ace-platform/sdk";

const client = new AceClient({ apiKey: "your_key" });
const playbooks = await client.listPlaybooks();
```

## OpenAPI Specification

The full OpenAPI spec is available at:

```
https://aceagent.io/openapi.json
```

Use it with tools like:
- Swagger UI
- Postman
- OpenAPI Generator

## Webhooks (Coming Soon)

Subscribe to events:
- `playbook.created`
- `playbook.updated`
- `evolution.completed`
- `evolution.failed`

## Next Steps

- [Authentication](/docs/api-reference/authentication)
- [Playbooks API](/docs/api-reference/playbooks)
- [Outcomes API](/docs/api-reference/outcomes)
