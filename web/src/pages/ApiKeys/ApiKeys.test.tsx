import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { ApiKeys } from './ApiKeys';

// Mock the auth context
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { email_verified: true },
    refreshUser: vi.fn(),
  }),
}));

// Mock the API
vi.mock('../../utils/api', () => ({
  apiKeysApi: {
    list: vi.fn().mockResolvedValue([
      {
        id: 'key-1',
        name: 'Test API Key',
        key_preview: 'ace_•••abc',
        scopes: ['playbooks:read', 'playbooks:write'],
        created_at: '2024-01-15T10:00:00Z',
        expires_at: null,
        last_used_at: null,
      },
    ]),
    create: vi.fn(),
    delete: vi.fn(),
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
  });

  describe('Setup Guide Button', () => {
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

    it('displays three tabs: Any Agent, Claude Code, MCP Config', async () => {
      await openSetupDocsModal();

      expect(screen.getByRole('button', { name: 'Any Agent' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Claude Code' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'MCP Config' })).toBeInTheDocument();
    });

    it('shows correct MCP server URL', async () => {
      await openSetupDocsModal();

      expect(screen.getByText(/aceagent\.io\/mcp\/sse/)).toBeInTheDocument();
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
      expect(screen.getByText('Run this command in your terminal:')).toBeInTheDocument();
      expect(screen.getByText(/claude mcp add/)).toBeInTheDocument();

      // Click "MCP Config" tab
      await user.click(screen.getByRole('button', { name: 'MCP Config' }));
      expect(
        screen.getByText('Add this to your MCP configuration file:')
      ).toBeInTheDocument();
      expect(screen.getByText(/"transport": "sse"/)).toBeInTheDocument();
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
    });
  });
});
