import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { playbooksApi } from '../../utils/api';
import { useAuth } from '../../contexts/AuthContext';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { SubscriptionGate } from '../../components/SubscriptionGate';
import {
  Plus,
  BookOpen,
  Clock,
  GitBranch,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Search,
  Filter,
} from 'lucide-react';
import type { PlaybookListItem, PlaybookCreate } from '../../types';
import styles from './Dashboard.module.css';

export function Dashboard() {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [mutationError, setMutationError] = useState<string | null>(null);

  const queryClient = useQueryClient();
  const { isAuthenticated, isLoading: isAuthLoading } = useAuth();

  const { data, isLoading, error } = useQuery({
    queryKey: ['playbooks', statusFilter, isAuthenticated],
    queryFn: () => playbooksApi.list(1, 50, statusFilter || undefined),
    enabled: !isAuthLoading && isAuthenticated,
    staleTime: 0, // Always consider data stale to ensure fresh fetches
  });

  const createMutation = useMutation({
    mutationFn: (newPlaybook: PlaybookCreate) => playbooksApi.create(newPlaybook),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      setShowCreateModal(false);
      setMutationError(null);
    },
    onError: () => {
      setMutationError('Failed to create playbook. Please try again.');
    },
  });

  const filteredPlaybooks = data?.items.filter((pb) =>
    pb.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerContent}>
          <h1>Playbooks</h1>
          <p>Living documentation that evolves with your outcomes</p>
        </div>
        <SubscriptionGate featureName="Playbooks">
          <Button icon={<Plus size={18} />} onClick={() => setShowCreateModal(true)}>
            New Playbook
          </Button>
        </SubscriptionGate>
      </div>

      {/* Filters */}
      <div className={styles.filters}>
        <div className={styles.searchWrapper}>
          <Search size={18} className={styles.searchIcon} />
          <input
            type="text"
            placeholder="Search playbooks..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className={styles.searchInput}
          />
        </div>
        <div className={styles.filterWrapper}>
          <Filter size={18} />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className={styles.filterSelect}
            aria-label="Filter by status"
          >
            <option value="">All Status</option>
            <option value="active">Active</option>
            <option value="paused">Paused</option>
            <option value="archived">Archived</option>
          </select>
        </div>
      </div>

      {/* Mutation Error */}
      {mutationError && (
        <div className={styles.mutationError}>
          <AlertCircle size={20} />
          <span>{mutationError}</span>
          <button
            className={styles.dismissError}
            onClick={() => setMutationError(null)}
            aria-label="Dismiss error"
          >
            &times;
          </button>
        </div>
      )}

      {/* Content */}
      {isAuthLoading || isLoading ? (
        <div className={styles.loading}>
          <div className={styles.spinner} />
          <span>Loading playbooks...</span>
        </div>
      ) : error ? (
        <div className={styles.error}>
          <AlertCircle size={24} />
          <span>Failed to load playbooks</span>
        </div>
      ) : filteredPlaybooks?.length === 0 ? (
        <EmptyState onCreateClick={() => setShowCreateModal(true)} />
      ) : (
        <div className={styles.grid}>
          {filteredPlaybooks?.map((playbook) => (
            <PlaybookCard key={playbook.id} playbook={playbook} />
          ))}
        </div>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <CreatePlaybookModal
          onClose={() => setShowCreateModal(false)}
          onCreate={(data) => createMutation.mutate(data)}
          isLoading={createMutation.isPending}
        />
      )}
    </div>
  );
}

function PlaybookCard({ playbook }: { playbook: PlaybookListItem }) {
  const statusIcon = {
    active: <CheckCircle2 size={14} className={styles.statusActive} />,
    paused: <AlertCircle size={14} className={styles.statusPaused} />,
    archived: <XCircle size={14} className={styles.statusArchived} />,
  };

  return (
    <Link to={`/playbooks/${playbook.id}`} className={styles.cardLink}>
      <Card variant="default" className={styles.card}>
        <div className={styles.cardHeader}>
          <div className={styles.cardIcon}>
            <BookOpen size={20} />
          </div>
          <div className={styles.cardStatus}>
            {statusIcon[playbook.status]}
            <span>{playbook.status}</span>
          </div>
        </div>

        <h3 className={styles.cardTitle}>{playbook.name}</h3>
        {playbook.description && (
          <p className={styles.cardDescription}>{playbook.description}</p>
        )}

        <div className={styles.cardMeta}>
          <div className={styles.metaItem}>
            <GitBranch size={14} />
            <span>{playbook.version_count} versions</span>
          </div>
          <div className={styles.metaItem}>
            <CheckCircle2 size={14} />
            <span>{playbook.outcome_count} outcomes</span>
          </div>
        </div>

        <div className={styles.cardFooter}>
          <Clock size={14} />
          <span>Updated {formatRelativeTime(playbook.updated_at)}</span>
        </div>
      </Card>
    </Link>
  );
}

function EmptyState({ onCreateClick }: { onCreateClick: () => void }) {
  return (
    <div className={styles.emptyState}>
      <div className={styles.emptyIcon}>
        <BookOpen size={48} />
      </div>
      <h2>No playbooks yet</h2>
      <p>Create your first playbook to start building living documentation</p>
      <SubscriptionGate featureName="Playbooks">
        <Button icon={<Plus size={18} />} onClick={onCreateClick}>
          Create your first playbook
        </Button>
      </SubscriptionGate>
    </div>
  );
}

interface CreateModalProps {
  onClose: () => void;
  onCreate: (data: PlaybookCreate) => void;
  isLoading: boolean;
}

function CreatePlaybookModal({ onClose, onCreate, isLoading }: CreateModalProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [content, setContent] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onCreate({
      name,
      description: description || undefined,
      initial_content: content || undefined,
    });
  };

  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h2>Create New Playbook</h2>
        <form onSubmit={handleSubmit} className={styles.modalForm}>
          <Input
            label="Name"
            placeholder="My Playbook"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <Input
            label="Description"
            placeholder="A brief description of what this playbook covers"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <div className={styles.textareaWrapper}>
            <label className={styles.textareaLabel}>Initial Content (optional)</label>
            <textarea
              placeholder="# My Playbook&#10;&#10;Write your initial playbook content here in Markdown..."
              value={content}
              onChange={(e) => setContent(e.target.value)}
              className={styles.textarea}
              rows={8}
            />
          </div>
          <div className={styles.modalActions}>
            <Button variant="ghost" type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" isLoading={isLoading}>
              Create Playbook
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}
