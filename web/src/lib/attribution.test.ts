import { beforeEach, describe, expect, it } from 'vitest';
import {
  appendAttributionParams,
  captureAndPersistAttribution,
  getStoredAttribution,
} from './attribution';

describe('attribution', () => {
  beforeEach(() => {
    localStorage.clear();
    window.history.pushState({}, '', '/');
    Object.defineProperty(document, 'referrer', {
      configurable: true,
      value: '',
    });
  });

  it('captures and normalizes first-touch attribution', () => {
    window.history.pushState(
      {},
      '',
      '/x?src=twitter&utm_campaign=launch&utm_medium=social&aid=abc123',
    );
    Object.defineProperty(document, 'referrer', {
      configurable: true,
      value: 'https://t.co/ace',
    });

    const snapshot = captureAndPersistAttribution();

    expect(snapshot.source).toBe('x');
    expect(snapshot.channel).toBe('social');
    expect(snapshot.campaign).toBe('launch');
    expect(snapshot.aid).toBe('abc123');
    expect(snapshot.landing_path).toBe('/x');
    expect(snapshot.referrer_host).toBe('t.co');
    expect(snapshot.anonymous_id).toBeTruthy();
  });

  it('keeps first-touch values on subsequent captures', () => {
    window.history.pushState({}, '', '/x?src=twitter&utm_campaign=launch');
    const first = captureAndPersistAttribution();
    expect(first.source).toBe('x');

    window.history.pushState({}, '', '/register?src=linkedin&utm_campaign=new_campaign');
    const second = captureAndPersistAttribution();

    expect(second.source).toBe('x');
    expect(second.campaign).toBe('launch');
  });

  it('preserves attribution params when appending to links', () => {
    window.history.pushState({}, '', '/x?src=x&utm_campaign=launch&aid=alpha');
    captureAndPersistAttribution();

    const href = appendAttributionParams('/register');
    const url = new URL(href, window.location.origin);

    expect(url.pathname).toBe('/register');
    expect(url.searchParams.get('src')).toBe('x');
    expect(url.searchParams.get('utm_campaign')).toBe('launch');
    expect(url.searchParams.get('aid')).toBe('alpha');
    expect(getStoredAttribution()).not.toBeNull();
  });
});
