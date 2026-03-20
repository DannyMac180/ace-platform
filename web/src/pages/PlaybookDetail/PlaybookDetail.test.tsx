import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { PlaybookDetail } from './PlaybookDetail';
import styles from './PlaybookDetail.module.css';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  update: vi.fn(),
  delete: vi.fn(),
  runReviewAction: vi.fn(),
  getVersions: vi.fn(),
  getOutcomes: vi.fn(),
  getActivity: vi.fn(),
  getEvolutions: vi.fn(),
  triggerHostedEval: vi.fn(),
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
    runReviewAction: mocks.runReviewAction,
    getVersions: mocks.getVersions,
    getOutcomes: mocks.getOutcomes,
    getActivity: mocks.getActivity,
    getEvolutions: mocks.getEvolutions,
  },
  hostedEvalRunsApi: {
    trigger: mocks.triggerHostedEval,
  },
}));

vi.mock('../../components/PlaybookRenderer', () => ({
  PlaybookRenderer: ({ content }: { content: string }) => <div>{content}</div>,
}));

function renderPlaybookDetail(entry = '/playbooks/pb-1?tab=evolutions') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
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
      review_status: 'draft',
      review_status_updated_at: '2026-01-01T10:00:00Z',
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
    mocks.getActivity.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
      total_pages: 0,
    });
    mocks.runReviewAction.mockResolvedValue({
      id: 'pb-1',
      name: 'Test Playbook',
      description: 'Test description',
      status: 'active',
      review_status: 'approved',
      review_status_updated_at: '2026-01-01T10:10:00Z',
      source: 'user_created',
      created_at: '2026-01-01T10:00:00Z',
      updated_at: '2026-01-01T10:10:00Z',
      current_version: null,
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

  it('shows the review state badge and available review action buttons', async () => {
    renderPlaybookDetail();

    expect(await screen.findByText('draft')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Submit for Review' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Archive' })).toBeInTheDocument();
  });

  it('renders review activity and submits review actions', async () => {
    const user = userEvent.setup();

    mocks.get.mockResolvedValue({
      id: 'pb-1',
      name: 'Test Playbook',
      description: 'Test description',
      status: 'active',
      review_status: 'proposed',
      review_status_updated_at: '2026-01-01T10:05:00Z',
      source: 'user_created',
      created_at: '2026-01-01T10:00:00Z',
      updated_at: '2026-01-01T10:05:00Z',
      current_version: null,
    });
    mocks.getActivity.mockResolvedValue({
      items: [
        {
          id: 'evt-1',
          action: 'proposed',
          from_review_status: 'draft',
          to_review_status: 'proposed',
          actor_user_id: 'user-1',
          actor_email: 'reviewer@example.com',
          created_at: '2026-01-01T10:05:00Z',
        },
      ],
      total: 1,
      page: 1,
      page_size: 20,
      total_pages: 1,
    });

    renderPlaybookDetail('/playbooks/pb-1?tab=activity');

    await waitFor(() => {
      expect(mocks.getActivity).toHaveBeenCalledWith('pb-1');
    });

    expect(await screen.findByText('Submitted for review')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Approve' }));

    await waitFor(() => {
      expect(mocks.runReviewAction).toHaveBeenCalledWith('pb-1', { action: 'approved' });
    });
  });
});
