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
  Cpu,
  FlaskConical,
  Gauge,
  HardDrive,
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
    queryFn: () => workspacesApi.getEntitlements(),
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
  const usageAlerts = buildUsageAlerts(usage);
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
              label="Hosted storage"
              value={formatCounterLimit(usage.storage_bytes.hard_limit, formatBytes)}
            />
            <AccountMetric
              label="Hosted evals"
              value={`${formatCounterLimit(usage.hosted_eval_runs.hard_limit ?? usage.monthly_evolution_runs, formatInteger)} / month`}
            />
            <AccountMetric
              label="Managed requests"
              value={formatCounterLimit(usage.managed_inference_requests.hard_limit, formatInteger)}
            />
            <AccountMetric
              label="Managed tokens"
              value={formatCounterLimit(usage.managed_inference_tokens.hard_limit, formatInteger)}
            />
          </div>
        </Card>
      </div>

      {usageAlerts.length > 0 ? (
        <Card variant="default" className={styles.alertCard}>
          <div className={styles.alertHeader}>
            <AlertCircle size={18} />
            <span>Usage attention needed</span>
          </div>
          <div className={styles.alertList}>
            {usageAlerts.map((alert) => (
              <span key={alert}>{alert}</span>
            ))}
          </div>
        </Card>
      ) : null}

      <div className={styles.summaryGrid}>
        <SummaryCard
          icon={<HardDrive />}
          label="Hosted Storage"
          value={formatUsageWithLimit(
            usage.storage_bytes.current,
            usage.storage_bytes.hard_limit,
            formatBytes
          )}
          color={usage.storage_bytes.status === 'blocked' ? 'error' : usage.storage_bytes.status === 'warning' ? 'primary' : 'success'}
        />
        <SummaryCard
          icon={<FlaskConical />}
          label="Hosted Evals"
          value={formatUsageWithLimit(
            usage.hosted_eval_runs.current,
            usage.hosted_eval_runs.hard_limit ?? usage.monthly_evolution_runs,
            formatInteger
          )}
          color={usage.hosted_eval_runs.status === 'blocked' ? 'error' : usage.hosted_eval_runs.status === 'warning' ? 'primary' : 'success'}
        />
        <SummaryCard
          icon={<Cpu />}
          label="Managed Requests"
          value={formatUsageWithLimit(
            usage.managed_inference_requests.current,
            usage.managed_inference_requests.hard_limit,
            formatInteger
          )}
          color={usage.managed_inference_requests.status === 'blocked' ? 'error' : usage.managed_inference_requests.status === 'warning' ? 'primary' : 'success'}
        />
        <SummaryCard
          icon={<Gauge />}
          label="Managed Tokens"
          value={formatUsageWithLimit(
            usage.managed_inference_tokens.current,
            usage.managed_inference_tokens.hard_limit,
            formatInteger
          )}
          color={usage.managed_inference_tokens.status === 'blocked' ? 'error' : usage.managed_inference_tokens.status === 'warning' ? 'primary' : 'success'}
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

  return (
    <Card variant="default" padding="lg" className={styles.noticeCard}>
      <div className={styles.chartHeader}>
        <h3>Consumed This Period</h3>
      </div>
      <div className={styles.meterList}>
        <ProgressMeter
          label="Hosted storage"
          current={usage.storage_bytes.current}
          total={usage.storage_bytes.hard_limit}
          helper={getCounterHelper(usage.storage_bytes, formatBytes)}
          formatter={formatBytes}
        />
        <ProgressMeter
          label="Hosted evals"
          current={usage.hosted_eval_runs.current}
          total={usage.hosted_eval_runs.hard_limit ?? usage.monthly_evolution_runs}
          helper={getCounterHelper(usage.hosted_eval_runs, formatInteger)}
          formatter={formatInteger}
        />
        <ProgressMeter
          label="Managed inference requests"
          current={usage.managed_inference_requests.current}
          total={usage.managed_inference_requests.hard_limit}
          helper={getCounterHelper(usage.managed_inference_requests, formatInteger)}
          formatter={formatInteger}
        />
        <ProgressMeter
          label="Managed inference tokens"
          current={usage.managed_inference_tokens.current}
          total={usage.managed_inference_tokens.hard_limit}
          helper={getCounterHelper(usage.managed_inference_tokens, formatInteger)}
          formatter={formatInteger}
        />
      </div>
      <div className={styles.planHighlights}>
        <FeatureChip label={`${formatLimit(usage.max_playbooks)} playbooks`} />
        <FeatureChip label={`${formatMoneyLimit(usage.monthly_cost_limit_usd)} managed budget`} />
        <FeatureChip label={`${formatInteger(usage.warning_fields.length)} warnings / ${formatInteger(usage.blocked_fields.length)} blocked`} />
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

  if (usage.blocked_fields.length > 0 || usage.limit_exceeded) {
    return 'error';
  }

  if (
    usage.warning_fields.length > 0 ||
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

  if (usage.blocked_fields.includes('storage_bytes')) {
    return {
      title: 'Hosted storage limit reached',
      description: 'Stored playbook content has reached the workspace limit. Trim old hosted content or upgrade to continue growing usage safely.',
      primaryAction: 'Upgrade Plan',
      primaryHref: '/pricing',
    };
  }

  if (usage.blocked_fields.includes('hosted_eval_runs') || usage.limit_exceeded === 'monthly_evolution_runs') {
    return {
      title: 'Monthly evolution limit reached',
      description: `You have used all ${formatLimit(
        usage.monthly_evolution_runs
      )} included hosted evolutions for this billing period. New hosted evolutions are blocked until the cycle resets or you upgrade.`,
      primaryAction: 'Upgrade Plan',
      primaryHref: '/pricing',
    };
  }

  if (usage.blocked_fields.includes('managed_inference_requests')) {
    return {
      title: 'Managed inference request limit reached',
      description: 'This workspace has exhausted the configured managed inference request quota for the current period.',
      primaryAction: 'Upgrade Plan',
      primaryHref: '/pricing',
    };
  }

  if (usage.blocked_fields.includes('managed_inference_tokens')) {
    return {
      title: 'Managed inference token limit reached',
      description: 'This workspace has exhausted the configured managed inference token quota for the current period.',
      primaryAction: 'Upgrade Plan',
      primaryHref: '/pricing',
    };
  }

  if (usage.warning_fields.includes('storage_bytes')) {
    return {
      title: 'Approaching your hosted storage limit',
      description: `Hosted storage is currently at ${formatUsageWithLimit(
        usage.storage_bytes.current,
        usage.storage_bytes.hard_limit,
        formatBytes
      )}. Upgrade before new hosted content starts getting blocked.`,
      primaryAction: 'Upgrade Before You Hit The Limit',
      primaryHref: '/pricing',
    };
  }

  if (usage.warning_fields.includes('hosted_eval_runs')) {
    return {
      title: 'Approaching your hosted eval limit',
      description: `You have ${formatLimit(
        usage.hosted_eval_runs.remaining_hard
      )} hosted eval run${usage.hosted_eval_runs.remaining_hard === 1 ? '' : 's'} remaining before the hard cap.`,
      primaryAction: 'Upgrade Before You Hit The Limit',
      primaryHref: '/pricing',
    };
  }

  if (
    usage.warning_fields.includes('managed_inference_requests') ||
    usage.warning_fields.includes('managed_inference_tokens')
  ) {
    return {
      title: 'Approaching a managed inference limit',
      description: 'Managed inference usage is above the warning threshold for this workspace. Upgrade now to avoid blocked requests.',
      primaryAction: 'Upgrade Before You Hit The Limit',
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

function formatBytes(value: number) {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let current = Math.max(value, 0);
  let unitIndex = 0;

  while (current >= 1024 && unitIndex < units.length - 1) {
    current /= 1024;
    unitIndex += 1;
  }

  const digits = unitIndex === 0 ? 0 : 1;
  return `${current.toFixed(digits)} ${units[unitIndex]}`;
}

function formatCounterLimit(
  value: number | null,
  formatter: (value: number) => string
) {
  if (value === null) {
    return 'Unlimited';
  }

  return formatter(value);
}

function formatUsageWithLimit(
  current: number,
  limit: number | null,
  formatter: (value: number) => string
) {
  if (limit == null) {
    return formatter(current);
  }

  return `${formatter(current)} / ${formatter(limit)}`;
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

function getCounterHelper(
  counter: WorkspaceEntitlements['usage_limits']['storage_bytes'],
  formatter: (value: number) => string
) {
  if (counter.status === 'blocked') {
    return 'Hard limit reached';
  }

  if (counter.remaining_hard !== null) {
    const remaining = formatter(counter.remaining_hard);
    const softLabel = counter.soft_limit === null ? null : `warning at ${formatter(counter.soft_limit)}`;
    return softLabel ? `${remaining} remaining · ${softLabel}` : `${remaining} remaining`;
  }

  if (counter.soft_limit !== null) {
    return `Warning at ${formatter(counter.soft_limit)}`;
  }

  return 'Unlimited on this plan';
}

function buildUsageAlerts(usage: WorkspaceEntitlements['usage_limits']) {
  const alerts: string[] = [];

  if (usage.blocked_fields.includes('storage_bytes')) {
    alerts.push('Hosted storage is at the hard limit.');
  }
  if (usage.blocked_fields.includes('hosted_eval_runs')) {
    alerts.push('Hosted evals are blocked until the limit resets or the plan changes.');
  }
  if (usage.blocked_fields.includes('managed_inference_requests')) {
    alerts.push('Managed inference requests are blocked for this workspace.');
  }
  if (usage.blocked_fields.includes('managed_inference_tokens')) {
    alerts.push('Managed inference tokens are blocked for this workspace.');
  }
  if (!alerts.length && usage.warning_fields.length > 0) {
    alerts.push('One or more workspace meters are above their warning threshold.');
  }

  return alerts;
}
