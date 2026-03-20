import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { AdminDashboard } from './AdminDashboard';

const {
  mockGetStats,
  mockGetOperationalHealth,
  mockGetSignups,
  mockGetFunnel,
  mockGetTopUsers,
  mockAuthState,
} = vi.hoisted(() => {
  const mockAuthState: {
    user: { is_admin: boolean } | null;
  } = {
    user: { is_admin: true },
  };

  return {
    mockGetStats: vi.fn(),
    mockGetOperationalHealth: vi.fn(),
    mockGetSignups: vi.fn(),
    mockGetFunnel: vi.fn(),
    mockGetTopUsers: vi.fn(),
    mockAuthState,
  };
});

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthState,
}));

vi.mock('../../utils/api', () => ({
  adminApi: {
    getStats: mockGetStats,
    getOperationalHealth: mockGetOperationalHealth,
    getSignups: mockGetSignups,
    getFunnel: mockGetFunnel,
    getTopUsers: mockGetTopUsers,
  },
}));

function renderWithProviders(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>{ui}</BrowserRouter>
    </QueryClientProvider>
  );
}

describe('AdminDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthState.user = { is_admin: true };

    mockGetStats.mockResolvedValue({
      total_users: 12,
      active_users_today: 5,
      signups_this_week: 2,
      total_cost_today: '3.42',
      tier_distribution: { free: 6, starter: 4, pro: 2 },
    });
    mockGetOperationalHealth.mockResolvedValue({
      generated_at: '2026-03-20T18:52:00Z',
      sync: {
        status: 'healthy',
        enabled_workspaces: 3,
        active_workspaces_24h: 2,
        sync_events_24h: 11,
        last_activity_at: '2026-03-20T18:40:00Z',
      },
      job_queue: {
        status: 'attention',
        queued_jobs: 2,
        running_jobs: 1,
        failed_jobs_24h: 0,
        jobs_observed_24h: 8,
        oldest_queued_at: '2026-03-20T18:45:00Z',
        last_completed_at: '2026-03-20T18:49:00Z',
      },
      inference_gateway: {
        status: 'idle',
        enabled_workspaces: 4,
        configured_providers: ['openai', 'anthropic'],
        requests_24h: 0,
        total_tokens_24h: 0,
        total_cost_usd_24h: '0',
        last_request_at: null,
      },
    });
    mockGetSignups.mockResolvedValue([{ date: '2026-03-20', count: 2 }]);
    mockGetFunnel.mockResolvedValue({
      days: 30,
      start_date: '2026-02-19T00:00:00Z',
      end_date: '2026-03-20T00:00:00Z',
      landing_views: 20,
      register_starts: 10,
      register_completes: 8,
      signups: 8,
      trial_checkout_intent: 4,
      trial_started: 3,
      first_playbook_created: 2,
      paid_active_non_trial: 1,
      conversion_landing_to_register_start_pct: 50,
      conversion_register_start_to_register_complete_pct: 80,
      conversion_landing_to_register_complete_pct: 40,
      conversion_signup_to_checkout_intent_pct: 50,
      conversion_checkout_intent_to_trial_started_pct: 75,
      conversion_trial_started_to_first_playbook_pct: 66.7,
      conversion_first_playbook_to_paid_active_non_trial_pct: 50,
      conversion_signup_to_trial_started_pct: 37.5,
      conversion_signup_to_paid_active_non_trial_pct: 12.5,
    });
    mockGetTopUsers.mockResolvedValue([]);
  });

  it('renders cloud rollout health panels for admin users', async () => {
    renderWithProviders(<AdminDashboard />);

    await waitFor(() => {
      expect(screen.getByText('Cloud Rollout Health')).toBeInTheDocument();
    });

    expect(screen.getByText('Sync health')).toBeInTheDocument();
    expect(screen.getByText('Job queue health')).toBeInTheDocument();
    expect(screen.getByText('Inference gateway health')).toBeInTheDocument();
    expect(screen.getByText('11')).toBeInTheDocument();
    expect(screen.getByText('Configured providers: openai, anthropic.')).toBeInTheDocument();
    expect(mockGetOperationalHealth).toHaveBeenCalled();
  });
});
