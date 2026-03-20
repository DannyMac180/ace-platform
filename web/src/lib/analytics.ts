import type { AnalyticsEventPayload, AcquisitionEventType, AttributionSnapshot } from '../types';
import { getAnonymousId } from './anonymousId';
import { getAttributionSnapshot } from './attribution';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';
const FLUSH_INTERVAL_MS = 1500;
const MAX_BATCH_SIZE = 10;

let queue: AnalyticsEventPayload[] = [];
let flushTimer: number | null = null;
let lifecycleHooksRegistered = false;

interface RetentionTrackingInput {
  userId: string;
  createdAt: string;
  path: string;
  subscriptionStatus: string;
  subscriptionTier: string | null;
  hasUsedTrial: boolean;
  trialEndsAt: string | null;
}

function getExperimentVariant(attribution: AttributionSnapshot): string | undefined {
  return attribution.exp_trial_disclosure ?? attribution.experiment_variant;
}

function buildEventPayload(
  eventType: AcquisitionEventType,
  eventData?: Record<string, unknown>,
  overrides?: Partial<AnalyticsEventPayload>,
): AnalyticsEventPayload {
  const attribution = getAttributionSnapshot();
  const anonymousId = overrides?.anonymous_id ?? getAnonymousId() ?? attribution.anonymous_id;

  return {
    event_type: eventType,
    event_id: overrides?.event_id,
    anonymous_id: anonymousId ?? undefined,
    source: overrides?.source ?? attribution.source ?? attribution.src,
    channel: overrides?.channel ?? attribution.channel,
    campaign: overrides?.campaign ?? attribution.campaign ?? attribution.utm_campaign,
    experiment_variant: overrides?.experiment_variant ?? getExperimentVariant(attribution),
    attribution,
    event_data: eventData,
  };
}

function registerLifecycleHooks(): void {
  if (lifecycleHooksRegistered || typeof window === 'undefined') {
    return;
  }

  const flushOnHide = () => {
    void flushAnalyticsEvents();
  };

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      flushOnHide();
    }
  });

  window.addEventListener('beforeunload', flushOnHide);
  lifecycleHooksRegistered = true;
}

async function sendEvent(payload: AnalyticsEventPayload): Promise<void> {
  const token = localStorage.getItem('access_token');
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}/analytics/events`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
    keepalive: true,
    credentials: 'include',
  });

  if (!response.ok) {
    throw new Error(`Analytics event rejected (${response.status})`);
  }
}

function scheduleFlush(): void {
  if (flushTimer !== null) {
    return;
  }

  flushTimer = window.setTimeout(() => {
    flushTimer = null;
    void flushAnalyticsEvents();
  }, FLUSH_INTERVAL_MS);
}

export async function flushAnalyticsEvents(): Promise<void> {
  if (queue.length === 0) {
    return;
  }

  const batch = queue.slice(0, MAX_BATCH_SIZE);
  queue = queue.slice(MAX_BATCH_SIZE);

  await Promise.all(
    batch.map(async (eventPayload) => {
      try {
        await sendEvent(eventPayload);
      } catch {
        // Drop failures silently; analytics should not block UX.
      }
    }),
  );

  if (queue.length > 0) {
    scheduleFlush();
  }
}

export function trackAcquisitionEvent(
  eventType: AcquisitionEventType,
  eventData?: Record<string, unknown>,
  overrides?: Partial<AnalyticsEventPayload>,
): AnalyticsEventPayload {
  registerLifecycleHooks();

  const payload = buildEventPayload(eventType, eventData, overrides);
  queue.push(payload);

  if (queue.length >= MAX_BATCH_SIZE) {
    void flushAnalyticsEvents();
  } else {
    scheduleFlush();
  }

  return payload;
}

function retentionStorageKey(userId: string, dayKey: string): string {
  return `ace_retention_active_${userId}_${dayKey}`;
}

function currentDayKey(now = new Date()): string {
  return now.toISOString().slice(0, 10);
}

function accountAgeDays(createdAt: string, now = new Date()): number {
  const createdAtMs = Date.parse(createdAt);
  if (Number.isNaN(createdAtMs)) {
    return 0;
  }

  return Math.max(0, Math.floor((now.getTime() - createdAtMs) / 86_400_000));
}

export function trackAuthenticatedRetention(
  input: RetentionTrackingInput,
  now = new Date(),
): AnalyticsEventPayload | null {
  if (typeof window === 'undefined') {
    return null;
  }

  const dayKey = currentDayKey(now);
  const storageKey = retentionStorageKey(input.userId, dayKey);
  if (window.localStorage.getItem(storageKey)) {
    return null;
  }

  const payload = trackAcquisitionEvent('retention_active', {
    path: input.path,
    account_age_days: accountAgeDays(input.createdAt, now),
    subscription_status: input.subscriptionStatus,
    subscription_tier: input.subscriptionTier,
    has_used_trial: input.hasUsedTrial,
    has_active_trial: Boolean(input.trialEndsAt && Date.parse(input.trialEndsAt) > now.getTime()),
  });

  window.localStorage.setItem(storageKey, '1');
  return payload;
}
