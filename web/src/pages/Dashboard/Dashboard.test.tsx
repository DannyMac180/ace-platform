import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { Dashboard } from './Dashboard';

const {
  mockListPlaybooks,
  mockCreatePlaybook,
  mockStartStarterTrial,
  mockListWorkspaces,
  mockGetEntitlements,
  mockListSharedPlaybooks,
  mockReuseSharedPlaybook,
  mockNavigate,
  mockAuthState,
} = vi.hoisted(() => {
  const mockAuthState: {
    user: {
      subscription_status: 'active' | 'past_due' | 'canceled' | 'unpaid' | 'none';
      subscription_tier: string | null;
      has_used_trial: boolean;
    } | null;
    isAuthenticated: boolean;
    isLoading: boolean;
  } = {
    user: {
      subscription_status: 'active',
      subscription_tier: 'starter',
      has_used_trial: false,
    },
    isAuthenticated: true,
    isLoading: false,
  };

  return {
    mockListPlaybooks: vi.fn(),
    mockCreatePlaybook: vi.fn(),
    mockStartStarterTrial: vi.fn(),
    mockListWorkspaces: vi.fn(),
    mockGetEntitlements: vi.fn(),
    mockListSharedPlaybooks: vi.fn(),
    mockReuseSharedPlaybook: vi.fn(),
    mockNavigate: vi.fn(),
    mockAuthState,
  };
});

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthState,
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('../../utils/api', () => ({
  playbooksApi: {
    list: mockListPlaybooks,
    create: mockCreatePlaybook,
  },
  billingApi: {
    startStarterTrial: mockStartStarterTrial,
  },
  workspacesApi: {
    list: mockListWorkspaces,
    getEntitlements: mockGetEntitlements,
    listSharedPlaybooks: mockListSharedPlaybooks,
    reuseSharedPlaybook: mockReuseSharedPlaybook,
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

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthState.user = {
      subscription_status: 'active',
      subscription_tier: 'starter',
      has_used_trial: false,
    };
    mockAuthState.isAuthenticated = true;
    mockAuthState.isLoading = false;

    mockListPlaybooks.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 50,
      total_pages: 0,
    });
    mockListWorkspaces.mockResolvedValue([
      {
        id: 'workspace-personal',
        name: 'Personal Workspace',
        plan: 'personal',
        deployment_mode: 'cloud',
        seat_limit: 1,
        member_count: 1,
        current_user_role: 'owner',
        inference_config: {
          mode: 'managed_provider',
          provider: 'openai',
          available_modes: ['managed_provider'],
        },
      },
    ]);
    mockGetEntitlements.mockResolvedValue({
      workspace_id: 'workspace-personal',
      plan: 'personal',
      deployment_mode: 'cloud',
      seat_limit: 1,
      enabled_features: [],
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
        current_evolution_runs: 0,
        remaining_evolution_runs: 100,
        monthly_cost_limit_usd: null,
        current_cost_usd: 0,
        remaining_cost_usd: null,
        current_total_tokens: 0,
        max_playbooks: 5,
        is_within_limits: true,
        limit_exceeded: null,
      },
    });
    mockListSharedPlaybooks.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 24,
      total_pages: 0,
    });
    mockReuseSharedPlaybook.mockResolvedValue({
      id: 'copied-playbook',
      name: 'Copied',
      description: null,
      status: 'active',
      source: 'imported',
      created_at: '2026-03-18T12:00:00Z',
      updated_at: '2026-03-18T12:00:00Z',
      current_version: null,
    });
    mockStartStarterTrial.mockResolvedValue({
      success: false,
      message: 'Checkout session could not be created',
      checkout_url: null,
      subscription: null,
    });
  });

  it('shows the empty state for paid users with no playbooks', async () => {
    renderWithProviders(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText('No playbooks yet')).toBeInTheDocument();
    });

    expect(mockListPlaybooks).toHaveBeenCalled();
  });

  it('shows the shared registry for team workspaces and can reuse a playbook', async () => {
    const user = userEvent.setup();
    mockListWorkspaces.mockResolvedValue([
      {
        id: 'workspace-team',
        name: 'Team Alpha',
        plan: 'team',
        deployment_mode: 'cloud',
        seat_limit: 5,
        member_count: 3,
        current_user_role: 'member',
        inference_config: {
          mode: 'managed_provider',
          provider: 'openai',
          available_modes: ['managed_provider'],
        },
      },
    ]);
    mockGetEntitlements.mockResolvedValue({
      workspace_id: 'workspace-team',
      plan: 'team',
      deployment_mode: 'cloud',
      seat_limit: 5,
      enabled_features: ['shared_workspace'],
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
        invite_members: true,
        shared_workspace: true,
        approvals: true,
        rbac: false,
        sso: false,
        audit_logs: false,
      },
      usage_limits: {
        monthly_evolution_runs: 100,
        current_evolution_runs: 0,
        remaining_evolution_runs: 100,
        monthly_cost_limit_usd: null,
        current_cost_usd: 0,
        remaining_cost_usd: null,
        current_total_tokens: 0,
        max_playbooks: 5,
        is_within_limits: true,
        limit_exceeded: null,
      },
    });
    mockListSharedPlaybooks.mockResolvedValue({
      items: [
        {
          id: 'shared-1',
          name: 'Incident Triage',
          description: 'Triage critical production issues.',
          status: 'active',
          source: 'user_created',
          created_at: '2026-03-18T12:00:00Z',
          updated_at: '2026-03-18T12:00:00Z',
          version_count: 3,
          outcome_count: 9,
          owner: {
            user_id: 'owner-1',
            email: 'owner@example.com',
          },
          is_owned_by_current_user: false,
        },
      ],
      total: 1,
      page: 1,
      page_size: 24,
      total_pages: 1,
    });

    renderWithProviders(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText('Incident Triage')).toBeInTheDocument();
    });

    expect(screen.getByText('Approved team playbooks')).toBeInTheDocument();
    expect(screen.getByText('owner@example.com')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Reuse' }));

    await waitFor(() => {
      expect(mockReuseSharedPlaybook).toHaveBeenCalledWith('workspace-team', 'shared-1');
    });
  });

  it('shows a subscription state instead of a load error for unpaid users', async () => {
    mockAuthState.user = {
      subscription_status: 'none',
      subscription_tier: null,
      has_used_trial: false,
    };

    renderWithProviders(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText('Start Your Free Trial')).toBeInTheDocument();
    });

    expect(screen.queryByText('Failed to load playbooks')).not.toBeInTheDocument();
    expect(mockListPlaybooks).not.toHaveBeenCalled();
  });

  it('starts trial checkout directly from the subscription state CTA', async () => {
    const user = userEvent.setup();
    mockAuthState.user = {
      subscription_status: 'none',
      subscription_tier: null,
      has_used_trial: false,
    };

    renderWithProviders(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Start Free Trial' })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'Start Free Trial' }));

    await waitFor(() => {
      expect(mockStartStarterTrial).toHaveBeenCalledTimes(1);
    });
  });

  it('shows an error when trial checkout initiation fails', async () => {
    const user = userEvent.setup();
    mockAuthState.user = {
      subscription_status: 'none',
      subscription_tier: null,
      has_used_trial: false,
    };
    mockStartStarterTrial.mockRejectedValue(new Error('network'));

    renderWithProviders(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Start Free Trial' })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: 'Start Free Trial' }));

    await waitFor(() => {
      expect(screen.getByText('Failed to start your trial. Please try again.')).toBeInTheDocument();
    });
  });
});
