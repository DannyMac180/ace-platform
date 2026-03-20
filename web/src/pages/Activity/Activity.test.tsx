import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { Activity } from './Activity';

const { mockGetSummary, mockGetDaily, mockGetByPlaybook, mockGetRecent, mockAuthState } =
  vi.hoisted(() => {
    const mockAuthState: {
      user: {
        subscription_status: 'active' | 'past_due' | 'canceled' | 'unpaid' | 'none';
        subscription_tier: string | null;
      } | null;
      isLoading: boolean;
    } = {
      user: {
        subscription_status: 'active',
        subscription_tier: 'starter',
      },
      isLoading: false,
    };

    return {
      mockGetSummary: vi.fn(),
      mockGetDaily: vi.fn(),
      mockGetByPlaybook: vi.fn(),
      mockGetRecent: vi.fn(),
      mockAuthState,
    };
  });

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthState,
}));

vi.mock('../../utils/api', () => ({
  evolutionsApi: {
    getSummary: mockGetSummary,
    getDaily: mockGetDaily,
    getByPlaybook: mockGetByPlaybook,
    getRecent: mockGetRecent,
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

describe('Activity', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthState.user = {
      subscription_status: 'active',
      subscription_tier: 'starter',
    };
    mockAuthState.isLoading = false;

    mockGetSummary.mockResolvedValue({
      start_date: '2026-01-01T00:00:00Z',
      end_date: '2026-02-01T00:00:00Z',
      total_evolutions: 0,
      completed_evolutions: 0,
      failed_evolutions: 0,
      running_evolutions: 0,
      queued_evolutions: 0,
      success_rate: 0,
      total_outcomes_processed: 0,
    });
    mockGetDaily.mockResolvedValue([]);
    mockGetByPlaybook.mockResolvedValue([]);
    mockGetRecent.mockResolvedValue([]);
  });

  it('shows the empty activity state for paid users with no evolution data', async () => {
    renderWithProviders(<Activity />);

    await waitFor(() => {
      expect(screen.getByText('No Evolution Runs Yet')).toBeInTheDocument();
    });

    expect(mockGetSummary).toHaveBeenCalled();
    expect(mockGetDaily).toHaveBeenCalled();
    expect(mockGetByPlaybook).toHaveBeenCalled();
    expect(mockGetRecent).toHaveBeenCalled();
  });

  it('shows subscription state for unpaid users', async () => {
    mockAuthState.user = {
      subscription_status: 'none',
      subscription_tier: null,
    };

    renderWithProviders(<Activity />);

    await waitFor(() => {
      expect(screen.getByText('Start Your Free Trial')).toBeInTheDocument();
    });

    expect(screen.queryByText("Couldn't Load Activity")).not.toBeInTheDocument();
    expect(mockGetSummary).not.toHaveBeenCalled();
  });
});
