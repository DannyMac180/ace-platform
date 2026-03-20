import { beforeEach, describe, expect, it } from 'vitest';
import { trackAuthenticatedRetention } from './analytics';

describe('trackAuthenticatedRetention', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('emits one retention event per user per day', () => {
    const now = new Date('2026-03-20T12:00:00.000Z');
    const input = {
      userId: 'user_123',
      createdAt: '2026-03-15T12:00:00.000Z',
      path: '/activity',
      subscriptionStatus: 'active',
      subscriptionTier: 'starter',
      hasUsedTrial: true,
      trialEndsAt: '2026-03-25T12:00:00.000Z',
    };

    const firstPayload = trackAuthenticatedRetention(input, now);
    const secondPayload = trackAuthenticatedRetention(input, now);

    expect(firstPayload?.event_type).toBe('retention_active');
    expect(firstPayload?.event_data).toMatchObject({
      path: '/activity',
      account_age_days: 5,
      subscription_status: 'active',
      subscription_tier: 'starter',
      has_used_trial: true,
      has_active_trial: true,
    });
    expect(secondPayload).toBeNull();
  });

  it('allows a new event on the next day', () => {
    const input = {
      userId: 'user_123',
      createdAt: '2026-03-15T12:00:00.000Z',
      path: '/usage',
      subscriptionStatus: 'active',
      subscriptionTier: 'pro',
      hasUsedTrial: true,
      trialEndsAt: null,
    };

    const firstDayPayload = trackAuthenticatedRetention(
      input,
      new Date('2026-03-20T12:00:00.000Z'),
    );
    const nextDayPayload = trackAuthenticatedRetention(
      input,
      new Date('2026-03-21T12:00:00.000Z'),
    );

    expect(firstDayPayload?.event_type).toBe('retention_active');
    expect(nextDayPayload?.event_type).toBe('retention_active');
    expect(nextDayPayload?.event_data).toMatchObject({
      path: '/usage',
      account_age_days: 6,
      has_active_trial: false,
    });
  });
});
