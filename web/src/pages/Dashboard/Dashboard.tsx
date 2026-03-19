import { useState } from 'react';
import { AxiosError } from 'axios';
import { Link, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { billingApi, playbooksApi, workspacesApi } from '../../utils/api';
import { useAuth } from '../../contexts/AuthContext';
import { trackAcquisitionEvent } from '../../lib/analytics';
import { getTrialDisclosureVariant, type TrialDisclosureVariant } from '../../lib/experiments';
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
  Users,
  Copy,
} from 'lucide-react';
import type {
  PlaybookListItem,
  PlaybookCreate,
  WorkspaceSharedPlaybook,
  WorkspaceSummary,
} from '../../types';
import styles from './Dashboard.module.css';

export function Dashboard() {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [reviewStatusFilter, setReviewStatusFilter] = useState<string>('');
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [isLimitError, setIsLimitError] = useState(false);
  const navigate = useNavigate();
  const trialDisclosureVariant = getTrialDisclosureVariant();

  const queryClient = useQueryClient();
  const { user, isAuthenticated, isLoading: isAuthLoading } = useAuth();
  const hasPaidAccess =
    user?.subscription_status === 'active' &&
    !!user.subscription_tier &&
    user.subscription_tier !== 'free';
  const workspacesQuery = useQuery({
    queryKey: ['workspaces', isAuthenticated],
    queryFn: () => workspacesApi.list(),
    enabled: !isAuthLoading && isAuthenticated,
  });
  const registryWorkspace =
    workspacesQuery.data?.find((workspace) => workspace.plan !== 'personal') ?? null;
  const registryWorkspaceId = registryWorkspace?.id ?? 'me';
  const entitlementsQuery = useQuery({
    queryKey: ['workspace-entitlements', registryWorkspaceId],
    queryFn: () => workspacesApi.getEntitlements(registryWorkspaceId),
    enabled: !isAuthLoading && isAuthenticated && hasPaidAccess,
  });
  const sharedRegistryEnabled =
    entitlementsQuery.data?.entitlements.shared_workspace === true;
  const sharedPlaybooksQuery = useQuery({
    queryKey: ['workspace-shared-playbooks', registryWorkspaceId],
    queryFn: () => workspacesApi.listSharedPlaybooks(registryWorkspaceId, 1, 24),
    enabled:
      !isAuthLoading &&
      isAuthenticated &&
      hasPaidAccess &&
      sharedRegistryEnabled,
  });

  const { data, isLoading, error } = useQuery({
    queryKey: ['playbooks', reviewStatusFilter, isAuthenticated, hasPaidAccess],
    queryFn: () => playbooksApi.list(1, 50, reviewStatusFilter || undefined),
    enabled: !isAuthLoading && isAuthenticated && hasPaidAccess,
    staleTime: 0, // Always consider data stale to ensure fresh fetches
  });

  const errorStatus = error instanceof AxiosError ? error.response?.status : undefined;
  const shouldShowSubscriptionState = !hasPaidAccess || errorStatus === 402;
  const playbookCount = data?.items.length ?? 0;

  const createMutation = useMutation({
    mutationFn: (newPlaybook: PlaybookCreate) => playbooksApi.create(newPlaybook),
    onSuccess: () => {
      if (playbookCount === 0) {
        trackAcquisitionEvent('first_playbook_created', {
          source: 'dashboard_create_modal',
        });
      }
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      setShowCreateModal(false);
      setMutationError(null);
      setIsLimitError(false);
    },
    onError: (err: unknown) => {
      const axiosErr = err as AxiosError<{ detail?: string; error?: { message?: string } }>;
      const status = axiosErr?.response?.status;
      const message =
        axiosErr?.response?.data?.detail ||
        axiosErr?.response?.data?.error?.message;
      if (status === 402 && message) {
        setMutationError(message);
        setIsLimitError(true);
      } else {
        setMutationError('Failed to create playbook. Please try again.');
        setIsLimitError(false);
      }
    },
  });

  const reuseMutation = useMutation({
    mutationFn: (playbookId: string) => workspacesApi.reuseSharedPlaybook(registryWorkspaceId, playbookId),
    onSuccess: (playbook) => {
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      setMutationError(null);
      setIsLimitError(false);
      navigate(`/playbooks/${playbook.id}`);
    },
    onError: (err: unknown) => {
      const axiosErr = err as AxiosError<{ detail?: string; error?: { message?: string } }>;
      const status = axiosErr?.response?.status;
      const message =
        axiosErr?.response?.data?.detail ||
        axiosErr?.response?.data?.error?.message;
      if (status === 402 && message) {
        setMutationError(message);
        setIsLimitError(true);
      } else {
        setMutationError(message || 'Failed to reuse shared playbook. Please try again.');
        setIsLimitError(false);
      }
    },
  });

  const filteredPlaybooks = data?.items.filter((pb) =>
    pb.name.toLowerCase().includes(searchQuery.toLowerCase())
  );
  const filteredSharedPlaybooks = sharedPlaybooksQuery.data?.items.filter((playbook) =>
    playbook.name.toLowerCase().includes(searchQuery.toLowerCase())
  );
  const showSharedRegistry =
    sharedRegistryEnabled &&
    (reviewStatusFilter === '' || reviewStatusFilter === 'approved');

  // Check if trial user is at playbook limit
  const isOnTrial = !!user?.trial_ends_at && new Date(user.trial_ends_at) > new Date();
  const atPlaybookLimit = isOnTrial && playbookCount >= 1;

  const handleNewPlaybookClick = () => {
    if (atPlaybookLimit) {
      setMutationError(
        "You've reached the maximum of 1 playbook(s) included in your free trial. " +
        "Subscribe to a paid plan to create more playbooks."
      );
      setIsLimitError(true);
    } else {
      setShowCreateModal(true);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerContent}>
          <h1>Playbooks</h1>
          <p>Living documentation that evolves with your outcomes</p>
        </div>
        <SubscriptionGate featureName="Playbooks">
          <Button icon={<Plus size={18} />} onClick={handleNewPlaybookClick}>
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
            value={reviewStatusFilter}
            onChange={(e) => setReviewStatusFilter(e.target.value)}
            className={styles.filterSelect}
            aria-label="Filter by review status"
          >
            <option value="">All Review States</option>
            <option value="draft">Draft</option>
            <option value="proposed">Proposed</option>
            <option value="approved">Approved</option>
            <option value="archived">Archived</option>
          </select>
        </div>
      </div>

      {/* Mutation Error */}
      {mutationError && (
        <div className={styles.mutationError}>
          <AlertCircle size={20} />
          <span>{mutationError}</span>
          {isLimitError && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => navigate('/pricing')}
            >
              View Plans
            </Button>
          )}
          <button
            className={styles.dismissError}
            onClick={() => { setMutationError(null); setIsLimitError(false); }}
            aria-label="Dismiss error"
          >
            &times;
          </button>
        </div>
      )}

      {showSharedRegistry && (
        <SharedRegistrySection
          workspace={registryWorkspace}
          isLoading={sharedPlaybooksQuery.isLoading || entitlementsQuery.isLoading}
          playbooks={filteredSharedPlaybooks ?? []}
          onReuse={(playbookId) => reuseMutation.mutate(playbookId)}
          activeReusePlaybookId={reuseMutation.isPending ? reuseMutation.variables : null}
        />
      )}

      {/* Content */}
      {isAuthLoading || isLoading ? (
        <div className={styles.loading}>
          <div className={styles.spinner} />
          <span>Loading playbooks...</span>
        </div>
      ) : shouldShowSubscriptionState ? (
        <SubscriptionRequiredState
          hasUsedTrial={user?.has_used_trial ?? false}
          trialDisclosureVariant={trialDisclosureVariant}
          onUpgradeClick={() => navigate('/pricing')}
        />
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

function SubscriptionRequiredState({
  onUpgradeClick,
  hasUsedTrial,
  trialDisclosureVariant,
}: {
  onUpgradeClick: () => void;
  hasUsedTrial: boolean;
  trialDisclosureVariant: TrialDisclosureVariant;
}) {
  const [isStartingTrial, setIsStartingTrial] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handlePrimaryAction = async () => {
    if (hasUsedTrial) {
      onUpgradeClick();
      return;
    }

    setIsStartingTrial(true);
    setError(null);
    try {
      trackAcquisitionEvent('trial_checkout_intent', {
        source: 'dashboard_subscription_state',
      });
      const result = await billingApi.startStarterTrial();
      if (result.success && result.checkout_url) {
        window.location.href = result.checkout_url;
        return;
      }
      setError(result.message || 'Failed to start your trial. Please try again.');
    } catch {
      setError('Failed to start your trial. Please try again.');
    } finally {
      setIsStartingTrial(false);
    }
  };

  return (
    <div className={styles.emptyState}>
      <div className={styles.emptyIcon}>
        <AlertCircle size={48} />
      </div>
      <h2>{hasUsedTrial ? 'Upgrade to Continue' : 'Start Your Free Trial'}</h2>
      <p>
        {hasUsedTrial
          ? 'Your free trial has ended. Upgrade to continue creating and evolving playbooks.'
          : trialDisclosureVariant === 'control'
            ? 'Start your 7-day free trial to access playbooks. Card required, no charge today. Trial includes 1 playbook and 5 evolutions.'
            : 'Start your 7-day free trial to access playbooks. Trial includes 1 playbook and 5 evolutions. Card is required before your trial starts.'}
      </p>
      {error && (
        <div className={styles.trialError}>
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}
      <div className={styles.subscriptionActions}>
        <Button onClick={handlePrimaryAction} isLoading={isStartingTrial}>
          {hasUsedTrial ? 'View Plans' : 'Start Free Trial'}
        </Button>
        {!hasUsedTrial && (
          <Button variant="ghost" onClick={onUpgradeClick} disabled={isStartingTrial}>
            See all plans
          </Button>
        )}
      </div>
    </div>
  );
}

function PlaybookCard({ playbook }: { playbook: PlaybookListItem }) {
  const reviewStatusIcon = {
    draft: <Clock size={14} className={styles.statusDraft} />,
    proposed: <AlertCircle size={14} className={styles.statusProposed} />,
    approved: <CheckCircle2 size={14} className={styles.statusApproved} />,
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
            {reviewStatusIcon[playbook.review_status]}
            <span>{playbook.review_status}</span>
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
          <span>
            Review updated {formatRelativeTime(playbook.review_status_updated_at || playbook.updated_at)}
          </span>
        </div>
      </Card>
    </Link>
  );
}

function SharedRegistrySection({
  workspace,
  isLoading,
  playbooks,
  onReuse,
  activeReusePlaybookId,
}: {
  workspace: WorkspaceSummary | null;
  isLoading: boolean;
  playbooks: WorkspaceSharedPlaybook[];
  onReuse: (playbookId: string) => void;
  activeReusePlaybookId: string | null;
}) {
  return (
    <section className={styles.section}>
      <div className={styles.sectionHeader}>
        <div>
          <span className={styles.sectionEyebrow}>Shared Registry</span>
          <h2>Approved team playbooks</h2>
          <p>
            {workspace
              ? `Browse approved playbooks from ${workspace.name} and copy them into your library.`
              : 'Browse approved team playbooks and copy them into your library.'}
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className={styles.sectionState}>
          <div className={styles.spinner} />
          <span>Loading shared registry...</span>
        </div>
      ) : playbooks.length === 0 ? (
        <div className={styles.sectionState}>
          <Users size={20} />
          <span>No approved team playbooks are shared yet.</span>
        </div>
      ) : (
        <div className={styles.grid}>
          {playbooks.map((playbook) => (
            <SharedPlaybookCard
              key={playbook.id}
              playbook={playbook}
              onReuse={onReuse}
              isReusing={activeReusePlaybookId === playbook.id}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function SharedPlaybookCard({
  playbook,
  onReuse,
  isReusing,
}: {
  playbook: WorkspaceSharedPlaybook;
  onReuse: (playbookId: string) => void;
  isReusing: boolean;
}) {
  return (
    <Card variant="default" className={styles.card}>
      <div className={styles.cardHeader}>
        <div className={styles.cardIcon}>
          <Users size={20} />
        </div>
        <span className={styles.ownerBadge}>
          {playbook.is_owned_by_current_user ? 'You' : playbook.owner.email}
        </span>
      </div>

      <span className={styles.cardEyebrow}>Approved team playbook</span>
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
          <Copy size={14} />
          <span>{playbook.is_owned_by_current_user ? 'Already yours' : 'Ready to reuse'}</span>
        </div>
      </div>

      <div className={styles.sharedCardActions}>
        <div className={styles.cardFooter}>
          <Clock size={14} />
          <span>Updated {formatRelativeTime(playbook.updated_at)}</span>
        </div>
        <Button
          size="sm"
          variant={playbook.is_owned_by_current_user ? 'ghost' : 'secondary'}
          onClick={() => onReuse(playbook.id)}
          isLoading={isReusing}
          disabled={playbook.is_owned_by_current_user}
        >
          {playbook.is_owned_by_current_user ? 'In your library' : 'Reuse'}
        </Button>
      </div>
    </Card>
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
