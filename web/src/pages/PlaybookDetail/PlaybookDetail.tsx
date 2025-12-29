import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { playbooksApi } from '../../utils/api';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import {
  ArrowLeft,
  Edit2,
  Trash2,
  GitBranch,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Sparkles,
} from 'lucide-react';
import type { PlaybookVersion, Outcome, EvolutionJob } from '../../types';
import styles from './PlaybookDetail.module.css';

type TabType = 'content' | 'versions' | 'outcomes' | 'evolutions';

export function PlaybookDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabType>('content');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const { data: playbook, isLoading, error } = useQuery({
    queryKey: ['playbook', id],
    queryFn: () => playbooksApi.get(id!),
    enabled: !!id,
  });

  const deleteMutation = useMutation({
    mutationFn: () => playbooksApi.delete(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      navigate('/dashboard');
    },
  });

  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>
          <div className={styles.spinner} />
          <span>Loading playbook...</span>
        </div>
      </div>
    );
  }

  if (error || !playbook) {
    return (
      <div className={styles.container}>
        <div className={styles.error}>
          <AlertCircle size={24} />
          <span>Failed to load playbook</span>
          <Button variant="secondary" onClick={() => navigate('/dashboard')}>
            Back to Dashboard
          </Button>
        </div>
      </div>
    );
  }

  const statusColors = {
    active: styles.statusActive,
    paused: styles.statusPaused,
    archived: styles.statusArchived,
  };

  return (
    <div className={styles.container}>
      {/* Header */}
      <div className={styles.header}>
        <Link to="/dashboard" className={styles.backLink}>
          <ArrowLeft size={20} />
          <span>Back to Playbooks</span>
        </Link>

        <div className={styles.headerContent}>
          <div className={styles.titleRow}>
            <h1>{playbook.name}</h1>
            <span className={`${styles.statusBadge} ${statusColors[playbook.status]}`}>
              {playbook.status}
            </span>
          </div>
          {playbook.description && <p className={styles.description}>{playbook.description}</p>}
        </div>

        <div className={styles.headerActions}>
          <Button variant="secondary" icon={<Edit2 size={16} />}>
            Edit
          </Button>
          <Button
            variant="danger"
            icon={<Trash2 size={16} />}
            onClick={() => setShowDeleteConfirm(true)}
          >
            Delete
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className={styles.tabs}>
        <button
          className={`${styles.tab} ${activeTab === 'content' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('content')}
        >
          Content
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'versions' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('versions')}
        >
          <GitBranch size={16} />
          Versions
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'outcomes' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('outcomes')}
        >
          <CheckCircle2 size={16} />
          Outcomes
        </button>
        <button
          className={`${styles.tab} ${activeTab === 'evolutions' ? styles.activeTab : ''}`}
          onClick={() => setActiveTab('evolutions')}
        >
          <Sparkles size={16} />
          Evolutions
        </button>
      </div>

      {/* Tab Content */}
      <div className={styles.tabContent}>
        {activeTab === 'content' && <ContentTab playbook={playbook} />}
        {activeTab === 'versions' && <VersionsTab playbookId={id!} />}
        {activeTab === 'outcomes' && <OutcomesTab playbookId={id!} />}
        {activeTab === 'evolutions' && <EvolutionsTab playbookId={id!} />}
      </div>

      {/* Delete Confirmation Modal */}
      {showDeleteConfirm && (
        <div className={styles.modalOverlay} onClick={() => setShowDeleteConfirm(false)}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <h2>Delete Playbook</h2>
            <p>
              Are you sure you want to delete "{playbook.name}"? This action cannot be undone.
            </p>
            <div className={styles.modalActions}>
              <Button variant="ghost" onClick={() => setShowDeleteConfirm(false)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                onClick={() => deleteMutation.mutate()}
                isLoading={deleteMutation.isPending}
              >
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ContentTab({ playbook }: { playbook: { current_version: PlaybookVersion | null } }) {
  if (!playbook.current_version) {
    return (
      <div className={styles.emptyContent}>
        <p>No content yet. Add outcomes to start evolving this playbook.</p>
      </div>
    );
  }

  return (
    <Card variant="default" padding="lg">
      <div className={styles.contentHeader}>
        <span className={styles.versionBadge}>
          Version {playbook.current_version.version_number}
        </span>
        <span className={styles.bulletCount}>
          {playbook.current_version.bullet_count} bullets
        </span>
      </div>
      <div className={styles.markdownContent}>
        <pre>{playbook.current_version.content}</pre>
      </div>
    </Card>
  );
}

function VersionsTab({ playbookId }: { playbookId: string }) {
  const [expandedVersions, setExpandedVersions] = useState<Set<number>>(new Set());

  const { data, isLoading } = useQuery({
    queryKey: ['playbook-versions', playbookId],
    queryFn: () => playbooksApi.getVersions(playbookId),
  });

  const toggleVersion = (versionNumber: number) => {
    setExpandedVersions((prev) => {
      const next = new Set(prev);
      if (next.has(versionNumber)) {
        next.delete(versionNumber);
      } else {
        next.add(versionNumber);
      }
      return next;
    });
  };

  if (isLoading) {
    return <div className={styles.loading}><div className={styles.spinner} /></div>;
  }

  if (!data?.items.length) {
    return <div className={styles.emptyContent}>No versions yet.</div>;
  }

  return (
    <div className={styles.versionsList}>
      {data.items.map((version, index) => (
        <div key={version.id} className={styles.versionItem}>
          <div
            className={styles.versionHeader}
            onClick={() => toggleVersion(version.version_number)}
          >
            <div className={styles.versionLine}>
              <div className={`${styles.versionDot} ${index === 0 ? styles.currentVersion : ''}`} />
              {index < data.items.length - 1 && <div className={styles.versionConnector} />}
            </div>
            <div className={styles.versionInfo}>
              <div className={styles.versionTitle}>
                <span>Version {version.version_number}</span>
                {index === 0 && <span className={styles.currentBadge}>Current</span>}
              </div>
              <div className={styles.versionMeta}>
                <Clock size={14} />
                <span>{new Date(version.created_at).toLocaleDateString()}</span>
                <span className={styles.bulletCount}>{version.bullet_count} bullets</span>
              </div>
              {version.diff_summary && (
                <p className={styles.diffSummary}>{version.diff_summary}</p>
              )}
            </div>
            <div className={styles.expandIcon}>
              {expandedVersions.has(version.version_number) ? (
                <ChevronDown size={20} />
              ) : (
                <ChevronRight size={20} />
              )}
            </div>
          </div>
          {expandedVersions.has(version.version_number) && (
            <div className={styles.versionContent}>
              <pre>{version.content}</pre>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function OutcomesTab({ playbookId }: { playbookId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['playbook-outcomes', playbookId],
    queryFn: () => playbooksApi.getOutcomes(playbookId),
  });

  if (isLoading) {
    return <div className={styles.loading}><div className={styles.spinner} /></div>;
  }

  if (!data?.items.length) {
    return <div className={styles.emptyContent}>No outcomes recorded yet.</div>;
  }

  const statusIcons = {
    success: <CheckCircle2 size={16} className={styles.outcomeSuccess} />,
    failure: <XCircle size={16} className={styles.outcomeFailure} />,
    partial: <AlertCircle size={16} className={styles.outcomePartial} />,
  };

  return (
    <div className={styles.outcomesList}>
      {data.items.map((outcome: Outcome) => (
        <Card key={outcome.id} variant="default" className={styles.outcomeCard}>
          <div className={styles.outcomeHeader}>
            {statusIcons[outcome.outcome_status]}
            <span className={styles.outcomeStatus}>{outcome.outcome_status}</span>
            <span className={styles.outcomeMeta}>
              {outcome.processed_at ? 'Processed' : 'Pending'}
            </span>
          </div>
          <p className={styles.outcomeDescription}>{outcome.task_description}</p>
          {outcome.notes && <p className={styles.outcomeNotes}>{outcome.notes}</p>}
          <div className={styles.outcomeFooter}>
            <Clock size={14} />
            <span>{new Date(outcome.created_at).toLocaleDateString()}</span>
          </div>
        </Card>
      ))}
    </div>
  );
}

function EvolutionsTab({ playbookId }: { playbookId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['playbook-evolutions', playbookId],
    queryFn: () => playbooksApi.getEvolutions(playbookId),
  });

  if (isLoading) {
    return <div className={styles.loading}><div className={styles.spinner} /></div>;
  }

  if (!data?.items.length) {
    return <div className={styles.emptyContent}>No evolutions yet.</div>;
  }

  const statusStyles = {
    pending: styles.evolutionPending,
    running: styles.evolutionRunning,
    completed: styles.evolutionCompleted,
    failed: styles.evolutionFailed,
  };

  return (
    <div className={styles.evolutionsList}>
      {data.items.map((job: EvolutionJob) => (
        <Card key={job.id} variant="default" className={styles.evolutionCard}>
          <div className={styles.evolutionHeader}>
            <Sparkles size={18} className={styles.evolutionIcon} />
            <span className={`${styles.evolutionStatus} ${statusStyles[job.status]}`}>
              {job.status}
            </span>
          </div>
          <div className={styles.evolutionInfo}>
            <p>Processed {job.outcomes_processed} outcomes</p>
            {job.error_message && (
              <p className={styles.evolutionError}>{job.error_message}</p>
            )}
          </div>
          <div className={styles.evolutionFooter}>
            <Clock size={14} />
            <span>{new Date(job.created_at).toLocaleDateString()}</span>
            {job.completed_at && (
              <span>Completed: {new Date(job.completed_at).toLocaleTimeString()}</span>
            )}
          </div>
        </Card>
      ))}
    </div>
  );
}
