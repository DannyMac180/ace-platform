import { useState } from 'react';
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { playbooksApi } from '../../utils/api';
import { useAuth } from '../../contexts/AuthContext';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { PlaybookRenderer } from '../../components/PlaybookRenderer';
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
import type { Playbook, PlaybookVersion, PlaybookUpdate, Outcome, EvolutionJob } from '../../types';
import styles from './PlaybookDetail.module.css';

type TabType = 'content' | 'versions' | 'outcomes' | 'evolutions';

const validTabs: TabType[] = ['content', 'versions', 'outcomes', 'evolutions'];

export function PlaybookDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const { isAuthenticated, isLoading: isAuthLoading } = useAuth();
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [updateError, setUpdateError] = useState<string | null>(null);

  // Get tab from URL, default to 'content'
  const tabParam = searchParams.get('tab') as TabType | null;
  const activeTab: TabType = tabParam && validTabs.includes(tabParam) ? tabParam : 'content';

  // Update URL when tab changes
  const setActiveTab = (tab: TabType) => {
    setSearchParams(tab === 'content' ? {} : { tab }, { replace: true });
  };

  const { data: playbook, isLoading, error } = useQuery({
    queryKey: ['playbook', id],
    queryFn: () => playbooksApi.get(id!),
    enabled: !!id && !isAuthLoading && isAuthenticated,
  });

  const deleteMutation = useMutation({
    mutationFn: () => playbooksApi.delete(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      navigate('/dashboard');
    },
  });

  const updateMutation = useMutation({
    mutationFn: (data: PlaybookUpdate) => playbooksApi.update(id!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['playbook', id] });
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      setShowEditModal(false);
      setUpdateError(null);
    },
    onError: () => {
      setUpdateError('Failed to update playbook. Please try again.');
    },
  });

  if (isAuthLoading || isLoading) {
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
          <Button
            variant="secondary"
            icon={<Edit2 size={16} />}
            onClick={() => setShowEditModal(true)}
          >
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
        {activeTab === 'content' && <ContentTab playbook={playbook} playbookId={id!} />}
        {activeTab === 'versions' && <VersionsTab playbookId={id!} isAuthLoading={isAuthLoading} isAuthenticated={isAuthenticated} />}
        {activeTab === 'outcomes' && <OutcomesTab playbookId={id!} isAuthLoading={isAuthLoading} isAuthenticated={isAuthenticated} />}
        {activeTab === 'evolutions' && <EvolutionsTab playbookId={id!} isAuthLoading={isAuthLoading} isAuthenticated={isAuthenticated} />}
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

      {/* Edit Playbook Modal */}
      {showEditModal && (
        <EditPlaybookModal
          playbook={playbook}
          onClose={() => {
            setShowEditModal(false);
            setUpdateError(null);
          }}
          onSave={(data) => updateMutation.mutate(data)}
          isLoading={updateMutation.isPending}
          error={updateError}
        />
      )}
    </div>
  );
}

function ContentTab({
  playbook,
  playbookId,
}: {
  playbook: { current_version: PlaybookVersion | null };
  playbookId: string;
}) {
  if (!playbook.current_version) {
    return (
      <div className={styles.emptyContent}>
        <p>No content yet.</p>
        <Link to={`/playbooks/${playbookId}/edit`}>
          <Button icon={<Edit2 size={16} />}>Add Content</Button>
        </Link>
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
        <Link to={`/playbooks/${playbookId}/edit`} className={styles.editContentLink}>
          <Button variant="secondary" size="sm" icon={<Edit2 size={14} />}>
            Edit Content
          </Button>
        </Link>
      </div>
      <div className={styles.markdownContent}>
        <PlaybookRenderer content={playbook.current_version.content} />
      </div>
    </Card>
  );
}

function VersionsTab({ playbookId, isAuthLoading, isAuthenticated }: { playbookId: string; isAuthLoading: boolean; isAuthenticated: boolean }) {
  const [expandedVersions, setExpandedVersions] = useState<Set<number>>(new Set());

  const { data, isLoading } = useQuery({
    queryKey: ['playbook-versions', playbookId],
    queryFn: () => playbooksApi.getVersions(playbookId),
    enabled: !isAuthLoading && isAuthenticated,
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
              <PlaybookRenderer content={version.content} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function OutcomesTab({ playbookId, isAuthLoading, isAuthenticated }: { playbookId: string; isAuthLoading: boolean; isAuthenticated: boolean }) {
  const { data, isLoading } = useQuery({
    queryKey: ['playbook-outcomes', playbookId],
    queryFn: () => playbooksApi.getOutcomes(playbookId),
    enabled: !isAuthLoading && isAuthenticated,
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

function EvolutionsTab({ playbookId, isAuthLoading, isAuthenticated }: { playbookId: string; isAuthLoading: boolean; isAuthenticated: boolean }) {
  const { data, isLoading } = useQuery({
    queryKey: ['playbook-evolutions', playbookId],
    queryFn: () => playbooksApi.getEvolutions(playbookId),
    enabled: !isAuthLoading && isAuthenticated,
  });

  if (isLoading) {
    return <div className={styles.loading}><div className={styles.spinner} /></div>;
  }

  if (!data?.items.length) {
    return <div className={styles.emptyContent}>No evolutions yet.</div>;
  }

  const statusStyles = {
    queued: styles.evolutionPending,
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

interface EditModalProps {
  playbook: Playbook;
  onClose: () => void;
  onSave: (data: PlaybookUpdate) => void;
  isLoading: boolean;
  error: string | null;
}

function EditPlaybookModal({ playbook, onClose, onSave, isLoading, error }: EditModalProps) {
  const [name, setName] = useState(playbook.name);
  const [description, setDescription] = useState(playbook.description || '');
  const [status, setStatus] = useState<'active' | 'paused' | 'archived'>(playbook.status);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave({
      name: name !== playbook.name ? name : undefined,
      description: description !== (playbook.description || '') ? description : undefined,
      status: status !== playbook.status ? status : undefined,
    });
  };

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h2>Edit Playbook</h2>
        {error && (
          <div className={styles.modalError}>
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}
        <form onSubmit={handleSubmit} className={styles.editForm}>
          <Input
            label="Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <Input
            label="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="A brief description..."
          />
          <div className={styles.selectWrapper}>
            <label className={styles.selectLabel}>Status</label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value as 'active' | 'paused' | 'archived')}
              className={styles.select}
            >
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="archived">Archived</option>
            </select>
          </div>
          <div className={styles.modalActions}>
            <Button variant="ghost" type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" isLoading={isLoading}>
              Save Changes
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
