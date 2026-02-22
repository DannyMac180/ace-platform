import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthPage } from './AuthPage';

const mocks = vi.hoisted(() => ({
  login: vi.fn(),
  register: vi.fn(),
  trackEvent: vi.fn(),
  trialVariant: 'control' as 'control' | 'late_disclosure',
}));

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    login: mocks.login,
    register: mocks.register,
  }),
}));

vi.mock('../../components/OAuthButtons/OAuthButtons', () => ({
  OAuthButtons: () => <div data-testid="oauth-buttons" />,
}));

vi.mock('../../lib/analytics', () => ({
  trackAcquisitionEvent: mocks.trackEvent,
}));

vi.mock('../../lib/attribution', () => ({
  appendAttributionParams: (url: string) => url,
  getAttributionSnapshot: () => ({ src: 'x' }),
}));

vi.mock('../../lib/anonymousId', () => ({
  getAnonymousId: () => 'anon_mobile_test',
}));

vi.mock('../../lib/experiments', () => ({
  getTrialDisclosureVariant: () => mocks.trialVariant,
}));

function renderRegisterPage() {
  return render(
    <MemoryRouter initialEntries={['/register']}>
      <Routes>
        <Route path="/register" element={<AuthPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('AuthPage mobile register flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.trialVariant = 'control';

    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: query.includes('max-width: 900px'),
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  it('supports two-step mobile registration', async () => {
    const user = userEvent.setup();
    mocks.register.mockResolvedValue(undefined);

    renderRegisterPage();

    expect(screen.getByText(/step 1 of 2/i)).toBeInTheDocument();

    await user.type(screen.getByLabelText(/email/i), 'mobile@example.com');
    await user.click(screen.getByRole('button', { name: /continue/i }));

    expect(screen.getByText(/step 2 of 2/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument();

    await user.type(screen.getByLabelText(/^password$/i), 'password123');
    await user.type(screen.getByLabelText(/confirm password/i), 'password123');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    await waitFor(() => {
      expect(mocks.register).toHaveBeenCalledWith(
        'mobile@example.com',
        'password123',
        expect.objectContaining({
          anonymous_id: 'anon_mobile_test',
          experiment_variant: 'control',
        }),
      );
    });
  });

  it('renders disclosure copy only for control variant on auth screen', () => {
    mocks.trialVariant = 'control';
    const { rerender } = renderRegisterPage();

    expect(screen.getByText(/7-day trial is card-required/i)).toBeInTheDocument();

    mocks.trialVariant = 'late_disclosure';
    rerender(
      <MemoryRouter initialEntries={['/register']}>
        <Routes>
          <Route path="/register" element={<AuthPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.queryByText(/7-day trial is card-required/i)).not.toBeInTheDocument();
  });
});
