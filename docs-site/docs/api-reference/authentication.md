---
sidebar_position: 2
---

# Authentication API

API key management and authentication endpoints.

## Overview

ACE uses API keys for authentication. Keys are passed via the `Authorization` header:

```
Authorization: Bearer YOUR_API_KEY
```

## API Keys

### Create API Key

:::note
API keys are created through the dashboard UI, not via API.
:::

1. Log in to [app.aceagent.io](https://app.aceagent.io)
2. Navigate to **API Keys**
3. Click **Create API Key**
4. Select scopes and confirm

### List API Keys

```
GET /api/keys
```

**Required scope:** `keys:read`

**Response:**

```json
{
  "items": [
    {
      "id": "key_abc123",
      "name": "Production Agent",
      "prefix": "ace_live_abc1",
      "scopes": ["playbooks:read", "outcomes:write"],
      "created_at": "2024-01-15T10:30:00Z",
      "last_used_at": "2024-01-20T14:22:00Z"
    }
  ],
  "total": 1
}
```

### Get API Key

```
GET /api/keys/{key_id}
```

**Required scope:** `keys:read`

**Response:**

```json
{
  "id": "key_abc123",
  "name": "Production Agent",
  "prefix": "ace_live_abc1",
  "scopes": ["playbooks:read", "outcomes:write"],
  "created_at": "2024-01-15T10:30:00Z",
  "last_used_at": "2024-01-20T14:22:00Z"
}
```

### Revoke API Key

```
DELETE /api/keys/{key_id}
```

**Required scope:** `keys:write`

**Response:**

```json
{
  "message": "API key revoked successfully"
}
```

:::warning
Revoking a key is immediate and permanent. All requests using that key will fail.
:::

## Scopes

### Available Scopes

| Scope | Description |
|-------|-------------|
| `playbooks:read` | Read playbook content and versions |
| `playbooks:write` | Create, update, delete playbooks |
| `outcomes:read` | View recorded outcomes |
| `outcomes:write` | Record new outcomes |
| `evolution:read` | View evolution status |
| `evolution:write` | Trigger manual evolution |
| `usage:read` | View usage statistics |
| `keys:read` | List and view API keys |
| `keys:write` | Create and revoke API keys |

### Scope Requirements

Each endpoint requires specific scopes. If a key lacks required scopes:

```json
{
  "error": "forbidden",
  "message": "API key missing required scope: playbooks:write",
  "required_scopes": ["playbooks:write"]
}
```

## Verify Token

Check if an API key is valid and get its details:

```
GET /api/auth/verify
```

**Response:**

```json
{
  "valid": true,
  "key_id": "key_abc123",
  "scopes": ["playbooks:read", "outcomes:write"],
  "user_id": "user_xyz789",
  "email": "user@example.com"
}
```

## Error Responses

### 401 Unauthorized

```json
{
  "error": "unauthorized",
  "message": "Invalid or missing API key"
}
```

**Causes:**
- No `Authorization` header
- Invalid key format
- Non-existent key
- Revoked key

### 403 Forbidden

```json
{
  "error": "forbidden",
  "message": "Insufficient permissions",
  "required_scopes": ["playbooks:write"]
}
```

**Causes:**
- Key missing required scope
- Account-level restriction

## Example: Key Lifecycle

### 1. Create Key (Dashboard)

Navigate to API Keys → Create API Key

### 2. Use Key

```bash
curl https://aceagent.io/api/playbooks \
  -H "Authorization: Bearer ace_live_abc123..."
```

### 3. Monitor Usage

```bash
curl https://aceagent.io/api/keys/key_abc123 \
  -H "Authorization: Bearer ADMIN_KEY"
```

### 4. Revoke When Done

```bash
curl -X DELETE https://aceagent.io/api/keys/key_abc123 \
  -H "Authorization: Bearer ADMIN_KEY"
```

## Security Best Practices

### Store Keys Securely

```python
# Good - environment variable
import os
api_key = os.environ["ACE_API_KEY"]

# Bad - hardcoded
api_key = "ace_live_abc123..."
```

### Use Minimum Scopes

| Use Case | Recommended Scopes |
|----------|-------------------|
| Read-only agent | `playbooks:read` |
| Recording agent | `playbooks:read`, `outcomes:write` |
| Admin tools | All scopes |

### Rotate Regularly

1. Create new key
2. Update configurations
3. Test new key
4. Revoke old key

### Monitor for Anomalies

- Unexpected `last_used_at` changes
- High request volumes
- Access from unusual locations

## Rate Limits

Authentication endpoints have specific limits:

| Endpoint | Limit |
|----------|-------|
| `GET /api/auth/verify` | 30/minute |
| `DELETE /api/keys/{id}` | 10/minute |

## Next Steps

- [API Overview](/docs/api-reference/overview)
- [Managing API Keys (Guide)](/docs/user-guides/managing-api-keys)
- [Playbooks API](/docs/api-reference/playbooks)
