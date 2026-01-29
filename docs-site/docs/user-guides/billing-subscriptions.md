---
sidebar_position: 4
---

# Billing & Subscriptions

Manage your ACE subscription, usage, and billing.

## Plans Overview

ACE offers three subscription tiers:

| Feature | Free | Pro | Team |
|---------|------|-----|------|
| **Playbooks** | 3 | 25 | Unlimited |
| **Evolutions/month** | 10 | 100 | Unlimited |
| **API requests/day** | 1,000 | 10,000 | Unlimited |
| **Outcome storage** | 30 days | 1 year | Unlimited |
| **Version history** | 10 versions | 50 versions | Unlimited |
| **Support** | Community | Email | Priority |
| **Price** | $0 | $29/month | $99/month |

## Choosing a Plan

### Free Plan

Best for:
- Trying out ACE
- Personal projects
- Learning and experimentation

Limitations:
- 3 playbooks maximum
- 10 evolutions per month
- 30-day outcome retention

### Pro Plan

Best for:
- Individual developers
- Small teams
- Production applications

Includes:
- 25 playbooks
- 100 evolutions per month
- 1-year outcome history
- Email support

### Team Plan

Best for:
- Larger teams
- Enterprise applications
- High-volume usage

Includes:
- Unlimited everything
- Priority support
- Advanced analytics (coming soon)
- Custom integrations (coming soon)

## Subscribing

### From the Dashboard

1. Go to **Settings** > **Billing**
2. Click **Upgrade Plan**
3. Select your desired plan
4. Enter payment details
5. Click **Subscribe**

### Payment Methods

We accept:
- Credit cards (Visa, Mastercard, Amex)
- Debit cards
- Link (one-click checkout)

All payments processed securely via Stripe.

## Managing Your Subscription

### Viewing Current Plan

1. Go to **Settings** > **Billing**
2. View your current plan details:
   - Plan name
   - Billing cycle
   - Next billing date
   - Current usage

### Changing Plans

**Upgrading:**
1. Go to **Settings** > **Billing**
2. Click **Change Plan**
3. Select new plan
4. Confirm upgrade

Upgrades take effect immediately. You'll be charged a prorated amount.

**Downgrading:**
1. Go to **Settings** > **Billing**
2. Click **Change Plan**
3. Select lower plan
4. Confirm downgrade

Downgrades take effect at the end of your current billing period.

### Canceling

1. Go to **Settings** > **Billing**
2. Click **Cancel Subscription**
3. Optionally provide feedback
4. Confirm cancellation

After cancellation:
- Access continues until period ends
- Data retained for 30 days
- Can reactivate anytime

## Usage Monitoring

### Dashboard View

The billing page shows:

```
┌─────────────────────────────────────┐
│ Current Usage                       │
├─────────────────────────────────────┤
│ Playbooks:    5 / 25                │
│ ███████░░░░░░░░░░░░░░░░░░░░ 20%    │
│                                     │
│ Evolutions:   45 / 100              │
│ █████████████░░░░░░░░░░░░░░ 45%    │
│                                     │
│ API Calls:    3,200 / 10,000        │
│ █████████░░░░░░░░░░░░░░░░░░ 32%    │
└─────────────────────────────────────┘
```

### Usage Alerts

Configure alerts when approaching limits:

1. Go to **Settings** > **Notifications**
2. Enable **Usage Alerts**
3. Set threshold (e.g., 80%)
4. Choose notification method (email, dashboard)

### API Usage Details

View detailed API usage:

```bash
curl https://aceagent.io/api/usage \
  -H "Authorization: Bearer YOUR_API_KEY"
```

Response:

```json
{
  "period": {
    "start": "2024-01-01T00:00:00Z",
    "end": "2024-01-31T23:59:59Z"
  },
  "usage": {
    "playbooks": {
      "current": 5,
      "limit": 25
    },
    "evolutions": {
      "current": 45,
      "limit": 100
    },
    "api_calls": {
      "current": 3200,
      "limit": 10000
    }
  }
}
```

## Billing Portal

Access the Stripe billing portal for:

- View invoices
- Update payment method
- Download receipts
- View payment history

### Accessing the Portal

1. Go to **Settings** > **Billing**
2. Click **Manage Billing**
3. Stripe portal opens in new tab

## Invoices

### Viewing Invoices

1. Go to **Settings** > **Billing**
2. Click **Invoice History**
3. View all past invoices

### Invoice Details

Each invoice includes:
- Invoice number
- Billing period
- Plan details
- Amount charged
- Payment method used
- Receipt link

### Downloading Receipts

1. Open invoice
2. Click **Download PDF**
3. Use for expense reporting

## Payment Issues

### Failed Payments

If a payment fails:

1. You'll receive an email notification
2. Dashboard shows billing alert
3. You have 7 days to update payment

After 7 days without payment:
- Account downgraded to Free plan
- Data above Free limits archived (not deleted)
- Access restored when payment succeeds

### Updating Payment Method

1. Go to **Settings** > **Billing**
2. Click **Manage Billing**
3. Update card in Stripe portal
4. Save changes

### Disputed Charges

Contact support at billing@aceagent.io with:
- Invoice number
- Dispute reason
- Any relevant screenshots

## Refunds

### Refund Policy

- Full refund within 14 days of first subscription
- Prorated refund for annual plans canceled early
- No refunds for usage-based overages

### Requesting a Refund

Email billing@aceagent.io with:
- Account email
- Reason for refund
- Invoice number

## Enterprise & Custom Plans

For organizations needing:
- Custom limits
- SLA guarantees
- Dedicated support
- On-premise deployment
- Custom integrations

Contact sales@aceagent.io to discuss options.

## Tax Information

### VAT/GST

If you need VAT invoices:
1. Go to **Settings** > **Billing**
2. Click **Manage Billing**
3. Add your VAT number in Stripe portal

### Tax Exemption

If tax-exempt, contact billing@aceagent.io with documentation.

## Troubleshooting

### Upgrade Not Reflecting

- Wait a few minutes for propagation
- Sign out and back in
- Check billing page for confirmation

### Usage Showing Incorrect

- Usage updates every hour
- Check specific counters in API
- Contact support if persists

### Can't Access Billing

- Verify email is confirmed
- Check you're the account owner
- Try incognito browser mode

## Next Steps

- [Monitor your usage](/docs/api-reference/usage-billing)
- [Optimize evolution usage](/docs/user-guides/understanding-evolution)
- [Contact support](mailto:support@aceagent.io)
