---
sidebar_position: 5
---

# Authentication

Learn how to authenticate with the ACE API.

## Authentication Methods

ACE supports two authentication methods:

1. **API Keys** - For programmatic access
2. **JWT Tokens** - For dashboard/web app access

For most integrations, you'll use **API Keys**.

## API Key Authentication

### Obtaining an API Key

1. Log in to [app.aceagent.io](https://app.aceagent.io)
2. Navigate to **API Keys**
3. Click **Create API Key**
4. Select required scopes
5. Copy and securely store the key

### Using API Keys

Include the key in the `Authorization` header:

```bash
curl https://aceagent.io/api/playbooks \
  -H "Authorization: Bearer ace_live_abc123..."
```

### Key Format

ACE API keys follow this format:

```
ace_{environment}_{random_string}
```

| Prefix | Environment |
|--------|-------------|
| `ace_live_` | Production |
| `ace_test_` | Testing |
| `ace_dev_` | Development |

## Scopes

API keys have scopes that control access:

### Available Scopes

| Scope | Description |
|-------|-------------|
| `playbooks:read` | Read playbook content and versions |
| `playbooks:write` | Create, update, delete playbooks |
| `outcomes:read` | View recorded outcomes |
| `outcomes:write` | Record new outcomes |
| `evolution:read` | View evolution status |
| `evolution:write` | Trigger evolution |
| `usage:read` | View usage statistics |

### Checking Required Scopes

Each API endpoint documents its required scope. For example:

```
GET /api/playbooks
Required scope: playbooks:read

POST /api/outcomes
Required scope: outcomes:write
```

### Scope Errors

If a key lacks required scopes:

```json
{
  "error": "forbidden",
  "message": "API key missing required scope: outcomes:write",
  "required_scopes": ["outcomes:write"]
}
```

## MCP Authentication

For MCP connections, pass the API key via environment variable:

```json
{
  "mcpServers": {
    "ace": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://aceagent.io/mcp/sse"],
      "env": {
        "AUTHORIZATION": "Bearer ace_live_abc123..."
      }
    }
  }
}
```

The MCP server reads the `AUTHORIZATION` header from the SSE connection.

## JWT Authentication (Web App)

The web dashboard uses JWT tokens. These are managed automatically:

1. User logs in (email/password or OAuth)
2. Server issues JWT token
3. Token stored in secure cookie
4. Token refreshed automatically

:::note
JWT tokens are for web app use only. Use API keys for programmatic access.
:::

## Error Responses

### 401 Unauthorized

Missing or invalid authentication:

```json
{
  "error": "unauthorized",
  "message": "Invalid or missing API key"
}
```

**Causes:**
- No `Authorization` header
- Malformed header (missing `Bearer ` prefix)
- Invalid API key
- Revoked API key

### 403 Forbidden

Valid authentication but insufficient permissions:

```json
{
  "error": "forbidden",
  "message": "Insufficient permissions for this action",
  "required_scopes": ["playbooks:write"]
}
```

**Causes:**
- API key missing required scope
- Action not allowed for this account

## Security Best Practices

### 1. Never Expose Keys in Code

```python
# Bad - hardcoded key
client = AceClient(api_key="ace_live_abc123...")

# Good - environment variable
import os
client = AceClient(api_key=os.environ["ACE_API_KEY"])
```

### 2. Use .gitignore

```gitignore
# Environment files
.env
.env.local
.env.*.local

# Secrets
secrets/
*.pem
*.key
```

### 3. Minimum Required Scopes

Create keys with only necessary scopes:

| Use Case | Scopes |
|----------|--------|
| Read-only agent | `playbooks:read` |
| Production agent | `playbooks:read`, `outcomes:write` |
| Admin dashboard | All scopes |

### 4. Rotate Keys Regularly

1. Create new key
2. Update all configurations
3. Test new key works
4. Revoke old key

### 5. Monitor Key Usage

Check the dashboard for:
- Last used timestamp
- Request patterns
- Error rates

### 6. Use Environment-Specific Keys

Create separate keys for:
- Development
- Staging
- Production

## Rate Limiting

API keys are rate limited based on plan:

| Plan | Requests/Minute | Requests/Day |
|------|-----------------|--------------|
| Free | 60 | 1,000 |
| Pro | 300 | 10,000 |
| Team | 1,000 | Unlimited |

### Rate Limit Headers

Responses include rate limit info:

```
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1704067200
```

### Handling Rate Limits

When rate limited (HTTP 429):

```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests",
  "retry_after": 60
}
```

Implement exponential backoff:

```python
import time

def make_request_with_retry(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return func()
        except RateLimitError as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(min(2 ** attempt * e.retry_after, 300))
```

## Troubleshooting

### "API key not found"

- Verify key is correct (no typos)
- Check key hasn't been revoked
- Ensure using correct environment

### "Invalid token format"

- Include `Bearer ` prefix (with space)
- Check for extra whitespace
- Verify no encoding issues

### Key working in curl but not in app

- Check header is being set correctly
- Verify no proxy stripping headers
- Look for CORS issues in browser

## Next Steps

- [Create API keys](/docs/user-guides/managing-api-keys)
- [API reference](/docs/api-reference/overview)
- [MCP integration](/docs/developer-guides/mcp-integration/overview)
