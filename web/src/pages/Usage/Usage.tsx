import { type ReactNode } from 'react';
import { AxiosError } from 'axios';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { useAuth } from '../../contexts/AuthContext';
import { evolutionsApi, workspacesApi } from '../../utils/api';
import {
  AlertCircle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  CreditCard,
  Gauge,
  Rocket,
  Sparkles,
  TriangleAlert,
} from 'lucide-react';
import type {
  DailyEvolution,
  EvolutionSummary,
  PlaybookEvolutionStats,
  WorkspaceEntitlements,
} from '../../types';
import styles from './Usage.module.css';

export function Usage() {
  const { user, isLoading: isAuthLoading } = useAuth();
  const queryClient = useQueryClient();

  const entitlementsQuery = useQuery<WorkspaceEntitlements>({
    queryKey: ['workspace-entitlements', 'me'],
    queryFn: workspacesApi.getEntitlements,
    enabled: !isAuthLoading,
  });

  const hasFeatureAccess = entitlementsQuery.data?.access.has_feature_access ?? false;

  const summaryQuery = useQuery<EvolutionSummary>({
    queryKey: ['usage-activity-summary'],
    queryFn: evolutionsApi.getSummary,
    enabled: !isAuthLoading && hasFeatureAccess,
  });

  const dailyQuery = useQuery<DailyEvolution[]>({
    queryKey: ['usage-activity-daily'],
    queryFn: () => evolutionsApi.getDaily(30),
    enabled: !isAuthLoading && hasFeatureAccess,
  });

  const playbookQuery = useQuery<PlaybookEvolutionStats[]>({
    queryKey: ['usage-activity-playbooks'],
    queryFn: () => evolutionsApi.getByPlaybook(5),
    enabled: !isAuthLoading && hasFeatureAccess,
  });

  const upgradeWorkspaceMutation = useMutation({
    mutationFn: () => workspacesApi.upgradePersonalToTeam(),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['workspace-entitlements', 'me'] });
    },
  });

  const detailErrors = [summaryQuery.error, dailyQuery.error, playbookQuery.error];
  const hasSubscriptionError = detailErrors.some(
    (error) => error instanceof AxiosError && error.response?.status === 402
  );
  const hasDetailError = detailErrors.some(
    (error) => !!error && !(error instanceof AxiosError && error.response?.status === 402)
  );

  const isLoading =
    isAuthLoading ||
    entitlementsQuery.isLoading ||
    (hasFeatureAccess &&
      (summaryQuery.isLoading || dailyQuery.isLoading || playbookQuery.isLoading));

  const handleRetry = () => {
    void entitlementsQuery.refetch();
    void summaryQuery.refetch();
    void dailyQuery.refetch();
    void playbookQuery.refetch();
  };

  if (isLoading) {
    return (
      <div className={styles.container}>
        <div className={styles.loading}>
          <div className={styles.spinner} />
          <span>Loading usage overview...</span>
        </div>
      </div>
    );
  }

  if (entitlementsQuery.isError || !entitlementsQuery.data) {
    return (
      <div className={styles.container}>
        <ErrorState
          title="Couldn't Load Usage"
          description="Something went wrong while loading plan usage and limits. Please try again."
          onRetry={handleRetry}
        />
      </div>
    );
  }

  const entitlements = entitlementsQuery.data;
  const usage = entitlements.usage_limits;
  const summary = summaryQuery.data;
  const dailyEvolutions = dailyQuery.data ?? [];
  const playbookStats = playbookQuery.data ?? [];
  const showActivityDetails = hasFeatureAccess && !hasSubscriptionError && !hasDetailError;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>Usage</h1>
        <p>See what your plan includes, what you have consumed, and what happens when you hit limits.</p>
      </div>

      <div className={styles.accountGrid}>
        <Card variant="default" padding="lg" className={styles.accountCard}>
          <div className={styles.chartHeader}>
            <h3>Plan Access</h3>
            <span className={`${styles.statusPill} ${styles[resolveUsageTone(entitlements)]}`}>
              {formatPlanHeadline(entitlements)}
            </span>
          </div>
          <div className={styles.accountList}>
            <AccountMetric label="Workspace plan" value={formatWorkspacePlan(entitlements.plan)} />
            <AccountMetric
              label="Billing state"
              value={formatStatus(entitlements.access.subscription_status)}
            />
            <AccountMetric
              label="Hosted access"
              value={entitlements.access.has_feature_access ? 'Active' : 'Upgrade required'}
            />
            <AccountMetric
              label="Trial policy"
              value={getTrialLabel(entitlements)}
            />
          </div>
        </Card>

        <Card variant="default" padding="lg" className={styles.accountCard}>
          <div className={styles.chartHeader}>
            <h3>Included With This Plan</h3>
          </div>
          <div className={styles.accountList}>
            <AccountMetric
              label="Hosted evolutions"
              value={`${formatLimit(usage.monthly_evolution_runs)} / month`}
            />
            <AccountMetric
              label="Playbooks"
              value={formatLimit(usage.max_playbooks)}
            />
            <AccountMetric
              label="Managed budget"
              value={formatMoneyLimit(usage.monthly_cost_limit_usd)}
            />
            <AccountMetric
              label="Premium models"
              value={usage.max_playbooks === null || entitlements.access.effective_tier !== 'free'
                ? 'Included'
                : 'Not included'}
            />
          </div>
        </Card>
      </div>

      <div className={styles.summaryGrid}>
        <SummaryCard
          icon={<CreditCard />}
          label="Current Plan"
          value={formatPlanHeadline(entitlements)}
          color="primary"
        />
        <SummaryCard
          icon={<Rocket />}
          label="Included Evolutions"
          value={formatLimit(usage.monthly_evolution_runs)}
          color="primary"
        />
        <SummaryCard
          icon={<Gauge />}
          label="Used This Month"
          value={formatInteger(usage.current_evolution_runs)}
          color="primary"
        />
        <SummaryCard
          icon={usage.limit_exceeded ? <TriangleAlert /> : <CheckCircle2 />}
          label="Remaining This Month"
          value={formatLimit(usage.remaining_evolution_runs)}
          color={usage.limit_exceeded ? 'error' : 'success'}
        />
      </div>

      <div className={styles.noticeGrid}>
        <PlanStatusCard
          entitlements={entitlements}
          hasUsedTrial={!!user?.has_used_trial}
          isUpgradingWorkspace={upgradeWorkspaceMutation.isPending}
          upgradeWorkspaceError={upgradeWorkspaceMutation.error}
          onUpgradeWorkspace={() => upgradeWorkspaceMutation.mutate()}
        />
        <UsageEnvelopeCard entitlements={entitlements} />
      </div>

      {hasDetailError ? (
        <InlineNotice
          title="Couldn't load detailed activity"
          description="The plan overview is current, but the 30-day evolution breakdown did not load."
          onRetry={handleRetry}
        />
      ) : showActivityDetails ? (
        <>
          <div className={styles.contentGrid}>
            <Card variant="default" padding="lg" className={styles.chartCard}>
              <div className={styles.chartHeader}>
                <h3>Evolution Activity</h3>
                <span className={styles.chartPeriod}>Last 30 days</span>
              </div>
              <div className={styles.chart}>
                {dailyEvolutions.length > 0 ? (
                  <EvolutionChart data={dailyEvolutions} />
                ) : (
                  <div className={styles.noData}>
                    <AlertCircle size={24} />
                    <span>No hosted evolutions recorded this period</span>
                  </div>
                )}
              </div>
            </Card>

            <Card variant="default" padding="lg" className={styles.playbookCard}>
              <div className={styles.chartHeader}>
                <h3>Most Active Playbooks</h3>
              </div>
              <div className={styles.playbookList}>
                {playbookStats.length > 0 ? (
                  playbookStats.map((stats) => (
                    <PlaybookActivityItem key={stats.playbook_id} stats={stats} />
                  ))
                ) : (
                  <div className={styles.noData}>
                    <BookOpen size={24} />
                    <span>No playbook usage yet</span>
                  </div>
                )}
              </div>
            </Card>
          </div>

          {summary && (
            <div className={styles.periodInfo}>
              <span>
                Showing detailed activity from {new Date(summary.start_date).toLocaleDateString()} to{' '}
                {new Date(summary.end_date).toLocaleDateString()}
              </span>
            </div>
          )}
        </>
      ) : (
        <DetailLockedState hasUsedTrial={!!user?.has_used_trial} />
      )}
    </div>
  );
}

interface SummaryCardProps {
  icon: ReactNode;
  label: string;
  value: string;
  color: 'primary' | 'success' | 'error';
}

function SummaryCard({ icon, label, value, color }: SummaryCardProps) {
  return (
    <Card variant="default" className={styles.summaryCard}>
      <div className={`${styles.summaryIcon} ${styles[color]}`}>{icon}</div>
      <div className={styles.summaryContent}>
        <span className={styles.summaryLabel}>{label}</span>
        <span className={styles.summaryValue}>{value}</span>
      </div>
    </Card>
  );
}

function UsageEnvelopeCard({ entitlements }: { entitlements: WorkspaceEntitlements }) {
  const usage = entitlements.usage_limits;
  const evolutionLabel = usage.remaining_evolution_runs === null
    ? 'Unlimited on this plan'
    : `${formatInteger(usage.current_evolution_runs)} used · ${formatLimit(
        usage.remaining_evolution_runs
      )} remaining`;

  const budgetLabel = usage.remaining_cost_usd === null
    ? 'Unlimited on this plan'
    : `${formatCurrency(toNumber(usage.current_cost_usd))} used · ${formatCurrency(
        toNumber(usage.remaining_cost_usd)
      )} remaining`;

  return (
    <Card variant="default" padding="lg" className={styles.noticeCard}>
      <div className={styles.chartHeader}>
        <h3>Consumed This Period</h3>
      </div>
      <div className={styles.meterList}>
        <ProgressMeter
          label="Hosted evolutions"
          current={usage.current_evolution_runs}
          total={usage.monthly_evolution_runs}
          helper={evolutionLabel}
          formatter={formatInteger}
        />
        <ProgressMeter
          label="Managed usage budget"
          current={toNumber(usage.current_cost_usd)}
          total={toNullableNumber(usage.monthly_cost_limit_usd)}
          helper={budgetLabel}
          formatter={formatCurrency}
        />
      </div>
      <div className={styles.planHighlights}>
        <FeatureChip label={`${formatLimit(usage.max_playbooks)} playbooks`} />
        <FeatureChip label={`${formatInteger(usage.current_total_tokens)} tokens recorded`} />
        <FeatureChip label={entitlements.access.has_feature_access ? 'Hosted access active' : 'Hosted access locked'} />
      </div>
    </Card>
  );
}

function ProgressMeter({
  label,
  current,
  total,
  helper,
  formatter,
}: {
  label: string;
  current: number;
  total: number | null;
  helper: string;
  formatter: (value: number) => string;
}) {
  const width = total === null || total <= 0 ? 100 : Math.min(100, (current / total) * 100);

  return (
    <div className={styles.meterRow}>
      <div className={styles.meterHeader}>
        <span className={styles.meterLabel}>{label}</span>
        <span className={styles.meterValue}>
          {total === null ? `${formatter(current)} used` : `${formatter(current)} / ${formatter(total)}`}
        </span>
      </div>
      <div className={styles.meterTrack} aria-hidden="true">
        <div className={styles.meterFill} style={{ width: `${width}%` }} />
      </div>
      <span className={styles.meterHelper}>{helper}</span>
    </div>
  );
}

function PlanStatusCard({
  entitlements,
  hasUsedTrial,
  isUpgradingWorkspace,
  upgradeWorkspaceError,
  onUpgradeWorkspace,
}: {
  entitlements: WorkspaceEntitlements;
  hasUsedTrial: boolean;
  isUpgradingWorkspace: boolean;
  upgradeWorkspaceError: Error | null;
  onUpgradeWorkspace: () => void;
}) {
  const navigate = useNavigate();
  const tone = resolveUsageTone(entitlements);
  const copy = getUsageCopy(entitlements, hasUsedTrial);
  const canUpgradeWorkspace = entitlements.plan === 'personal';

  return (
    <Card variant="default" padding="lg" className={`${styles.noticeCard} ${styles.noticeTone} ${styles[tone]}`}>
      <div className={styles.statusHeader}>
        <div className={`${styles.statusIcon} ${styles[tone]}`}>
          {tone === 'success' ? <Sparkles size={18} /> : <TriangleAlert size={18} />}
        </div>
        <div>
          <h3>{copy.title}</h3>
          <p>{copy.description}</p>
        </div>
      </div>
      <div className={styles.noticeActions}>
        {canUpgradeWorkspace && (
          <Button
            variant="secondary"
            onClick={onUpgradeWorkspace}
            disabled={isUpgradingWorkspace}
          >
            {isUpgradingWorkspace ? 'Upgrading Workspace...' : 'Upgrade Workspace To Team'}
          </Button>
        )}
        <Button
          variant={tone === 'success' ? 'secondary' : 'primary'}
          onClick={() => navigate(copy.primaryHref)}
          icon={<ArrowRight size={16} />}
        >
          {copy.primaryAction}
        </Button>
        <Button variant="ghost" onClick={() => navigate('/playbooks')}>
          Review Playbooks
        </Button>
      </div>
      {upgradeWorkspaceError && (
        <p>{extractMutationError(upgradeWorkspaceError, 'Could not upgrade this workspace right now.')}</p>
      )}
    </Card>
  );
}

function InlineNotice({
  title,
  description,
  onRetry,
}: {
  title: string;
  description: string;
  onRetry: () => void;
}) {
  return (
    <Card variant="default" padding="lg" className={styles.inlineNotice}>
      <div className={styles.statusHeader}>
        <div className={`${styles.statusIcon} ${styles.warning}`}>
          <AlertCircle size={18} />
        </div>
        <div>
          <h3>{title}</h3>
          <p>{description}</p>
        </div>
      </div>
      <div className={styles.noticeActions}>
        <Button variant="secondary" onClick={onRetry}>
          Retry
        </Button>
      </div>
    </Card>
  );
}

function DetailLockedState({ hasUsedTrial }: { hasUsedTrial: boolean }) {
  const navigate = useNavigate();

  return (
    <Card variant="default" padding="lg" className={styles.inlineNotice}>
      <div className={styles.statusHeader}>
        <div className={`${styles.statusIcon} ${styles.warning}`}>
          <AlertCircle size={18} />
        </div>
        <div>
          <h3>Detailed hosted activity unlocks after upgrade</h3>
          <p>
            This page already shows your plan allowance and current usage. Start a trial or upgrade
            to unlock the 30-day evolution chart and per-playbook breakdown.
          </p>
        </div>
      </div>
      <div className={styles.noticeActions}>
        <Button
          variant="primary"
          onClick={() => navigate('/pricing')}
          icon={<ArrowRight size={16} />}
        >
          {hasUsedTrial ? 'View Pricing' : 'Start Free Trial'}
        </Button>
      </div>
    </Card>
  );
}

function EvolutionChart({ data }: { data: DailyEvolution[] }) {
  const chartData = data.slice(-14);

  if (chartData.length === 0) {
    return null;
  }

  const maxEvolutions = Math.max(...chartData.map((day) => day.total_evolutions), 1);

  return (
    <div className={styles.barChart}>
      {chartData.map((day, index) => {
        const completedHeight = maxEvolutions > 0 ? (day.completed / maxEvolutions) * 100 : 0;
        const failedHeight = maxEvolutions > 0 ? (day.failed / maxEvolutions) * 100 : 0;
        const runningHeight = maxEvolutions > 0 ? (day.running / maxEvolutions) * 100 : 0;
        const date = new Date(day.date);
        const dayLabel = date.toLocaleDateString('en-US', { weekday: 'short' });

        return (
          <div key={day.date} className={styles.barColumn}>
            <div className={styles.barWrapper}>
              {day.total_evolutions > 0 ? (
                <div className={styles.stackedBar}>
                  {day.completed > 0 && (
                    <div
                      className={`${styles.bar} ${styles.completed}`}
                      style={{
                        height: `${completedHeight}%`,
                        animationDelay: `${index * 50}ms`,
                      }}
                      title={`${day.completed} completed`}
                    />
                  )}
                  {day.failed > 0 && (
                    <div
                      className={`${styles.bar} ${styles.failed}`}
                      style={{
                        height: `${failedHeight}%`,
                        animationDelay: `${index * 50 + 25}ms`,
                      }}
                      title={`${day.failed} failed`}
                    />
                  )}
                  {day.running > 0 && (
                    <div
                      className={`${styles.bar} ${styles.running}`}
                      style={{
                        height: `${runningHeight}%`,
                        animationDelay: `${index * 50 + 50}ms`,
                      }}
                      title={`${day.running} running`}
                    />
                  )}
                </div>
              ) : (
                <div className={styles.emptyBar} />
              )}
            </div>
            <span className={styles.barLabel}>{dayLabel}</span>
          </div>
        );
      })}
    </div>
  );
}

function PlaybookActivityItem({ stats }: { stats: PlaybookEvolutionStats }) {
  const navigate = useNavigate();
  const timeSince = stats.last_evolution_at ? formatTimeAgo(new Date(stats.last_evolution_at)) : 'Never';

  return (
    <div className={styles.playbookItem} onClick={() => navigate(`/playbooks/${stats.playbook_id}`)}>
      <div className={styles.playbookIcon}>
        <BookOpen size={16} />
      </div>
      <div className={styles.playbookInfo}>
        <span className={styles.playbookName}>{stats.playbook_name}</span>
        <span className={styles.playbookStats}>
          {formatInteger(stats.total_evolutions)} evolution{stats.total_evolutions !== 1 ? 's' : ''} ·{' '}
          {Math.round(stats.success_rate * 100)}% success
        </span>
        <span className={styles.playbookLastRun}>Last run: {timeSince}</span>
      </div>
    </div>
  );
}

function ErrorState({
  title,
  description,
  onRetry,
}: {
  title: string;
  description: string;
  onRetry: () => void;
}) {
  return (
    <div className={styles.emptyState}>
      <div className={styles.emptyIcon}>
        <AlertCircle size={48} />
      </div>
      <h2>{title}</h2>
      <p>{description}</p>
      <button className={styles.emptyButton} onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}

function FeatureChip({ label }: { label: string }) {
  return <span className={styles.featureChip}>{label}</span>;
}

function AccountMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.accountMetric}>
      <span className={styles.accountLabel}>{label}</span>
      <span className={styles.accountValue}>{value}</span>
    </div>
  );
}

function resolveUsageTone(entitlements: WorkspaceEntitlements): 'success' | 'warning' | 'error' {
  const usage = entitlements.usage_limits;

  if (!entitlements.access.has_feature_access || entitlements.access.is_trialing) {
    return 'warning';
  }

  if (usage.limit_exceeded) {
    return 'error';
  }

  if (
    isApproachingLimit(usage.current_evolution_runs, usage.monthly_evolution_runs) ||
    isApproachingLimit(toNumber(usage.current_cost_usd), toNullableNumber(usage.monthly_cost_limit_usd))
  ) {
    return 'warning';
  }

  return 'success';
}

function getUsageCopy(entitlements: WorkspaceEntitlements, hasUsedTrial: boolean) {
  const usage = entitlements.usage_limits;
  const pricingAction = hasUsedTrial ? 'View Pricing' : 'Start Free Trial';

  if (!entitlements.access.has_feature_access) {
    return {
      title: 'Hosted usage is mapped, but hosted runs stay locked until upgrade',
      description: `This account is on the ${formatPlanHeadline(
        entitlements
      )} path with ${formatLimit(usage.monthly_evolution_runs)} included evolutions and ${formatLimit(
        usage.max_playbooks
      )} playbooks once hosted access is active.`,
      primaryAction: pricingAction,
      primaryHref: '/pricing',
    };
  }

  if (entitlements.access.is_trialing) {
    return {
      title: 'Trial access is active with the free allowance envelope',
      description: `Trial accounts keep the hosted experience active, but limits stay capped at ${formatLimit(
        usage.monthly_evolution_runs
      )} evolutions and ${formatLimit(usage.max_playbooks)} playbook${
        usage.max_playbooks === 1 ? '' : 's'
      } until the paid cycle begins.`,
      primaryAction: 'View Pricing',
      primaryHref: '/pricing',
    };
  }

  if (usage.limit_exceeded === 'monthly_cost_limit') {
    return {
      title: 'Managed usage budget reached',
      description: `You have used ${formatCurrency(toNumber(usage.current_cost_usd))} of ${formatMoneyLimit(
        usage.monthly_cost_limit_usd
      )}. Hosted evolutions pause until the next billing cycle or an upgrade.`,
      primaryAction: 'Upgrade Plan',
      primaryHref: '/pricing',
    };
  }

  if (usage.limit_exceeded === 'monthly_evolution_runs') {
    return {
      title: 'Monthly evolution limit reached',
      description: `You have used all ${formatLimit(
        usage.monthly_evolution_runs
      )} included hosted evolutions for this billing period. New hosted evolutions are blocked until the cycle resets or you upgrade.`,
      primaryAction: 'Upgrade Plan',
      primaryHref: '/pricing',
    };
  }

  if (
    isApproachingLimit(
      toNumber(usage.current_cost_usd),
      toNullableNumber(usage.monthly_cost_limit_usd)
    )
  ) {
    return {
      title: 'Approaching your managed usage budget',
      description: `You have ${formatMoneyLimit(
        usage.remaining_cost_usd
      )} remaining in the managed usage budget for this period. Upgrade now to avoid blocked hosted runs when the budget cap is reached.`,
      primaryAction: 'Upgrade Before You Hit The Limit',
      primaryHref: '/pricing',
    };
  }

  if (isApproachingLimit(usage.current_evolution_runs, usage.monthly_evolution_runs)) {
    return {
      title: 'Approaching your monthly evolution limit',
      description: `You have ${formatLimit(
        usage.remaining_evolution_runs
      )} hosted evolution${usage.remaining_evolution_runs === 1 ? '' : 's'} remaining this period. Upgrade now to avoid blocked runs at the limit.`,
      primaryAction: 'Upgrade Before You Hit The Limit',
      primaryHref: '/pricing',
    };
  }

  return {
    title: 'Within plan limits',
    description: `You are using ${formatInteger(usage.current_evolution_runs)} of ${formatLimit(
      usage.monthly_evolution_runs
    )} included evolutions this period. When you hit a cap, hosted evolutions pause here and this page will point you to the right upgrade path.`,
    primaryAction: 'Review Plans',
    primaryHref: '/pricing',
  };
}

function extractMutationError(error: Error, fallback: string) {
  if (error instanceof AxiosError) {
    const message = error.response?.data?.error?.message;
    if (typeof message === 'string' && message.trim()) {
      return message;
    }
  }

  return fallback;
}

function isApproachingLimit(current: number, total: number | null) {
  if (total === null || total <= 0) {
    return false;
  }

  const remaining = total - current;
  const threshold = Math.max(1, Math.ceil(total * 0.2));
  return remaining > 0 && remaining <= threshold;
}

function formatInteger(value: number) {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(value);
}

function formatCurrency(value: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function formatLimit(value: number | null) {
  if (value === null) {
    return 'Unlimited';
  }

  return formatInteger(value);
}

function formatMoneyLimit(value: string | number | null) {
  if (value === null) {
    return 'Unlimited';
  }

  return formatCurrency(toNumber(value));
}

function formatPlanHeadline(entitlements: WorkspaceEntitlements) {
  const tier = entitlements.access.subscription_tier;

  if (entitlements.access.is_trialing && tier && tier !== 'free') {
    return `${formatLabel(tier)} Trial`;
  }

  if (!tier || tier === 'free') {
    return 'Free';
  }

  return formatLabel(tier);
}

function formatWorkspacePlan(plan: string) {
  return formatLabel(plan);
}

function formatStatus(status: string | undefined) {
  if (!status || status === 'none') {
    return 'Not subscribed';
  }

  return status
    .split('_')
    .map(formatLabel)
    .join(' ');
}

function formatLabel(value: string) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function getTrialLabel(entitlements: WorkspaceEntitlements) {
  if (!entitlements.access.is_trialing) {
    return 'No trial active';
  }

  return `${formatLimit(entitlements.usage_limits.monthly_evolution_runs)} evolutions / ${formatLimit(
    entitlements.usage_limits.max_playbooks
  )} playbooks`;
}

function formatTimeAgo(date: Date): string {
  const now = new Date();
  const diffInSeconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (diffInSeconds < 60) {
    return 'just now';
  }

  const diffInMinutes = Math.floor(diffInSeconds / 60);
  if (diffInMinutes < 60) {
    return `${diffInMinutes} minute${diffInMinutes !== 1 ? 's' : ''} ago`;
  }

  const diffInHours = Math.floor(diffInMinutes / 60);
  if (diffInHours < 24) {
    return `${diffInHours} hour${diffInHours !== 1 ? 's' : ''} ago`;
  }

  const diffInDays = Math.floor(diffInHours / 24);
  if (diffInDays < 7) {
    return `${diffInDays} day${diffInDays !== 1 ? 's' : ''} ago`;
  }

  return date.toLocaleDateString();
}

function toNumber(value: string | number) {
  if (typeof value === 'number') {
    return value;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function toNullableNumber(value: string | number | null) {
  if (value === null) {
    return null;
  }

  return toNumber(value);
}
