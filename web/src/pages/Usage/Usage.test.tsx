import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { Usage } from './Usage';

const { mockGetSummary, mockGetDaily, mockGetByPlaybook, mockGetEntitlements, mockAuthState } =
  vi.hoisted(() => {
    const mockAuthState: {
      user: {
        subscription_status: 'active' | 'past_due' | 'canceled' | 'unpaid' | 'none';
        subscription_tier: string | null;
        trial_ends_at?: string | null;
        has_payment_method?: boolean;
        email_verified?: boolean;
      } | null;
      isLoading: boolean;
    } = {
      user: {
        subscription_status: 'active',
        subscription_tier: 'starter',
        trial_ends_at: null,
        has_payment_method: true,
        email_verified: true,
      },
      isLoading: false,
    };

    return {
      mockGetSummary: vi.fn(),
      mockGetDaily: vi.fn(),
      mockGetByPlaybook: vi.fn(),
      mockGetEntitlements: vi.fn(),
      mockAuthState,
    };
  });

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthState,
}));

vi.mock('../../utils/api', () => ({
  workspacesApi: {
    getPersonalEntitlements: mockGetEntitlements,
  },
  usageApi: {
    getSummary: mockGetSummary,
    getDaily: mockGetDaily,
    getByPlaybook: mockGetByPlaybook,
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

describe('Usage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthState.user = {
      subscription_status: 'active',
      subscription_tier: 'starter',
      trial_ends_at: null,
      has_payment_method: true,
      email_verified: true,
    };
    mockAuthState.isLoading = false;

    mockGetSummary.mockResolvedValue({
      start_date: '2026-01-01T00:00:00Z',
      end_date: '2026-02-01T00:00:00Z',
      total_requests: 0,
      total_prompt_tokens: 0,
      total_completion_tokens: 0,
      total_tokens: 0,
      total_cost_usd: '0.00',
    });
    mockGetDaily.mockResolvedValue([]);
    mockGetByPlaybook.mockResolvedValue([]);
    mockGetEntitlements.mockResolvedValue({
      workspace_id: 'me',
      plan: 'personal',
      deployment_mode: 'cloud',
      seat_limit: 1,
      enabled_features: ['cloud_sync', 'hosted_backups', 'managed_inference', 'hosted_evals'],
      access: {
        subscription_tier: 'starter',
        subscription_status: 'active',
        effective_tier: 'starter',
        has_feature_access: true,
        is_trialing: false,
      },
      entitlements: {
        cloud_sync: true,
        hosted_backups: true,
        managed_inference: true,
        hosted_evals: true,
        invite_members: false,
        shared_workspace: false,
        approvals: false,
        rbac: false,
        sso: false,
        audit_logs: false,
      },
      usage_limits: {
        monthly_evolution_runs: 100,
        current_evolution_runs: 12,
        remaining_evolution_runs: 88,
        monthly_cost_limit_usd: '9.00',
        current_cost_usd: '1.25',
        remaining_cost_usd: '7.75',
        current_total_tokens: 12000,
        max_playbooks: 5,
        storage_bytes: {
          current: 5242880,
          soft_limit: null,
          hard_limit: 104857600,
          remaining_soft: null,
          remaining_hard: 99614720,
          status: 'ok',
        },
        hosted_eval_runs: {
          current: 12,
          soft_limit: null,
          hard_limit: 100,
          remaining_soft: null,
          remaining_hard: 88,
          status: 'ok',
        },
        managed_inference_requests: {
          current: 24,
          soft_limit: null,
          hard_limit: null,
          remaining_soft: null,
          remaining_hard: null,
          status: 'ok',
        },
        managed_inference_tokens: {
          current: 12000,
          soft_limit: null,
          hard_limit: null,
          remaining_soft: null,
          remaining_hard: null,
          status: 'ok',
        },
        warning_fields: [],
        blocked_fields: [],
        is_within_limits: true,
        limit_exceeded: null,
      },
    });
  });

  it('shows hosted usage envelope and account summary cards for paid users', async () => {
    renderWithProviders(<Usage />);

    await waitFor(() => {
      expect(screen.getByText('Daily Managed Inference')).toBeInTheDocument();
    });

    expect(mockGetEntitlements).toHaveBeenCalled();
    expect(mockGetSummary).toHaveBeenCalled();
    expect(mockGetDaily).toHaveBeenCalled();
    expect(mockGetByPlaybook).toHaveBeenCalled();
    expect(screen.getByText('Current Plan')).toBeInTheDocument();
    expect(screen.getByText('Hosted Storage')).toBeInTheDocument();
    expect(screen.getByText('Hosted Evals')).toBeInTheDocument();
    expect(screen.getByText('Managed Inference')).toBeInTheDocument();
  });

  it('shows subscription state and account readiness for unpaid users', async () => {
    mockAuthState.user = {
      subscription_status: 'none',
      subscription_tier: null,
      trial_ends_at: null,
      has_payment_method: false,
      email_verified: false,
    };

    renderWithProviders(<Usage />);

    await waitFor(() => {
      expect(screen.getByText('Start Your Free Trial')).toBeInTheDocument();
    });

    expect(screen.getByText('Account Readiness')).toBeInTheDocument();
    expect(screen.queryByText("Couldn't Load Usage")).not.toBeInTheDocument();
    expect(mockGetSummary).not.toHaveBeenCalled();
  });
});
