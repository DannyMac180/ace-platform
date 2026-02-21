import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { ApiKeys } from './ApiKeys';

const {
  mockListApiKeys,
  mockCreateApiKey,
  mockDeleteApiKey,
  mockAuthState,
} = vi.hoisted(() => {
  const refreshUser = vi.fn();
  const mockAuthState: {
    user: {
      email_verified: boolean;
      subscription_status: 'active' | 'past_due' | 'canceled' | 'unpaid' | 'none';
      subscription_tier: string | null;
      has_used_trial: boolean;
    };
    refreshUser: ReturnType<typeof vi.fn>;
  } = {
    user: {
      email_verified: true,
      subscription_status: 'active',
      subscription_tier: 'starter',
      has_used_trial: false,
    },
    refreshUser,
  };

  return {
    mockListApiKeys: vi.fn(),
    mockCreateApiKey: vi.fn(),
    mockDeleteApiKey: vi.fn(),
    mockAuthState,
  };
});

// Mock the auth context
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => mockAuthState,
}));

// Mock the API
vi.mock('../../utils/api', () => ({
  apiKeysApi: {
    list: mockListApiKeys,
    create: mockCreateApiKey,
    delete: mockDeleteApiKey,
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

describe('ApiKeys', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthState.user = {
      email_verified: true,
      subscription_status: 'active',
      subscription_tier: 'starter',
      has_used_trial: false,
    };
    mockListApiKeys.mockResolvedValue([
      {
        id: 'key-1',
        name: 'Test API Key',
        key_prefix: 'ace_1234',
        scopes: ['playbooks:read', 'playbooks:write'],
        created_at: '2024-01-15T10:00:00Z',
        last_used_at: null,
        is_active: true,
      },
    ]);
  });

  describe('Setup Guide Button', () => {
    it('renders API key prefix from backend payload shape', async () => {
      renderWithProviders(<ApiKeys />);

      await waitFor(() => {
        expect(screen.getByText('Test API Key')).toBeInTheDocument();
      });

      expect(screen.getByText('ace_1234')).toBeInTheDocument();
    });

    it('renders setup guide button on each API key card', async () => {
      renderWithProviders(<ApiKeys />);

      // Wait for API keys to load
      await waitFor(() => {
        expect(screen.getByText('Test API Key')).toBeInTheDocument();
      });

      // Check for the setup button (BookOpen icon button)
      const setupButton = screen.getByTitle('View setup instructions');
      expect(setupButton).toBeInTheDocument();
    });

    it('opens SetupDocsModal when setup button is clicked', async () => {
      const user = userEvent.setup();
      renderWithProviders(<ApiKeys />);

      // Wait for API keys to load
      await waitFor(() => {
        expect(screen.getByText('Test API Key')).toBeInTheDocument();
      });

      // Click the setup button
      const setupButton = screen.getByTitle('View setup instructions');
      await user.click(setupButton);

      // Check that the modal opens
      expect(screen.getByText('MCP Setup Guide')).toBeInTheDocument();
      expect(
        screen.getByText(/Connect your AI coding assistant to ACE Platform/)
      ).toBeInTheDocument();
    });
  });

  describe('Subscription and Verification States', () => {
    it('shows a trial prompt instead of a load error for users without paid access', async () => {
      mockAuthState.user = {
        email_verified: true,
        subscription_status: 'none',
        subscription_tier: null,
        has_used_trial: false,
      };

      renderWithProviders(<ApiKeys />);

      await waitFor(() => {
        expect(screen.getByText('Start Your Free Trial')).toBeInTheDocument();
      });

      expect(screen.queryByText('Failed to load API keys')).not.toBeInTheDocument();
      expect(mockListApiKeys).not.toHaveBeenCalled();
    });

    it('does not fetch API keys for unverified users', async () => {
      mockAuthState.user = {
        email_verified: false,
        subscription_status: 'active',
        subscription_tier: 'starter',
        has_used_trial: false,
      };

      renderWithProviders(<ApiKeys />);

      await waitFor(() => {
        expect(screen.getByText('Email verification required')).toBeInTheDocument();
      });

      expect(screen.queryByText('Failed to load API keys')).not.toBeInTheDocument();
      expect(mockListApiKeys).not.toHaveBeenCalled();
    });
  });

  describe('SetupDocsModal', () => {
    async function openSetupDocsModal() {
      const user = userEvent.setup();
      renderWithProviders(<ApiKeys />);

      await waitFor(() => {
        expect(screen.getByText('Test API Key')).toBeInTheDocument();
      });

      const setupButton = screen.getByTitle('View setup instructions');
      await user.click(setupButton);

      return user;
    }

    it('displays three tabs: Any Agent, Claude Code, JSON Config', async () => {
      await openSetupDocsModal();

      expect(screen.getByRole('button', { name: 'Any Agent' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Claude Code' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'JSON Config' })).toBeInTheDocument();
    });

    it('shows correct MCP server URL', async () => {
      await openSetupDocsModal();

      expect(screen.getByText(/Server URL:\s*https:\/\/aceagent\.io\/mcp\b/)).toBeInTheDocument();
    });

    it('shows placeholder for API key', async () => {
      await openSetupDocsModal();

      // The placeholder appears multiple times (in the code block and the note)
      const placeholders = screen.getAllByText(/<YOUR_API_KEY>/);
      expect(placeholders.length).toBeGreaterThan(0);
    });

    it('switches between tabs when clicked', async () => {
      const user = await openSetupDocsModal();

      // Default is "Any Agent" tab - check for its instruction text
      expect(
        screen.getByText('Copy and paste this into your AI coding assistant:')
      ).toBeInTheDocument();

      // Click "Claude Code" tab
      await user.click(screen.getByRole('button', { name: 'Claude Code' }));
      expect(screen.getByText(/Add this to your/i)).toBeInTheDocument();
      expect(screen.getByText('~/.claude.json')).toBeInTheDocument();
      expect(screen.getByText(/"X-API-Key": "<YOUR_API_KEY>"/)).toBeInTheDocument();

      // Click "JSON Config" tab
      await user.click(screen.getByRole('button', { name: 'JSON Config' }));
      expect(screen.getByText(/Add this to your MCP client configuration:/)).toBeInTheDocument();
      expect(screen.getByText(/"type": "http"/)).toBeInTheDocument();
    });

    it('has copy buttons in the code block', async () => {
      await openSetupDocsModal();

      // Verify there are buttons that can be used for copying
      // The copy button is inside the setupCodeBlock
      const buttons = screen.getAllByRole('button');

      // Filter to buttons that are likely copy buttons (small buttons with SVG icons, no text)
      const iconButtons = buttons.filter(btn => {
        const hasIcon = btn.querySelector('svg');
        const hasNoText = !btn.textContent?.trim() || btn.textContent === '';
        return hasIcon && hasNoText;
      });

      // There should be at least one copy button
      expect(iconButtons.length).toBeGreaterThan(0);
    });

    it('closes modal when Done button is clicked', async () => {
      const user = await openSetupDocsModal();

      // Click Done button
      await user.click(screen.getByRole('button', { name: 'Done' }));

      // Modal should be closed
      await waitFor(() => {
        expect(screen.queryByText('MCP Setup Guide')).not.toBeInTheDocument();
      });
    });

    it('does not close modal when clicking inside the modal', async () => {
      const user = await openSetupDocsModal();

      // Click inside the modal (on the title)
      await user.click(screen.getByText('MCP Setup Guide'));

      // Modal should still be open
      expect(screen.getByText('MCP Setup Guide')).toBeInTheDocument();
    });

    it('displays helpful notes about API key replacement', async () => {
      await openSetupDocsModal();

      expect(
        screen.getByText(/Replace.*with your API key/)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/If you've lost your key, create a new one/)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Legacy SSE endpoint compatibility remains available at/)
      ).toBeInTheDocument();
    });
  });
});
