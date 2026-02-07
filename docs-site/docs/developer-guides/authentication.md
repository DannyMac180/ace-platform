---
sidebar_position: 5
---

# Authentication

Learn how to authenticate with ACE for MCP integrations.

## Authentication Methods

ACE supports two authentication methods:

1. **API Keys** - For MCP tool access
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

Pass the key in your MCP client headers or env config (see MCP Authentication below).

### Key Format

ACE API keys follow the format `ace_<random_string>`. The first 8 characters are stored as the key prefix for identification.

For full details on creating and managing keys, see [Managing API Keys](/docs/user-guides/managing-api-keys).

## Scopes

API keys have scopes that control access. See [Managing API Keys](/docs/user-guides/managing-api-keys) for the full scopes reference.

Each MCP tool documents its required scope (see [MCP Integration](/docs/developer-guides/mcp-integration/overview)). If a key lacks required scopes, the server returns a `forbidden` error:

```json
{
  "error": "forbidden",
  "message": "API key missing required scope: outcomes:write",
  "required_scopes": ["outcomes:write"]
}
```

## MCP Authentication

For MCP connections, pass the API key via the `X-API-Key` header. See [MCP Integration](/docs/developer-guides/mcp-integration/overview) for full connection setup details.

## JWT Authentication (Web App)

The web dashboard uses JWT tokens. These are managed automatically:

1. User logs in (email/password or OAuth)
2. Server issues JWT token
3. Token stored in secure cookie
4. Token refreshed automatically

:::note
JWT tokens are for web app use only. Use API keys for MCP tool access.
:::

## Common Auth Errors

### Unauthorized

**Causes:**
- No `X-API-Key` header
- Invalid API key
- Revoked API key

### Insufficient Permissions

**Causes:**
- API key missing required scope
- Action not allowed for this account

## Security Best Practices

For detailed security practices (key rotation, `.gitignore` setup, scope recommendations), see the [Managing API Keys](/docs/user-guides/managing-api-keys#key-security) guide.

Key principles:
1. **Never hardcode keys** — use environment variables
2. **Use minimum required scopes** — production agents typically only need `playbooks:read` and `outcomes:write`
3. **Rotate keys regularly** and revoke compromised keys immediately
4. **Use separate keys per environment** (development, staging, production)

## Rate Limiting

API keys are subject to rate limiting based on your [subscription tier](/docs/user-guides/billing-subscriptions). When rate limited (HTTP 429), implement exponential backoff:

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

- Verify the API key is correct
- Check for extra whitespace
- Verify no encoding issues

### Key working in one client but not another

- Check headers are being set correctly
- Verify no proxy is stripping headers
- Confirm the MCP client supports custom headers

## Next Steps

- [Create API keys](/docs/user-guides/managing-api-keys)
- [MCP integration](/docs/developer-guides/mcp-integration/overview)
