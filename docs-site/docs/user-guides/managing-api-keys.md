---
sidebar_position: 3
---

# Managing API Keys

Create and manage API keys to authenticate MCP tool access with ACE.

## Overview

API keys authenticate your MCP tool requests to ACE. Each key has specific
scopes that control what actions it can perform.

API-key onboarding is provider-neutral. You can sign in with email and password
or use hosted OAuth, then create an API key for Claude Code, Codex, Claude
Desktop, or another MCP client.

## Before You Start

You need all of the following before ACE Cloud will let you create or manage API
keys:

- A hosted ACE account
- A verified email address
- Active paid access, which means either:
  - an active trial, or
  - an active paid subscription

### Verification Requirements

- If you signed up with **email and password**, verify your email first.
- If you signed up with **hosted OAuth**, ACE Cloud treats your account as
  verified automatically.

### Trial and Subscription Gating

API keys are a hosted, paid-access feature in ACE Cloud.

- If you have not started a trial or subscription yet, the dashboard prompts you
  to start your free trial before you can create API keys.
- If your trial has ended, the dashboard prompts you to upgrade your plan before
  you can create or manage API keys.

## Creating API Keys

### Prerequisites

- Verified email address
- Active trial or paid subscription on ACE Cloud

### Provider-Neutral Onboarding Flow

Use these steps when you want MCP access without relying on hosted OAuth:

1. [Create your ACE account](/docs/getting-started/creating-account) with
   **email and password**
2. Verify your email
3. Start your trial or subscribe
4. Return to the dashboard and create an API key
5. Add the key to your MCP client as an `X-API-Key` header

If you prefer hosted OAuth for sign-in, you can still follow the same API-key
steps after you reach the dashboard.

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
| `playbooks:read` | View playbook content | Agents that use playbooks |
| `playbooks:write` | Create and update playbooks | Admin tools, dashboard |
| `outcomes:write` | Submit task outcomes | Active agents |
| `evolution:read` | View evolution status | Monitoring |
| `evolution:write` | Manually trigger evolution | Admin tools |

### Recommended Scope Combinations

**Production Agent (Read + Record):**
- `playbooks:read`
- `outcomes:write`

**Full Access:**
- Select All (all scopes)

**Monitoring Only:**
- `playbooks:read`
- `evolution:read`

## Using API Keys

### MCP Configuration

Pass your API key via the `X-API-Key` header in your MCP client config. See the
[MCP Integration Overview](/docs/developer-guides/mcp-integration/overview) for
generic setup instructions and
[Claude Code Setup](/docs/developer-guides/mcp-integration/claude-code) for a
full example.

### Environment Variables

Store keys in environment variables for MCP clients and tooling:

```bash
export ACE_API_KEY="ace_..."
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

Each key card on the dashboard shows:

- **Name** and **key prefix** (`ace_...`)
- **Scopes** as badges
- **Created** date and **last used** date

:::note
You cannot view the full key after creation. Only the prefix is shown.
:::

## Deleting API Keys

1. Go to **API Keys**
2. Click the **trash icon** on the key you want to delete
3. Confirm by clicking **Delete** in the confirmation prompt

:::warning
Deleting a key is immediate and irreversible. All requests using that key will fail.
:::

## Key Format

ACE API keys follow the format `ace_<random_string>`. The first 8 characters are stored as the key prefix for identification.

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

### "Email Verification Required"

- Verify the email on your ACE account before creating API keys
- If needed, resend the verification email from **Settings** in the dashboard

### "Start your free trial or subscribe to continue"

- Start your free trial if you have not activated paid access yet
- Upgrade your plan if your trial has already ended
- Return to **API Keys** after billing access is active

### Key Not Working with MCP

- Verify the `X-API-Key` header is set in your MCP config
- Check the key is correct (no extra spaces)
- Restart your MCP client after config changes

## Next Steps

- [Set up MCP integration](/docs/developer-guides/mcp-integration/overview)
- [Monitor usage](/docs/user-guides/billing-subscriptions)
