const ANONYMOUS_ID_KEY = 'ace_anonymous_id';

function generateAnonymousId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }

  const random = Math.random().toString(36).slice(2, 12);
  return `anon_${Date.now()}_${random}`;
}

export function getAnonymousId(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    const existing = window.localStorage.getItem(ANONYMOUS_ID_KEY);
    if (existing) {
      return existing;
    }

    const generated = generateAnonymousId();
    window.localStorage.setItem(ANONYMOUS_ID_KEY, generated);
    return generated;
  } catch {
    return null;
  }
}

export function clearAnonymousId(): void {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    window.localStorage.removeItem(ANONYMOUS_ID_KEY);
  } catch {
    // Ignore storage failures.
  }
}
