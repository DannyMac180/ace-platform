# Week 1 Outreach Runbook: Unactivated Signups

## Goal
Move new signups to trial start quickly with short, personal founder outreach.

## Daily Pull (Last 7 Days, No Trial Start)
Run in Postgres:

```sql
SELECT
  u.id,
  u.email,
  u.created_at,
  u.stripe_customer_id,
  u.has_used_trial,
  u.trial_ends_at
FROM users u
WHERE u.created_at >= NOW() - INTERVAL '7 days'
  AND u.has_used_trial = FALSE
  AND (u.trial_ends_at IS NULL OR u.trial_ends_at <= NOW())
ORDER BY u.created_at DESC;
```

## Email Sequence
Use the user first name if available; otherwise keep it simple and direct.

### Day 0
Subject: Quick help getting your first playbook live

Body:
Can I help you get your first playbook live in 5 minutes?
If useful, I can send a fast setup path for your use case.

### Day 1
Subject: One concrete use case for ACE

Body:
Most teams start by capturing one repeated workflow and evolving it from outcomes.
If you want, I can suggest the first playbook structure and share a direct trial link.

### Day 3
Subject: Quick feedback?

Body:
What almost stopped you from starting the trial?
One sentence is enough and helps me improve onboarding.

## Tracking
Track per-contact status in a sheet:
- `email`
- `day0_sent_at`
- `day1_sent_at`
- `day3_sent_at`
- `replied` (yes/no)
- `trial_started` (yes/no)
- `notes`
