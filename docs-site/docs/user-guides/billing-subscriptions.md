---
sidebar_position: 4
---

# Hosted Plans, Billing, and Limits

ACE Cloud uses a plan-aware entitlement model. This page explains what your
hosted workspace includes, what counts against limits, what warning and blocked
states mean, and when you should upgrade.

## Two Layers You Will See In Hosted ACE

Hosted ACE currently exposes two related concepts:

| Layer | Values you may see | What it controls |
| --- | --- | --- |
| **Workspace plan** | `personal`, `team`, `enterprise` | Seat model, collaboration, and governance features |
| **Billing tier / effective tier** | `free` (trial envelope), `starter`, `pro`, `ultra`, `enterprise` | Playbook allowance, hosted eval allowance, storage envelope, and managed inference budget |
| **Billing state** | `active`, active + trial indicator, `past_due`, `unpaid`, `canceled`, `none` | Whether hosted paid features continue to work |

Think of the **workspace plan** as the shape of the workspace and the
**billing tier** as the usage envelope that funds hosted operations.

:::note
Hosted entitlements such as cloud sync, hosted backups, hosted evals, billing
checks, and ACE-managed inference are cloud-side services. They do not apply to
ACE OSS or self-managed local usage.
:::

## Workspace Plans And Core Entitlements

| Workspace plan | Best for | Core hosted entitlements | Typical upgrade trigger |
| --- | --- | --- | --- |
| **Personal** | One hosted user | Cloud sync, hosted backups, ACE-managed inference, hosted evals, one-seat workspace | You need more hosted allowance or want to invite teammates |
| **Team** | Shared hosted work | Personal entitlements plus shared workspace features such as invites and approvals | You need multiple seats, shared playbooks, or workspace-level collaboration |
| **Enterprise** | Governance-heavy or private deployments | Team capabilities plus enterprise governance, support, and deployment flexibility | You need SSO, auditability, procurement controls, or private deployment terms |

In the current product, a hosted user can see both values at once. For example,
you might have a `personal` workspace while the billing and entitlement APIs
still report a `starter`, `pro`, or `ultra` tier for the actual monthly usage
envelope.

## Trial Envelopes

When a hosted account is in an active trial:

- hosted convenience features stay available,
- the workspace still behaves like its selected workspace plan, but
- usage enforcement falls back to the **trial envelope** until the trial ends.

That trial envelope is currently the same effective limit shape as the internal
`free` tier:

- **1 playbook**
- **5 hosted eval runs per billing period**
- **5 MiB hosted storage**
- **$1.00 of managed inference budget**

In entitlement responses, this usually appears as:

- the selected subscription tier still reflecting the destination tier, such as
  `starter`, and
- the **effective tier** falling back to `free` while `is_trialing = true`.

This is why a trial workspace can still have hosted feature access while using a
smaller temporary allowance.

## Current Hosted Usage Envelopes

These are the current hosted envelopes enforced by the app today.

| Effective tier | Typical plan code you may see | Max playbooks | Hosted eval runs / billing period | Managed inference budget / billing period | Hosted storage |
| --- | --- | ---: | ---: | ---: | ---: |
| **Trial envelope** | `free`, active trial, or effective `free` limits | 1 | 5 | $1.00 | 5 MiB |
| **Starter** | `starter` or `personal-starter` | 5 | 100 | $9.00 | 100 MiB |
| **Pro** | `pro` or `personal-pro` | 20 | 500 | $29.00 | 1 GiB |
| **Ultra** | `ultra` or `personal-ultra` | 100 | 2,000 | $79.00 | 10 GiB |
| **Enterprise** | `enterprise` | Custom / unlimited | Custom / unlimited | Custom / unlimited | Custom / unlimited |

Workspace admins can also configure **workspace-specific soft or hard
thresholds** for:

- hosted storage,
- hosted eval runs,
- managed inference requests, and
- managed inference tokens.

That is why your dashboard can show `warning` or `blocked` on a workspace even
before the broader billing-period envelope is fully exhausted.

## What Counts Against Limits

- **Playbooks**: creating or importing hosted playbooks counts against the
  playbook allowance.
- **Hosted evals**: each hosted eval run counts against the monthly hosted eval
  envelope.
- **Managed inference**: ACE-run model requests count toward managed inference
  requests, tokens, and spend.
- **Hosted storage**: stored hosted workspace data counts against the storage
  envelope.

## Warning And Blocked States

The entitlement model uses three usage states:

| State | What it means | What happens |
| --- | --- | --- |
| **ok** | You are below the configured thresholds. | Hosted actions continue normally. |
| **warning** | You crossed a soft limit such as storage, hosted eval runs, or managed inference tokens. | The workspace still works, but you are close to a block and should clean up, wait for reset, or upgrade. |
| **blocked** | You hit a hard workspace threshold or exhausted a billing-period envelope. | New hosted actions of that type are rejected until the limit resets, the workspace limit is raised, or the plan is upgraded. |

Typical blocked examples:

- **Managed inference blocked**: the workspace has hit a request or token limit.
- **Hosted eval blocked**: the workspace has hit the hosted eval allowance.
- **Billing-period budget blocked**: the workspace has exhausted the monthly
  managed inference spend envelope.

## Billing States And What They Mean

| Billing state or signal | Meaning | What to do |
| --- | --- | --- |
| **No subscription / `none`** | Hosted paid access has not started yet. | Start a trial or subscribe from **Settings** > **Billing**. |
| **Active** | Billing is in good standing. | Continue using hosted features within the current envelope. |
| **Active + trial indicator** | The workspace is trialing. Access is on, but the trial envelope is still enforced. | Use the trial allowance to evaluate ACE, then keep billing active if you want the paid envelope after the trial ends. |
| **Past due** | Payment collection failed. | Update the payment method in the billing portal. Hosted paid actions can be blocked until the account is current. |
| **Unpaid** | The subscription remains unpaid. | Fix billing before expecting hosted paid features to resume. |
| **Canceled** | The paid subscription has ended. | Resubscribe if you want to restore paid hosted access. |

In workspace entitlement views, a Stripe `trialing` subscription is normalized
to **active access** plus a separate `is_trialing` signal. That separation is
intentional: access and limits are related, but they are not the same thing.

## Upgrade Paths

Choose the upgrade path that matches the thing you are running out of:

- **Need more hosted allowance but still only one user**:
  move up from trial -> `starter` -> `pro` -> `ultra`.
- **Need invites, shared workflows, or more than one seat**:
  upgrade the workspace from **personal** to **team**.
- **Need governance or private deployment terms**:
  move to **enterprise**.
- **Blocked by billing state, not by plan size**:
  update the payment method or reactivate the subscription before changing tiers.

## Where To Check In The App

Use these app surfaces together:

- **Settings** > **Billing**: billing state, plan selection, and billing portal
- **Workspace settings**: workspace plan, seat model, and managed inference mode
- **Usage and entitlement readouts**: current counters plus `warning` or
  `blocked` states

## Related Guides

- [Creating an Account](/docs/getting-started/creating-account)
- [Core Concepts](/docs/getting-started/core-concepts)
- [Understanding Evolution](/docs/user-guides/understanding-evolution)
- [Managing API Keys](/docs/user-guides/managing-api-keys)
