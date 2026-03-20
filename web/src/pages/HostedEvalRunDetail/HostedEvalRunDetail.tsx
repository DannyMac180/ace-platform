import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  LoaderCircle,
  Sparkles,
  XCircle,
} from 'lucide-react';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { useAuth } from '../../contexts/AuthContext';
import { hostedEvalRunsApi } from '../../utils/api';
import type { HostedEvalRun } from '../../types';
import styles from './HostedEvalRunDetail.module.css';

const ACTIVE_STATUSES = new Set<HostedEvalRun['status']>(['queued', 'running']);

export function HostedEvalRunDetail() {
  const { id, runId } = useParams<{ id: string; runId: string }>();
  const navigate = useNavigate();
  const { isAuthenticated, isLoading: isAuthLoading } = useAuth();

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['hosted-eval-run', runId],
    queryFn: () => hostedEvalRunsApi.get(runId!),
    enabled: !!runId && !isAuthLoading && isAuthenticated,
    refetchInterval: (query) => {
      const run = query.state.data as HostedEvalRun | undefined;
      return run && ACTIVE_STATUSES.has(run.status) ? 3000 : false;
    },
  });

  if (isAuthLoading || isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.stateBlock}>
          <div className={styles.spinner} />
          <span>Loading hosted eval run...</span>
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className={styles.container}>
        <div className={styles.stateBlock}>
          <AlertCircle size={24} />
          <span>Failed to load hosted eval run.</span>
          <div className={styles.errorActions}>
            <Button variant="secondary" onClick={() => refetch()}>
              Retry
            </Button>
            <Button variant="ghost" onClick={() => navigate(id ? `/playbooks/${id}?tab=evolutions` : '/dashboard')}>
              Back
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const tokenSummary = summarizeTokenTotals(data.token_totals);
  const statusMeta = getStatusMeta(data.status);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <Link to={id ? `/playbooks/${id}?tab=evolutions` : '/dashboard'} className={styles.backLink}>
          <ArrowLeft size={18} />
          <span>Back to evolutions</span>
        </Link>
        <div className={styles.headerCopy}>
          <div className={styles.eyebrow}>
            <Sparkles size={16} />
            <span>Hosted Eval Run</span>
          </div>
          <h1>{data.playbook_name}</h1>
          <p>
            This run was launched through ACE-hosted infrastructure for your personal workspace.
          </p>
        </div>
        <span className={`${styles.statusBadge} ${styles[`status-${data.status}`]}`}>
          {statusMeta.icon}
          <span>{statusMeta.label}</span>
        </span>
      </div>

      <div className={styles.summaryGrid}>
        <Card variant="default" padding="lg" className={styles.summaryCard}>
          <p className={styles.label}>Queued</p>
          <p className={styles.value}>{formatTimestamp(data.created_at)}</p>
        </Card>
        <Card variant="default" padding="lg" className={styles.summaryCard}>
          <p className={styles.label}>Started</p>
          <p className={styles.value}>{data.started_at ? formatTimestamp(data.started_at) : 'Waiting for worker'}</p>
        </Card>
        <Card variant="default" padding="lg" className={styles.summaryCard}>
          <p className={styles.label}>Completed</p>
          <p className={styles.value}>{data.completed_at ? formatTimestamp(data.completed_at) : 'Still in progress'}</p>
        </Card>
        <Card variant="default" padding="lg" className={styles.summaryCard}>
          <p className={styles.label}>Outcomes processed</p>
          <p className={styles.value}>{data.outcomes_processed}</p>
        </Card>
      </div>

      <div className={styles.detailGrid}>
        <Card variant="default" padding="lg" className={styles.detailCard}>
          <h2>Run result</h2>
          <div className={styles.detailList}>
            <div className={styles.detailRow}>
              <span>Status</span>
              <strong>{statusMeta.description}</strong>
            </div>
            <div className={styles.detailRow}>
              <span>Changes created</span>
              <strong>{formatChangesState(data.has_changes)}</strong>
            </div>
            <div className={styles.detailRow}>
              <span>Workspace scope</span>
              <strong>{data.workspace_id}</strong>
            </div>
            {data.ace_core_version && (
              <div className={styles.detailRow}>
                <span>ACE core version</span>
                <strong>{data.ace_core_version}</strong>
              </div>
            )}
          </div>
        </Card>

        <Card variant="default" padding="lg" className={styles.detailCard}>
          <h2>Version output</h2>
          <div className={styles.versionGrid}>
            <div className={styles.versionPanel}>
              <p className={styles.label}>From version</p>
              <p className={styles.value}>
                {data.from_version ? `v${data.from_version.version_number}` : 'No prior version'}
              </p>
            </div>
            <div className={styles.versionPanel}>
              <p className={styles.label}>To version</p>
              <p className={styles.value}>
                {data.to_version ? `v${data.to_version.version_number}` : 'No new version yet'}
              </p>
            </div>
          </div>
          {data.to_version?.diff_summary && (
            <div className={styles.diffBlock}>
              <p className={styles.label}>Diff summary</p>
              <p>{data.to_version.diff_summary}</p>
            </div>
          )}
        </Card>

        <Card variant="default" padding="lg" className={styles.detailCard}>
          <h2>Token usage</h2>
          <div className={styles.detailList}>
            <div className={styles.detailRow}>
              <span>Total tokens</span>
              <strong>{tokenSummary.totalTokens}</strong>
            </div>
            <div className={styles.detailRow}>
              <span>Model</span>
              <strong>{tokenSummary.model}</strong>
            </div>
            <div className={styles.detailRow}>
              <span>Tracked operations</span>
              <strong>{tokenSummary.operationCount}</strong>
            </div>
          </div>
        </Card>
      </div>

      {data.error_message && (
        <Card variant="outlined" padding="lg" className={styles.errorCard}>
          <div className={styles.errorHeader}>
            <AlertCircle size={18} />
            <h2>Worker error</h2>
          </div>
          <p>{data.error_message}</p>
        </Card>
      )}
    </div>
  );
}

function getStatusMeta(status: HostedEvalRun['status']) {
  switch (status) {
    case 'queued':
      return {
        label: 'Queued',
        description: 'Queued for hosted execution',
        icon: <Clock size={16} />,
      };
    case 'running':
      return {
        label: 'Running',
        description: 'Currently running in hosted infrastructure',
        icon: <LoaderCircle size={16} className={styles.spinningIcon} />,
      };
    case 'completed':
      return {
        label: 'Completed',
        description: 'Completed successfully',
        icon: <CheckCircle2 size={16} />,
      };
    case 'failed':
      return {
        label: 'Failed',
        description: 'Completed with an error',
        icon: <XCircle size={16} />,
      };
  }
}

function formatTimestamp(value: string) {
  return new Date(value).toLocaleString();
}

function formatChangesState(hasChanges: boolean | null) {
  if (hasChanges === null) {
    return 'Pending result';
  }
  return hasChanges ? 'New playbook version created' : 'No content changes';
}

function summarizeTokenTotals(tokenTotals: Record<string, unknown> | null) {
  const model = typeof tokenTotals?.model === 'string' ? tokenTotals.model : 'Not reported';
  const totalTokens =
    typeof tokenTotals?.total_tokens === 'number' ? tokenTotals.total_tokens.toLocaleString() : 'Not reported';
  const operations = tokenTotals?.operations;
  const operationCount =
    operations && typeof operations === 'object' ? Object.keys(operations as Record<string, unknown>).length : 0;

  return {
    model,
    totalTokens,
    operationCount,
  };
}
