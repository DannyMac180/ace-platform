import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { XLandingPage } from './XLandingPage';

const mocks = vi.hoisted(() => ({
  trackEvent: vi.fn(),
}));

vi.mock('../../lib/attribution', () => ({
  appendAttributionParams: (url: string) => `${url}?src=x&utm_campaign=launch`,
}));

vi.mock('../../lib/analytics', () => ({
  trackAcquisitionEvent: mocks.trackEvent,
}));

describe('XLandingPage', () => {
  it('renders mobile-focused structure and sticky CTA', async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <XLandingPage />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('heading', {
        name: /your ai workflow should improve after every task/i,
      }),
    ).toBeInTheDocument();

    const cta = screen.getByRole('link', { name: /start free trial/i });
    expect(cta).toHaveAttribute('href', '/register?src=x&utm_campaign=launch');

    await user.click(cta);
    expect(mocks.trackEvent).toHaveBeenCalledWith(
      'register_start',
      expect.objectContaining({ source: 'x_landing_sticky_cta' }),
    );
  });
});
