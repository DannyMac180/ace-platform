import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import { Settings } from './Settings';

const mocks = vi.hoisted(() => ({
  refreshUser: vi.fn(),
  logout: vi.fn(),
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  apiDelete: vi.fn(),
  setPassword: vi.fn(),
  changePassword: vi.fn(),
  listAuditLogs: vi.fn(),
  exportData: vi.fn(),
  deleteAccount: vi.fn(),
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
    refreshUser: mocks.refreshUser,
    logout: mocks.logout,
  }),
}));

vi.mock('../../utils/api', () => ({
  api: {
    get: mocks.apiGet,
    post: mocks.apiPost,
    delete: mocks.apiDelete,
  },
  authApi: {
    getOAuthCsrfToken: vi.fn(),
    setPassword: mocks.setPassword,
    changePassword: mocks.changePassword,
  },
  accountApi: {
    listAuditLogs: mocks.listAuditLogs,
    exportData: mocks.exportData,
    deleteAccount: mocks.deleteAccount,
  },
}));

function renderSettings() {
  return render(
    <BrowserRouter>
      <Settings />
    </BrowserRouter>
  );
}

describe('Settings', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mocks.apiGet.mockImplementation((url: string) => {
      if (url === '/auth/oauth/accounts') {
        return Promise.resolve({ data: { google: false, github: false, has_password: false } });
      }
      if (url === '/auth/oauth/providers') {
        return Promise.resolve({ data: { google: false, github: false } });
      }
      return Promise.reject(new Error('unknown url'));
    });

    mocks.listAuditLogs.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      total_pages: 1,
    });
  });

  it('sets a password via modal when account has no password', async () => {
    const user = userEvent.setup();
    mocks.setPassword.mockResolvedValue({ message: 'Password set' });

    renderSettings();

    const setButton = await screen.findByRole('button', { name: 'Set' });
    await user.click(setButton);

    expect(screen.getByRole('heading', { name: 'Set password' })).toBeInTheDocument();

    await user.type(screen.getByLabelText('New password'), 'newpassword123');
    await user.click(screen.getByRole('button', { name: 'Set password' }));

    await waitFor(() => {
      expect(mocks.setPassword).toHaveBeenCalledWith('newpassword123');
    });
  });

  it('requires typing DELETE before enabling account deletion', async () => {
    const user = userEvent.setup();
    mocks.deleteAccount.mockResolvedValue({ message: 'Account deleted' });

    renderSettings();

    const deleteButton = await screen.findByRole('button', { name: 'Delete' });
    await user.click(deleteButton);

    expect(screen.getByRole('heading', { name: 'Delete account' })).toBeInTheDocument();

    const confirmInput = screen.getByLabelText('Confirmation');
    const submit = screen.getByRole('button', { name: 'Delete account' });

    expect(submit).toBeDisabled();
    await user.type(confirmInput, 'DELETE');
    expect(submit).not.toBeDisabled();

    await user.click(submit);

    await waitFor(() => {
      expect(mocks.deleteAccount).toHaveBeenCalledWith('DELETE', undefined);
      expect(mocks.logout).toHaveBeenCalled();
    });
  });
});
