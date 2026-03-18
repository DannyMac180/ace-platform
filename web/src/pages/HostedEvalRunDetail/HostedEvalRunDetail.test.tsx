import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { HostedEvalRunDetail } from './HostedEvalRunDetail';

const mocks = vi.hoisted(() => ({
  getRun: vi.fn(),
}));

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    isAuthenticated: true,
    isLoading: false,
  }),
}));

vi.mock('../../utils/api', () => ({
  hostedEvalRunsApi: {
    get: mocks.getRun,
  },
}));

function renderHostedEvalRunDetail() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/playbooks/pb-1/evolutions/run-1']}>
        <Routes>
          <Route path="/playbooks/:id/evolutions/:runId" element={<HostedEvalRunDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('HostedEvalRunDetail', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getRun.mockResolvedValue({
      id: 'run-1',
      workspace_id: 'me',
      playbook_id: 'pb-1',
      playbook_name: 'Revenue Assistant',
      status: 'completed',
      outcomes_processed: 6,
      error_message: null,
      created_at: '2026-01-01T10:00:00Z',
      started_at: '2026-01-01T10:01:00Z',
      completed_at: '2026-01-01T10:02:00Z',
      ace_core_version: '1.2.3',
      token_totals: {
        total_tokens: 3210,
        model: 'gpt-5.2',
        operations: {
          evolve: { total_tokens: 3210 },
        },
      },
      has_changes: true,
      from_version: {
        id: 'v1',
        version_number: 1,
        created_at: '2026-01-01T09:00:00Z',
        diff_summary: null,
      },
      to_version: {
        id: 'v2',
        version_number: 2,
        created_at: '2026-01-01T10:02:00Z',
        diff_summary: 'Added a fallback qualification step',
      },
    });
  });

  it('renders hosted eval run status and stored result detail', async () => {
    renderHostedEvalRunDetail();

    await waitFor(() => {
      expect(mocks.getRun).toHaveBeenCalledWith('run-1');
    });

    expect(await screen.findByText('Revenue Assistant')).toBeInTheDocument();
    expect(screen.getByText('Completed successfully')).toBeInTheDocument();
    expect(screen.getByText('New playbook version created')).toBeInTheDocument();
    expect(screen.getByText('Added a fallback qualification step')).toBeInTheDocument();
    expect(screen.getByText('3,210')).toBeInTheDocument();
  });
});
