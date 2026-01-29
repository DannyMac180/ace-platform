---
sidebar_position: 6
---

# Usage & Billing API

Monitor usage and manage subscription information.

## Get Usage

Get current usage statistics.

```
GET /api/usage
```

**Required scope:** `usage:read`

### Response

```json
{
  "period": {
    "start": "2024-01-01T00:00:00Z",
    "end": "2024-01-31T23:59:59Z"
  },
  "playbooks": {
    "current": 5,
    "limit": 25
  },
  "evolutions": {
    "current": 45,
    "limit": 100
  },
  "outcomes": {
    "current": 234,
    "this_month": 89
  },
  "api_calls": {
    "today": 1250,
    "this_month": 28500,
    "daily_limit": 10000
  }
}
```

### Usage Fields

| Field | Description |
|-------|-------------|
| `playbooks.current` | Active playbooks |
| `playbooks.limit` | Maximum allowed |
| `evolutions.current` | Evolutions this month |
| `evolutions.limit` | Monthly limit |
| `outcomes.current` | Total outcomes recorded |
| `outcomes.this_month` | Outcomes this month |
| `api_calls.today` | API calls today |
| `api_calls.this_month` | API calls this month |
| `api_calls.daily_limit` | Daily API call limit |

## Get Usage History

Get historical usage data.

```
GET /api/usage/history
```

**Required scope:** `usage:read`

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `period` | string | `month` | Aggregation: `day`, `week`, `month` |
| `start` | string | - | Start date (ISO 8601) |
| `end` | string | - | End date (ISO 8601) |

### Example Request

```bash
curl "https://aceagent.io/api/usage/history?period=day&start=2024-01-01&end=2024-01-31" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

### Response

```json
{
  "period": "day",
  "data": [
    {
      "date": "2024-01-01",
      "api_calls": 450,
      "outcomes_recorded": 12,
      "evolutions_triggered": 1
    },
    {
      "date": "2024-01-02",
      "api_calls": 380,
      "outcomes_recorded": 8,
      "evolutions_triggered": 0
    }
  ]
}
```

## Get Subscription

Get current subscription details.

```
GET /api/subscription
```

**Required scope:** `usage:read`

### Response

```json
{
  "plan": "pro",
  "status": "active",
  "current_period": {
    "start": "2024-01-15T00:00:00Z",
    "end": "2024-02-14T23:59:59Z"
  },
  "features": {
    "playbooks_limit": 25,
    "evolutions_limit": 100,
    "outcome_retention_days": 365,
    "version_history_limit": 50,
    "api_rate_limit": 300,
    "support_level": "email"
  },
  "billing": {
    "amount": 2900,
    "currency": "usd",
    "interval": "month",
    "next_billing_date": "2024-02-15T00:00:00Z"
  }
}
```

### Plan Values

| Plan | Description |
|------|-------------|
| `free` | Free tier |
| `pro` | Pro subscription |
| `team` | Team subscription |

### Status Values

| Status | Description |
|--------|-------------|
| `active` | Subscription active |
| `past_due` | Payment failed |
| `canceled` | Canceled (active until period end) |
| `unpaid` | Payment failed, access restricted |

## Get Billing Portal URL

Get a URL to the Stripe billing portal.

```
POST /api/subscription/portal
```

**Required scope:** `usage:read`

### Request Body

| Field | Type | Description |
|-------|------|-------------|
| `return_url` | string | URL to return to after portal |

### Response

```json
{
  "url": "https://billing.stripe.com/session/..."
}
```

The URL is valid for 24 hours.

## Get Invoices

List past invoices.

```
GET /api/subscription/invoices
```

**Required scope:** `usage:read`

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 10 | Items per page |
| `offset` | integer | 0 | Skip N items |

### Response

```json
{
  "items": [
    {
      "id": "inv_abc123",
      "number": "ACE-0042",
      "amount": 2900,
      "currency": "usd",
      "status": "paid",
      "created_at": "2024-01-15T00:00:00Z",
      "paid_at": "2024-01-15T00:01:30Z",
      "pdf_url": "https://pay.stripe.com/invoice/...",
      "hosted_invoice_url": "https://invoice.stripe.com/..."
    }
  ],
  "total": 3,
  "limit": 10,
  "offset": 0
}
```

### Invoice Status Values

| Status | Description |
|--------|-------------|
| `draft` | Not yet finalized |
| `open` | Awaiting payment |
| `paid` | Successfully paid |
| `void` | Canceled |
| `uncollectible` | Payment failed |

## Check Feature Access

Check if a specific feature is available.

```
GET /api/subscription/features/{feature}
```

**Required scope:** `usage:read`

### Path Parameters

| Parameter | Description |
|-----------|-------------|
| `feature` | Feature name |

### Available Features

- `playbooks`
- `evolutions`
- `outcomes`
- `api_calls`
- `priority_support`
- `custom_integrations`

### Response

```json
{
  "feature": "evolutions",
  "available": true,
  "current": 45,
  "limit": 100,
  "percentage_used": 45
}
```

### Response: Limit Reached

```json
{
  "feature": "evolutions",
  "available": false,
  "current": 100,
  "limit": 100,
  "percentage_used": 100,
  "upgrade_required": true,
  "next_reset": "2024-02-01T00:00:00Z"
}
```

## Alerts Configuration

Configure usage alerts.

### Get Alert Settings

```
GET /api/usage/alerts
```

**Required scope:** `usage:read`

### Response

```json
{
  "alerts": [
    {
      "id": "alert_abc123",
      "metric": "evolutions",
      "threshold": 80,
      "enabled": true,
      "notification_channels": ["email", "dashboard"]
    },
    {
      "id": "alert_def456",
      "metric": "api_calls",
      "threshold": 90,
      "enabled": true,
      "notification_channels": ["email"]
    }
  ]
}
```

### Update Alert Settings

```
PUT /api/usage/alerts/{alert_id}
```

**Required scope:** `usage:read`

### Request Body

```json
{
  "threshold": 75,
  "enabled": true,
  "notification_channels": ["email", "dashboard"]
}
```

## Error Responses

### 403 Forbidden

```json
{
  "error": "forbidden",
  "message": "Billing access restricted",
  "details": "Only account owners can access billing information"
}
```

### 402 Payment Required

```json
{
  "error": "payment_required",
  "message": "Subscription payment failed",
  "details": {
    "last_payment_attempt": "2024-01-20T10:00:00Z",
    "update_payment_url": "https://billing.stripe.com/..."
  }
}
```

## Upgrading/Downgrading

Subscription changes are handled through the Stripe billing portal:

```python
# Get portal URL
response = client.create_billing_portal_session(
    return_url="https://app.aceagent.io/settings/billing"
)

# Redirect user to portal
redirect(response["url"])
```

## Webhook Events (Coming Soon)

Subscribe to billing events:

- `subscription.created`
- `subscription.updated`
- `subscription.canceled`
- `invoice.paid`
- `invoice.payment_failed`
- `usage.threshold_reached`

## Next Steps

- [Billing & Subscriptions Guide](/docs/user-guides/billing-subscriptions)
- [API Overview](/docs/api-reference/overview)
- [Managing API Keys](/docs/user-guides/managing-api-keys)
