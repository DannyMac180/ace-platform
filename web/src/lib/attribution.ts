import type { AttributionSnapshot } from '../types';
import { getAnonymousId } from './anonymousId';

const FIRST_TOUCH_STORAGE_KEY = 'ace_attribution_first_touch';

const QUERY_KEYS = [
  'src',
  'source',
  'aid',
  'anonymous_id',
  'exp_trial_disclosure',
  'experiment_variant',
  'utm_source',
  'utm_medium',
  'utm_campaign',
  'utm_term',
  'utm_content',
] as const;

function normalizeSource(source: string | undefined, referrerHost: string | undefined): string | undefined {
  const raw = source ?? referrerHost;
  if (!raw) {
    return undefined;
  }

  const value = raw.toLowerCase();
  if (
    value === 'x' ||
    value === 'x.com' ||
    value === 'www.x.com' ||
    value === 'twitter' ||
    value === 'twitter.com' ||
    value === 'www.twitter.com' ||
    value === 'mobile.twitter.com' ||
    value === 't.co'
  ) {
    return 'x';
  }

  return value;
}

function normalizeReferrerHost(referrer: string): string | undefined {
  if (!referrer) {
    return undefined;
  }

  try {
    return new URL(referrer).hostname.toLowerCase();
  } catch {
    return undefined;
  }
}

function getDeviceType(): 'mobile' | 'desktop' {
  if (typeof window === 'undefined') {
    return 'desktop';
  }

  return window.matchMedia('(max-width: 900px)').matches ? 'mobile' : 'desktop';
}

function parseStoredSnapshot(raw: string | null): AttributionSnapshot | null {
  if (!raw) {
    return null;
  }

  try {
    const parsed = JSON.parse(raw) as AttributionSnapshot;
    if (parsed && typeof parsed === 'object') {
      return parsed;
    }
  } catch {
    // Ignore malformed JSON.
  }

  return null;
}

function mergeFirstTouch(
  existing: AttributionSnapshot | null,
  current: AttributionSnapshot,
): AttributionSnapshot {
  const merged: AttributionSnapshot = { ...(existing ?? {}) };

  for (const [key, value] of Object.entries(current)) {
    if (!value) {
      continue;
    }

    if (!(merged as Record<string, string | undefined>)[key]) {
      (merged as Record<string, string | undefined>)[key] = value;
    }
  }

  return merged;
}

export function buildCurrentAttributionSnapshot(): AttributionSnapshot {
  if (typeof window === 'undefined') {
    return {};
  }

  const params = new URLSearchParams(window.location.search);
  const snapshot: AttributionSnapshot = {
    landing_path: window.location.pathname,
    device_type: getDeviceType(),
  };

  for (const key of QUERY_KEYS) {
    const value = params.get(key);
    if (value) {
      snapshot[key] = value;
    }
  }

  const referrerHost = normalizeReferrerHost(document.referrer);
  if (referrerHost) {
    snapshot.referrer_host = referrerHost;
  }

  const sourceCandidate =
    snapshot.src ??
    snapshot.source ??
    snapshot.utm_source;

  const source = normalizeSource(sourceCandidate, snapshot.referrer_host);
  if (source) {
    snapshot.source = source;
    if (!snapshot.src) {
      snapshot.src = source;
    }
  }

  if (!snapshot.channel) {
    if (source === 'x') {
      snapshot.channel = 'social';
    } else if (snapshot.utm_medium) {
      snapshot.channel = snapshot.utm_medium;
    }
  }

  if (!snapshot.campaign) {
    snapshot.campaign = snapshot.utm_campaign;
  }

  if (!snapshot.anonymous_id) {
    const anonymousId = getAnonymousId();
    if (anonymousId) {
      snapshot.anonymous_id = anonymousId;
    }
  }

  return snapshot;
}

export function captureAndPersistAttribution(): AttributionSnapshot {
  if (typeof window === 'undefined') {
    return {};
  }

  const existing = parseStoredSnapshot(window.localStorage.getItem(FIRST_TOUCH_STORAGE_KEY));
  const current = buildCurrentAttributionSnapshot();
  const merged = mergeFirstTouch(existing, current);

  try {
    window.localStorage.setItem(FIRST_TOUCH_STORAGE_KEY, JSON.stringify(merged));
  } catch {
    // Ignore storage failures.
  }

  return merged;
}

export function getStoredAttribution(): AttributionSnapshot | null {
  if (typeof window === 'undefined') {
    return null;
  }

  return parseStoredSnapshot(window.localStorage.getItem(FIRST_TOUCH_STORAGE_KEY));
}

export function getAttributionSnapshot(): AttributionSnapshot {
  return getStoredAttribution() ?? captureAndPersistAttribution();
}

export function buildAttributionQueryParams(
  attribution: AttributionSnapshot | null,
): URLSearchParams {
  const params = new URLSearchParams();
  if (!attribution) {
    return params;
  }

  const keysToCarry: Array<keyof AttributionSnapshot> = [
    'src',
    'aid',
    'anonymous_id',
    'exp_trial_disclosure',
    'utm_source',
    'utm_medium',
    'utm_campaign',
    'utm_term',
    'utm_content',
  ];

  for (const key of keysToCarry) {
    const value = attribution[key];
    if (value) {
      params.set(key, value);
    }
  }

  return params;
}

export function appendAttributionParams(
  url: string,
  attribution: AttributionSnapshot | null = getStoredAttribution(),
): string {
  if (!attribution || typeof window === 'undefined') {
    return url;
  }

  const absoluteUrl = new URL(url, window.location.origin);
  const params = buildAttributionQueryParams(attribution);
  params.forEach((value, key) => {
    if (!absoluteUrl.searchParams.has(key)) {
      absoluteUrl.searchParams.set(key, value);
    }
  });

  if (url.startsWith('http')) {
    return absoluteUrl.toString();
  }

  return `${absoluteUrl.pathname}${absoluteUrl.search}${absoluteUrl.hash}`;
}

export function updateStoredAttribution(
  patch: Partial<AttributionSnapshot>,
): AttributionSnapshot | null {
  if (typeof window === 'undefined') {
    return null;
  }

  const current = getAttributionSnapshot();
  const merged: AttributionSnapshot = { ...current, ...patch };
  try {
    window.localStorage.setItem(FIRST_TOUCH_STORAGE_KEY, JSON.stringify(merged));
  } catch {
    // Ignore storage failures.
  }

  return merged;
}
