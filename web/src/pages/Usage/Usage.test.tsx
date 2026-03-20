import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { Usage } from './Usage';

const {
  mockGetEntitlements,
  mockGetSummary,
  mockGetDaily,
  mockGetByPlaybook,
  mockUpgradePersonalToTeam,
  mockAuthState,
} = vi.hoisted(() => {
  const mockAuthState: {
    user: {
      subscription_status: 'active' | 'trialing' | 'past_due' | 'canceled' | 'unpaid' | 'none';
      subscription_tier: string | null;
      trial_ends_at?: string | null;
      has_payment_method?: boolean;
      email_verified?: boolean;
      has_used_trial?: boolean;
    } | null;
    isLoading: boolean;
  } = {
    user: {
      subscription_status: 'active',
      subscription_tier: 'starter',
      trial_ends_at: null,
      has_payment_method: true,
      email_verified: true,
      has_used_trial: false,
    },
    isLoading: false,
  };

  return {
    mockGetEntitlements: vi.fn(),
    mockGetSummary: vi.fn(),
    mockGetDaily: vi.fn(),
    mockGetByPlaybook: vi.fn(),
    mockUpgradePersonalToTeam: vi.fn(),
    mockAuthState,
  };
});

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthState,
}));

vi.mock('../../utils/api', () => ({
  workspacesApi: {
    getEntitlements: mockGetEntitlements,
    upgradePersonalToTeam: mockUpgradePersonalToTeam,
  },
  evolutionsApi: {
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

function buildEntitlements(overrides: Record<string, unknown> = {}) {
  const base = {
    workspace_id: 'me',
    plan: 'personal',
    deployment_mode: 'cloud',
    seat_limit: 1,
    enabled_features: ['cloud_sync', 'managed_inference', 'hosted_evals', 'hosted_backups'],
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
      current_evolution_runs: 24,
      remaining_evolution_runs: 76,
      monthly_cost_limit_usd: '9.00',
      current_cost_usd: '2.40',
      remaining_cost_usd: '6.60',
      current_total_tokens: 4000,
      max_playbooks: 5,
      storage_bytes: {
        current: 2048,
        soft_limit: 1024,
        hard_limit: 4096,
        remaining_soft: 0,
        remaining_hard: 2048,
        status: 'warning',
      },
      hosted_eval_runs: {
        current: 24,
        soft_limit: 80,
        hard_limit: 100,
        remaining_soft: 56,
        remaining_hard: 76,
        status: 'ok',
      },
      managed_inference_requests: {
        current: 18,
        soft_limit: 40,
        hard_limit: 100,
        remaining_soft: 22,
        remaining_hard: 82,
        status: 'ok',
      },
      managed_inference_tokens: {
        current: 4000,
        soft_limit: 10000,
        hard_limit: 20000,
        remaining_soft: 6000,
        remaining_hard: 16000,
        status: 'ok',
      },
      warning_fields: ['storage_bytes'],
      blocked_fields: [],
      is_within_limits: true,
      limit_exceeded: null,
    },
  };

  return {
    ...base,
    ...overrides,
    access: {
      ...base.access,
      ...((overrides.access as Record<string, unknown> | undefined) ?? {}),
    },
    entitlements: {
      ...base.entitlements,
      ...((overrides.entitlements as Record<string, unknown> | undefined) ?? {}),
    },
    usage_limits: {
      ...base.usage_limits,
      ...((overrides.usage_limits as Record<string, unknown> | undefined) ?? {}),
    },
  };
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
      has_used_trial: false,
    };
    mockAuthState.isLoading = false;

    mockGetEntitlements.mockResolvedValue(buildEntitlements());
    mockGetSummary.mockResolvedValue({
      start_date: '2026-03-01T00:00:00Z',
      end_date: '2026-03-31T00:00:00Z',
      total_evolutions: 24,
      completed_evolutions: 20,
      failed_evolutions: 4,
      running_evolutions: 0,
      queued_evolutions: 0,
      success_rate: 0.83,
      total_outcomes_processed: 67,
    });
    mockGetDaily.mockResolvedValue([
      {
        date: '2026-03-10T00:00:00Z',
        total_evolutions: 2,
        completed: 2,
        failed: 0,
        running: 0,
        queued: 0,
      },
    ]);
    mockGetByPlaybook.mockResolvedValue([
      {
        playbook_id: 'playbook-1',
        playbook_name: 'Customer Support',
        total_evolutions: 12,
        completed: 10,
        failed: 2,
        success_rate: 0.83,
        last_evolution_at: '2026-03-12T10:00:00Z',
      },
    ]);
    mockUpgradePersonalToTeam.mockResolvedValue({
      id: 'workspace-1',
      name: 'ACE Team',
      plan: 'team',
      deployment_mode: 'cloud',
      seat_limit: 5,
      inference_config: {
        mode: 'managed_provider',
        provider: 'openai',
        available_modes: ['byo_provider', 'managed_provider'],
      },
      member_count: 1,
      current_user_role: 'owner',
    });
  });

  it('shows plan allowance and upgrade messaging for free users without detailed activity', async () => {
    mockAuthState.user = {
      subscription_status: 'none',
      subscription_tier: null,
      trial_ends_at: null,
      has_payment_method: false,
      email_verified: false,
      has_used_trial: false,
    };

    mockGetEntitlements.mockResolvedValue(
      buildEntitlements({
        access: {
          subscription_tier: 'free',
          subscription_status: 'none',
          effective_tier: 'free',
          has_feature_access: false,
          is_trialing: false,
        },
        enabled_features: [],
        entitlements: {
          cloud_sync: false,
          hosted_backups: false,
          managed_inference: false,
          hosted_evals: false,
          invite_members: false,
          shared_workspace: false,
          approvals: false,
          rbac: false,
          sso: false,
          audit_logs: false,
        },
        usage_limits: {
          monthly_evolution_runs: 5,
          current_evolution_runs: 0,
          remaining_evolution_runs: 5,
          monthly_cost_limit_usd: '1.00',
          current_cost_usd: '0.00',
          remaining_cost_usd: '1.00',
          current_total_tokens: 0,
          max_playbooks: 1,
          storage_bytes: {
            current: 0,
            soft_limit: null,
            hard_limit: 1024,
            remaining_soft: null,
            remaining_hard: 1024,
            status: 'ok',
          },
          hosted_eval_runs: {
            current: 0,
            soft_limit: null,
            hard_limit: 5,
            remaining_soft: null,
            remaining_hard: 5,
            status: 'ok',
          },
          managed_inference_requests: {
            current: 0,
            soft_limit: null,
            hard_limit: null,
            remaining_soft: null,
            remaining_hard: null,
            status: 'ok',
          },
          managed_inference_tokens: {
            current: 0,
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
      })
    );

    renderWithProviders(<Usage />);

    await waitFor(() => {
      expect(screen.getByText('Plan Access')).toBeInTheDocument();
    });

    expect(screen.getAllByText('Free').length).toBeGreaterThan(0);
    expect(screen.getByText('Included With This Plan')).toBeInTheDocument();
    expect(screen.getByText('5 / month')).toBeInTheDocument();
    expect(screen.getByText(/hosted usage is mapped/i)).toBeInTheDocument();
    expect(screen.getByText(/detailed hosted activity unlocks after upgrade/i)).toBeInTheDocument();
    expect(mockGetSummary).not.toHaveBeenCalled();
    expect(mockGetDaily).not.toHaveBeenCalled();
    expect(mockGetByPlaybook).not.toHaveBeenCalled();
  });

  it('shows the activity dashboard and warning state when a paid user is approaching a limit', async () => {
    mockGetEntitlements.mockResolvedValue(
      buildEntitlements({
        usage_limits: {
          monthly_evolution_runs: 100,
          current_evolution_runs: 92,
          remaining_evolution_runs: 8,
          monthly_cost_limit_usd: '9.00',
          current_cost_usd: '4.50',
          remaining_cost_usd: '4.50',
          current_total_tokens: 12345,
          max_playbooks: 5,
          hosted_eval_runs: {
            current: 92,
            soft_limit: 80,
            hard_limit: 100,
            remaining_soft: 0,
            remaining_hard: 8,
            status: 'warning',
          },
          warning_fields: ['hosted_eval_runs'],
          is_within_limits: true,
          limit_exceeded: null,
        },
      })
    );

    renderWithProviders(<Usage />);

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: 'Upgrade Before You Hit The Limit' })
      ).toBeInTheDocument();
    });

    expect(mockGetSummary).toHaveBeenCalled();
    expect(mockGetDaily).toHaveBeenCalled();
    expect(mockGetByPlaybook).toHaveBeenCalled();
    expect(screen.getByText('Hosted Storage')).toBeInTheDocument();
    expect(screen.getByText('Managed Requests')).toBeInTheDocument();
    expect(screen.getByText('Evolution Activity')).toBeInTheDocument();
    expect(screen.getByText('Most Active Playbooks')).toBeInTheDocument();
    expect(screen.getByText('Customer Support')).toBeInTheDocument();
    expect(screen.getAllByText('92 / 100').length).toBeGreaterThan(0);
  });

  it('shows an upgrade prompt when the evolution limit has been reached', async () => {
    mockAuthState.user = {
      subscription_status: 'active',
      subscription_tier: 'starter',
      trial_ends_at: null,
      has_payment_method: true,
      email_verified: true,
      has_used_trial: true,
    };

    mockGetEntitlements.mockResolvedValue(
      buildEntitlements({
        usage_limits: {
          monthly_evolution_runs: 100,
          current_evolution_runs: 100,
          remaining_evolution_runs: 0,
          monthly_cost_limit_usd: '9.00',
          current_cost_usd: '8.90',
          remaining_cost_usd: '0.10',
          current_total_tokens: 9999,
          max_playbooks: 5,
          hosted_eval_runs: {
            current: 100,
            soft_limit: 80,
            hard_limit: 100,
            remaining_soft: 0,
            remaining_hard: 0,
            status: 'blocked',
          },
          blocked_fields: ['hosted_eval_runs'],
          warning_fields: [],
          is_within_limits: false,
          limit_exceeded: 'monthly_evolution_runs',
        },
      })
    );

    renderWithProviders(<Usage />);

    await waitFor(() => {
      expect(screen.getByText(/monthly evolution limit reached/i)).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: 'Upgrade Plan' })).toBeInTheDocument();
    expect(screen.getByText(/hosted evals are blocked until the limit resets or the plan changes/i)).toBeInTheDocument();
    expect(screen.getByText('Hard limit reached')).toBeInTheDocument();
  });

  it('shows budget-specific limit messaging when the managed usage cap is reached', async () => {
    mockAuthState.user = {
      subscription_status: 'active',
      subscription_tier: 'starter',
      trial_ends_at: null,
      has_payment_method: true,
      email_verified: true,
      has_used_trial: true,
    };

    mockGetEntitlements.mockResolvedValue(
      buildEntitlements({
        usage_limits: {
          monthly_evolution_runs: 100,
          current_evolution_runs: 64,
          remaining_evolution_runs: 36,
          monthly_cost_limit_usd: '9.00',
          current_cost_usd: '9.00',
          remaining_cost_usd: '0.00',
          current_total_tokens: 16888,
          max_playbooks: 5,
          warning_fields: [],
          blocked_fields: ['monthly_cost_limit'],
          is_within_limits: false,
          limit_exceeded: 'monthly_cost_limit',
        },
      })
    );

    renderWithProviders(<Usage />);

    await waitFor(() => {
      expect(screen.getByText(/managed usage budget reached/i)).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: 'Upgrade Plan' })).toBeInTheDocument();
    expect(screen.getByText(/you have used \$9\.00 of \$9\.00/i)).toBeInTheDocument();
    expect(screen.getByText(/\$9\.00 managed budget/i)).toBeInTheDocument();
  });

  it('offers a personal-to-team workspace upgrade action', async () => {
    renderWithProviders(<Usage />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Upgrade Workspace To Team' })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Upgrade Workspace To Team' }));

    await waitFor(() => {
      expect(mockUpgradePersonalToTeam).toHaveBeenCalledTimes(1);
    });
  });
});
