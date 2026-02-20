import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Pricing } from './Pricing';

const mocks = vi.hoisted(() => ({
  apiPost: vi.fn(),
}));

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      email: 'test@example.com',
      email_verified: true,
      subscription_tier: null,
      subscription_status: 'none',
      has_used_trial: false,
      trial_ends_at: null,
    },
  }),
}));

vi.mock('../../utils/api', () => ({
  api: {
    post: mocks.apiPost,
  },
}));

describe('Pricing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.apiPost.mockResolvedValue({
      data: {
        success: false,
        message: 'Checkout session could not be created',
        checkout_url: null,
        subscription: null,
      },
    });
  });

  it('toggles to yearly pricing with a 17% discount and sends yearly interval when subscribing', async () => {
    const user = userEvent.setup();
    render(<Pricing />);

    expect(screen.getByRole('button', { name: 'Subscribe - $29/mo' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /yearly/i }));

    expect(screen.getByRole('button', { name: 'Subscribe - $290/yr' })).toBeInTheDocument();
    expect(screen.getAllByText('17% off').length).toBeGreaterThan(0);
    expect(screen.getAllByText('/year').length).toBeGreaterThan(0);

    await user.click(screen.getByRole('button', { name: 'Subscribe - $290/yr' }));

    await waitFor(() => {
      expect(mocks.apiPost).toHaveBeenCalledWith('/billing/subscribe', {
        tier: 'pro',
        interval: 'year',
      });
    });
  });

  it('renders explicit trial disclosure and starter trial limits copy', () => {
    render(<Pricing />);

    expect(
      screen.getByText(/Starter trial is card-required/i)
    ).toBeInTheDocument();
    expect(screen.getAllByText(/Trial includes 1 playbook and 5 evolutions/i).length).toBeGreaterThan(0);
  });
});
