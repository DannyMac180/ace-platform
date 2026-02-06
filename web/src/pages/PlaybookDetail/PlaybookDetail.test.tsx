import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { PlaybookDetail } from './PlaybookDetail';
import styles from './PlaybookDetail.module.css';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  update: vi.fn(),
  delete: vi.fn(),
  getVersions: vi.fn(),
  getOutcomes: vi.fn(),
  getEvolutions: vi.fn(),
}));

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    isAuthenticated: true,
    isLoading: false,
  }),
}));

vi.mock('../../utils/api', () => ({
  playbooksApi: {
    get: mocks.get,
    update: mocks.update,
    delete: mocks.delete,
    getVersions: mocks.getVersions,
    getOutcomes: mocks.getOutcomes,
    getEvolutions: mocks.getEvolutions,
  },
}));

vi.mock('../../components/PlaybookRenderer', () => ({
  PlaybookRenderer: ({ content }: { content: string }) => <div>{content}</div>,
}));

function renderPlaybookDetail() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/playbooks/pb-1?tab=evolutions']}>
        <Routes>
          <Route path="/playbooks/:id" element={<PlaybookDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('PlaybookDetail evolutions status rendering', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mocks.get.mockResolvedValue({
      id: 'pb-1',
      name: 'Test Playbook',
      description: 'Test description',
      status: 'active',
      source: 'user_created',
      created_at: '2026-01-01T10:00:00Z',
      updated_at: '2026-01-01T10:00:00Z',
      current_version: null,
    });

    mocks.getEvolutions.mockResolvedValue({
      items: [
        {
          id: 'job-queued',
          status: 'queued',
          from_version_id: null,
          to_version_id: null,
          outcomes_processed: 3,
          error_message: null,
          created_at: '2026-01-01T10:00:00Z',
          started_at: null,
          completed_at: null,
        },
        {
          id: 'job-running',
          status: 'running',
          from_version_id: null,
          to_version_id: null,
          outcomes_processed: 1,
          error_message: null,
          created_at: '2026-01-01T11:00:00Z',
          started_at: '2026-01-01T11:01:00Z',
          completed_at: null,
        },
      ],
      total: 2,
      page: 1,
      page_size: 20,
      total_pages: 1,
    });
  });

  it('renders queued and running evolution statuses with the correct status styles', async () => {
    renderPlaybookDetail();

    await waitFor(() => {
      expect(mocks.getEvolutions).toHaveBeenCalledWith('pb-1');
    });

    const queuedStatus = await screen.findByText('queued');
    const runningStatus = await screen.findByText('running');

    expect(queuedStatus).toBeInTheDocument();
    expect(runningStatus).toBeInTheDocument();
    expect(queuedStatus).toHaveClass(styles.evolutionPending);
    expect(runningStatus).toHaveClass(styles.evolutionRunning);
  });
});
