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
  listWorkspaces: vi.fn(),
  listMemberships: vi.fn(),
  listInvitations: vi.fn(),
  listMyInvitations: vi.fn(),
  createInvitation: vi.fn(),
  deleteInvitation: vi.fn(),
  acceptInvitation: vi.fn(),
  removeMembership: vi.fn(),
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
  workspacesApi: {
    list: mocks.listWorkspaces,
    listMemberships: mocks.listMemberships,
    listInvitations: mocks.listInvitations,
    listMyInvitations: mocks.listMyInvitations,
    createInvitation: mocks.createInvitation,
    deleteInvitation: mocks.deleteInvitation,
    acceptInvitation: mocks.acceptInvitation,
    removeMembership: mocks.removeMembership,
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
    mocks.listWorkspaces.mockResolvedValue([]);
    mocks.listMemberships.mockResolvedValue([]);
    mocks.listInvitations.mockResolvedValue([]);
    mocks.listMyInvitations.mockResolvedValue([]);
    mocks.createInvitation.mockResolvedValue({});
    mocks.deleteInvitation.mockResolvedValue(undefined);
    mocks.acceptInvitation.mockResolvedValue({});
    mocks.removeMembership.mockResolvedValue(undefined);
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

  it('creates a workspace invitation from the members section', async () => {
    const user = userEvent.setup();
    mocks.listWorkspaces.mockResolvedValue([
      {
        id: 'workspace-1',
        name: 'Team Alpha',
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
      },
    ]);
    mocks.listMemberships.mockResolvedValue([
      {
        id: 'member-1',
        workspace_id: 'workspace-1',
        user_id: 'user-1',
        user_email: 'test@example.com',
        role: 'owner',
      },
    ]);

    renderSettings();

    await screen.findByRole('heading', { name: 'Workspace Members' });
    await waitFor(() => {
      expect(screen.queryByText('Loading workspace membership data...')).not.toBeInTheDocument();
    });

    await user.type(await screen.findByLabelText('Invite by email'), 'teammate@example.com');
    await user.click(screen.getByRole('button', { name: 'Send invite' }));

    await waitFor(() => {
      expect(mocks.createInvitation).toHaveBeenCalledWith('workspace-1', {
        email: 'teammate@example.com',
        role: 'member',
      });
    });
  });

  it('accepts an inbound workspace invitation', async () => {
    const user = userEvent.setup();
    mocks.listMyInvitations.mockResolvedValue([
      {
        id: 'invite-1',
        workspace_id: 'workspace-1',
        workspace_name: 'Team Alpha',
        invited_email: 'test@example.com',
        role: 'member',
        invited_by_user_id: 'user-2',
        invited_by_email: 'owner@example.com',
        created_at: '2026-03-18T12:00:00Z',
      },
    ]);

    renderSettings();

    await user.click(await screen.findByRole('button', { name: 'Accept' }));

    await waitFor(() => {
      expect(mocks.acceptInvitation).toHaveBeenCalledWith('invite-1');
      expect(mocks.refreshUser).toHaveBeenCalled();
    });
  });
});
