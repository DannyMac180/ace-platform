---
sidebar_position: 3
---

# Managing API Keys

Create and manage API keys to authenticate MCP tool access with ACE.

## Overview

API keys authenticate your MCP tool requests to ACE. Each key has specific scopes that control what actions it can perform.

## Creating API Keys

### Prerequisites

- Verified email address
- Active ACE account

### From the Dashboard

1. Log in to [app.aceagent.io](https://app.aceagent.io)
2. Navigate to **API Keys** in the sidebar
3. Click **Create API Key**
4. Configure your key:
   - **Name** - Descriptive name (e.g., "Production Agent", "Local Dev")
   - **Scopes** - Select required permissions
5. Click **Create**
6. **Copy your key immediately** - it won't be shown again!

## API Key Scopes

| Scope | Description | Use Case |
|-------|-------------|----------|
| `playbooks:read` | Read playbook content and versions | Agents that use playbooks |
| `playbooks:write` | Create, update, delete playbooks | Admin tools, dashboard |
| `outcomes:read` | View recorded outcomes | Analytics, reporting |
| `outcomes:write` | Record new outcomes | Active agents |
| `evolution:read` | Check evolution status | Monitoring |
| `evolution:write` | Trigger manual evolution | Admin tools |
| `usage:read` | View usage statistics | Billing, monitoring |

### Recommended Scope Combinations

**Production Agent (Read + Record):**
- `playbooks:read`
- `outcomes:write`

**Admin Key (Full Access):**
- All scopes

**Monitoring Only:**
- `playbooks:read`
- `evolution:read`
- `usage:read`

## Using API Keys

### MCP Configuration

For MCP clients, configure the ACE server with your API key:

```json
{
  "mcpServers": {
    "ace": {
      "type": "sse",
      "url": "https://aceagent.io/mcp/sse",
      "headers": {
        "X-API-Key": "YOUR_API_KEY"
      }
    }
  }
}
```

### Environment Variables

Store keys in environment variables for MCP clients and tooling:

```bash
export ACE_API_KEY="ace_live_..."
```

## Key Security

### Best Practices

1. **Never commit keys to version control**
   ```gitignore
   # .gitignore
   .env
   .env.local
   **/secrets/*
   ```

2. **Use environment variables**
   - Development: `.env` files
   - Production: Secret managers (AWS Secrets, Vault, etc.)

3. **Rotate keys regularly**
   - Create new key
   - Update configurations
   - Revoke old key

4. **Use minimum required scopes**
   - Production agents don't need `playbooks:write`
   - Read-only dashboards don't need write scopes

5. **Use separate keys per environment**
   - Development key
   - Staging key
   - Production key

### What to Do If a Key Is Compromised

1. **Immediately revoke the key** in the dashboard
2. **Create a new key** with the same scopes
3. **Update all configurations** using the old key
4. **Review activity logs** for unauthorized usage
5. **Rotate any other secrets** that might be exposed

## Viewing API Keys

### Key List

The dashboard shows:

| Column | Description |
|--------|-------------|
| Name | Key identifier |
| Prefix | First 8 characters (`ace_live_...`) |
| Scopes | Assigned permissions |
| Created | Creation date |
| Last Used | Most recent tool call |

### Key Details

Click on a key to view:

- Full scope list
- Creation timestamp
- Last activity
- Usage statistics

:::note
You cannot view the full key after creation. Only the prefix is shown.
:::

## Revoking API Keys

### From Dashboard

1. Go to **API Keys**
2. Find the key to revoke
3. Click the **...** menu
4. Select **Revoke**
5. Confirm the action

:::warning
Revoking a key is immediate and irreversible. All requests using that key will fail.
:::

## Key Prefixes

ACE API keys have prefixes indicating their type:

| Prefix | Environment |
|--------|-------------|
| `ace_live_` | Production |
| `ace_test_` | Testing/staging |
| `ace_dev_` | Development |

## Rate Limits

If you encounter rate limits, wait and retry with exponential backoff.

## Troubleshooting

### "Invalid API Key"

- Verify the key is copied correctly (no extra spaces)
- Check the key hasn't been revoked
- Ensure you're using the correct environment

### "Insufficient Scopes"

- Check the error message for required scope
- Create a new key with additional scopes
- Update your configuration

### "API Key Required"

- Verify the `X-API-Key` header is present
- Ensure the key isn't empty or malformed

### Key Not Working with MCP

- Verify the `X-API-Key` header is set in your MCP config
- Check the key is correct (no extra spaces)
- Restart your MCP client after config changes

## Next Steps

- [Set up MCP integration](/docs/developer-guides/mcp-integration/overview)
- [Monitor usage](/docs/user-guides/billing-subscriptions)
