---
sidebar_position: 4
---

# Create an ACE Cloud Account

Create and verify an account for `ACE Cloud Personal`, `ACE Cloud Team`, or `ACE Enterprise`.

If you want `ACE OSS` on your own machine or infrastructure, you do not need an ACE-hosted account. Start with [ACE OSS & Local Start](/docs/getting-started/oss-local-start).

On ACE Cloud, you can onboard in two ways:

- **Email and password + API key** for a provider-neutral path that works well
  with MCP clients like Claude Code or Codex
- **Hosted OAuth** for faster sign-in with Google or GitHub

Hosted OAuth is a convenience layer, not a requirement. Both paths land in the
same hosted workspace.

If you are choosing between `ACE OSS`, `ACE Cloud Personal`, and `ACE Cloud Team`, read [Choosing the right ACE product](/docs/getting-started/product-split) first.

## Sign Up

### Option 1: Email & Password

1. Visit [app.aceagent.io](https://app.aceagent.io)
2. Click **Sign Up**
3. Enter your email address
4. Create a strong password (minimum 8 characters)
5. Click **Create Account**
6. Check your email for verification link
7. Verify your email before creating API keys or using verification-gated
   hosted features

This is the recommended path if you want to manage ACE access with an API key
instead of signing your MCP client in through hosted OAuth.

### Option 2: Hosted OAuth

Sign up instantly using:

- **Google** - Use your Google Workspace or personal account
- **GitHub** - Recommended for developers

Hosted OAuth automatically verifies your email on ACE Cloud, so it can shorten
the path into the product. You can still switch to API-key-based MCP access
later from the dashboard.

## Recommended Onboarding Paths

### Provider-Neutral MCP Setup

Use this flow for Claude Code, Codex, or any MCP client where you want to
authenticate with an ACE API key:

1. Create your account with **email and password**
2. Verify your email
3. Start your trial or subscribe
4. Create an API key in the dashboard
5. Add that key to your MCP client using the `X-API-Key` header

### Fastest Hosted Sign-In

Use this flow if you want the quickest way into the hosted app:

1. Sign up with **Google** or **GitHub**
2. Land in your workspace with email verification already satisfied
3. Start your trial or subscribe when you need API-key-gated hosted features
4. Create an API key later if you want MCP access without relying on hosted OAuth

## Email Verification

Email verification is required to:

- Create API keys
- Record outcomes
- Trigger evolutions
- Access billing features

On ACE Cloud:

- **Email/password accounts** must complete email verification before those
  actions are unlocked
- **Hosted OAuth accounts** are treated as verified immediately

### Verification Process

1. Check your inbox for an email from `noreply@aceagent.io`
2. Click the **Verify Email** button
3. You'll be redirected to the dashboard
4. A confirmation banner shows verification succeeded

### Didn't Receive the Email?

- Check your spam/junk folder
- Wait a few minutes and try again
- Click **Resend Verification** in the dashboard
- Contact support if issues persist

## Your First Hosted Workspace

When you create a hosted ACE account, ACE places you into a hosted `personal` workspace.

That means:

- your hosted account has a one-seat workspace by default
- you can keep using ACE as a solo hosted user without enabling team features
- invites and shared workspace features stay off until you upgrade that workspace to `team`

If you were already a hosted solo user before the workspace rollout, ACE maps that account into the same `personal` workspace model without requiring a separate signup. If you want the March 2026 migration summary for existing hosted users, read the [hosted plans update](/docs/user-guides/hosted-plans-migration).

## Next Steps

With your account ready:

1. [Create an API Key](/docs/user-guides/managing-api-keys)
2. [Understand personal vs team workspaces](/docs/user-guides/workspaces-and-teams)
3. [Read the hosted plans update](/docs/user-guides/hosted-plans-migration)
4. [Set up your first playbook](/docs/getting-started/quick-start)
5. [Connect via MCP](/docs/developer-guides/mcp-integration/overview)
6. [Review hosted plans, billing states, and usage limits](/docs/user-guides/billing-subscriptions)
