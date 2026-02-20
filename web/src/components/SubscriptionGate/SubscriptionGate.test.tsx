import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { SubscriptionGate } from './SubscriptionGate';

const { mockStartStarterTrial, mockAuthState } = vi.hoisted(() => {
  const mockAuthState: {
    user: {
      subscription_status: 'active' | 'past_due' | 'canceled' | 'unpaid' | 'none';
      subscription_tier: string | null;
      has_used_trial: boolean;
    } | null;
  } = {
    user: {
      subscription_status: 'none',
      subscription_tier: null,
      has_used_trial: false,
    },
  };

  return {
    mockStartStarterTrial: vi.fn(),
    mockAuthState,
  };
});

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthState,
}));

vi.mock('../../utils/api', () => ({
  billingApi: {
    startStarterTrial: mockStartStarterTrial,
  },
}));

describe('SubscriptionGate', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthState.user = {
      subscription_status: 'none',
      subscription_tier: null,
      has_used_trial: false,
    };
    mockStartStarterTrial.mockResolvedValue({
      success: false,
      message: 'Checkout session could not be created',
      checkout_url: null,
      subscription: null,
    });
  });

  it('shows card-required and trial-limit messaging in the modal', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <SubscriptionGate featureName="Playbooks">
          <button type="button">Open gated action</button>
        </SubscriptionGate>
      </MemoryRouter>
    );

    await user.click(screen.getByRole('button', { name: 'Open gated action' }));

    expect(screen.getByText('Start Your Free Trial')).toBeInTheDocument();
    expect(
      screen.getByText(/Card required, no charge today/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/includes 1 playbook and 5 evolutions/i)
    ).toBeInTheDocument();
  });

  it('initiates trial checkout when the primary CTA is clicked', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <SubscriptionGate featureName="Playbooks">
          <button type="button">Open gated action</button>
        </SubscriptionGate>
      </MemoryRouter>
    );

    await user.click(screen.getByRole('button', { name: 'Open gated action' }));
    await user.click(screen.getByRole('button', { name: 'Start Free Trial' }));

    await waitFor(() => {
      expect(mockStartStarterTrial).toHaveBeenCalledTimes(1);
    });
  });
});
