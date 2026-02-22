import { getAnonymousId } from './anonymousId';

export type TrialDisclosureVariant = 'control' | 'late_disclosure';

const STORAGE_KEY = 'ace_exp_trial_disclosure_variant';

function hashString(value: string): number {
  let hash = 5381;
  for (let index = 0; index < value.length; index += 1) {
    hash = ((hash << 5) + hash) ^ value.charCodeAt(index);
  }
  return Math.abs(hash);
}

function assignVariant(anonymousId: string | null): TrialDisclosureVariant {
  if (!anonymousId) {
    return 'control';
  }

  const bucket = hashString(anonymousId) % 100;
  return bucket < 50 ? 'control' : 'late_disclosure';
}

export function isTrialDisclosureExperimentEnabled(): boolean {
  return import.meta.env.VITE_EXPERIMENT_TRIAL_DISCLOSURE_ENABLED !== 'false';
}

export function getTrialDisclosureVariant(anonymousId: string | null = getAnonymousId()): TrialDisclosureVariant {
  if (!isTrialDisclosureExperimentEnabled()) {
    return 'control';
  }

  if (typeof window === 'undefined') {
    return assignVariant(anonymousId);
  }

  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (stored === 'control' || stored === 'late_disclosure') {
    return stored;
  }

  const assigned = assignVariant(anonymousId);
  window.localStorage.setItem(STORAGE_KEY, assigned);
  return assigned;
}

export function getTrialDisclosureExperimentLabel(): string {
  return `trial_disclosure_timing:${getTrialDisclosureVariant()}`;
}
