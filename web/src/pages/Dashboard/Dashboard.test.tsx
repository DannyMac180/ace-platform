import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { Dashboard } from './Dashboard';

const { mockListPlaybooks, mockCreatePlaybook, mockStartStarterTrial, mockAuthState } = vi.hoisted(() => {
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
    mockAuthState,
  };
});

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthState,
}));

vi.mock('../../utils/api', () => ({
  playbooksApi: {
    list: mockListPlaybooks,
    create: mockCreatePlaybook,
  },
  billingApi: {
    startStarterTrial: mockStartStarterTrial,
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
