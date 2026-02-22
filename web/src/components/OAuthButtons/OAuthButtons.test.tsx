import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { OAuthButtons } from './OAuthButtons';

const mocks = vi.hoisted(() => ({
  apiGet: vi.fn(),
  getCsrfToken: vi.fn(),
  getOAuthLoginUrl: vi.fn(),
  trackEvent: vi.fn(),
}));

vi.mock('../../utils/api', () => ({
  api: {
    get: mocks.apiGet,
  },
  authApi: {
    getOAuthCsrfToken: mocks.getCsrfToken,
    getOAuthLoginUrl: mocks.getOAuthLoginUrl,
  },
}));

vi.mock('../../lib/attribution', () => ({
  getAttributionSnapshot: () => ({
    src: 'x',
    utm_campaign: 'launch',
  }),
  buildAttributionQueryParams: () => new URLSearchParams([['src', 'x'], ['utm_campaign', 'launch']]),
}));

vi.mock('../../lib/anonymousId', () => ({
  getAnonymousId: () => 'anon_test_123',
}));

vi.mock('../../lib/experiments', () => ({
  getTrialDisclosureVariant: () => 'control',
}));

vi.mock('../../lib/analytics', () => ({
  trackAcquisitionEvent: mocks.trackEvent,
}));

describe('OAuthButtons', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.apiGet.mockResolvedValue({ data: { google: true, github: true } });
    mocks.getCsrfToken.mockResolvedValue('csrf_123');
    mocks.getOAuthLoginUrl.mockReturnValue('https://example.com/oauth/google/login');
    Object.defineProperty(window.navigator, 'userAgent', {
      configurable: true,
      value: 'Mozilla/5.0',
    });
  });

  it('shows X in-app browser hint when user agent matches', async () => {
    Object.defineProperty(window.navigator, 'userAgent', {
      configurable: true,
      value: 'Twitter for iPhone',
    });

    render(<OAuthButtons />);

    expect(await screen.findByText(/open this page in your browser/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /open in browser/i })).toBeInTheDocument();
  });

  it('appends attribution and experiment params to OAuth login URL', async () => {
    const user = userEvent.setup();
    render(<OAuthButtons />);

    await user.click(await screen.findByRole('button', { name: /continue with google/i }));

    await waitFor(() => {
      expect(mocks.getCsrfToken).toHaveBeenCalledTimes(1);
      expect(mocks.getOAuthLoginUrl).toHaveBeenCalledWith(
        'google',
        'csrf_123',
        expect.objectContaining({
          src: 'x',
          utm_campaign: 'launch',
          anonymous_id: 'anon_test_123',
          experiment_variant: 'control',
          exp_trial_disclosure: 'control',
        }),
      );
    });
  });
});
