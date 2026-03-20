import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import App from './App';

vi.mock('./contexts/AuthContext', () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: () => ({
    isAuthenticated: true,
    isLoading: false,
    user: {
      email: 'test@example.com',
      subscription_status: 'none',
      subscription_tier: null,
      trial_ends_at: null,
      has_used_trial: false,
      email_verified: true,
    },
    logout: vi.fn(),
    refreshUser: vi.fn(),
  }),
}));

describe('App routing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('routes the authenticated dashboard entry point to activity', async () => {
    window.history.pushState({}, '', '/dashboard');
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Activity' })).toBeInTheDocument();
  });
});
