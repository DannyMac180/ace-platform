import { beforeEach, describe, expect, it } from 'vitest';
import { getTrialDisclosureVariant } from './experiments';

describe('experiments', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('assigns a deterministic variant per anonymous id', () => {
    const first = getTrialDisclosureVariant('anon_same_user');
    localStorage.clear();
    const second = getTrialDisclosureVariant('anon_same_user');

    expect(first).toBe(second);
    expect(['control', 'late_disclosure']).toContain(first);
  });

  it('persists assignment in localStorage', () => {
    const variant = getTrialDisclosureVariant('anon_for_storage');
    const stored = localStorage.getItem('ace_exp_trial_disclosure_variant');

    expect(stored).toBe(variant);
  });
});
