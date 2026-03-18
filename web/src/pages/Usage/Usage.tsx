import { AxiosError } from 'axios';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { usageApi, workspacesApi } from '../../utils/api';
import { Card } from '../../components/ui/Card';
import { useAuth } from '../../contexts/AuthContext';
import {
  BookOpen,
  Cpu,
  CreditCard,
  HardDrive,
  TrendingUp,
  AlertCircle,
  FlaskConical,
} from 'lucide-react';
import type {
  UsageSummary,
  DailyUsage,
  PlaybookUsage,
  WorkspaceEntitlements,
} from '../../types';
import styles from './Usage.module.css';

export function Usage() {
  const { user, isLoading: isAuthLoading } = useAuth();
  const hasPaidAccess =
    user?.subscription_status === 'active' &&
    !!user.subscription_tier &&
    user.subscription_tier !== 'free';

  const summaryQuery = useQuery<UsageSummary>({
    queryKey: ['usage-summary'],
    queryFn: usageApi.getSummary,
    enabled: !isAuthLoading && hasPaidAccess,
  });
  const entitlementsQuery = useQuery<WorkspaceEntitlements>({
    queryKey: ['workspace-entitlements', 'me'],
    queryFn: workspacesApi.getPersonalEntitlements,
    enabled: !isAuthLoading && hasPaidAccess,
  });

  const dailyQuery = useQuery<DailyUsage[]>({
    queryKey: ['usage-daily'],
    queryFn: () => usageApi.getDaily(30),
    enabled: !isAuthLoading && hasPaidAccess,
  });

  const playbookQuery = useQuery<PlaybookUsage[]>({
    queryKey: ['usage-by-playbook'],
    queryFn: usageApi.getByPlaybook,
    enabled: !isAuthLoading && hasPaidAccess,
  });

  const queryErrors = [
    entitlementsQuery.error,
    summaryQuery.error,
    dailyQuery.error,
    playbookQuery.error,
  ];
  const hasSubscriptionError = queryErrors.some(
    (err) => err instanceof AxiosError && err.response?.status === 402
  );
  const isLoading =
    isAuthLoading ||
    entitlementsQuery.isLoading ||
    summaryQuery.isLoading ||
    dailyQuery.isLoading ||
    playbookQuery.isLoading;
  const isError =
    entitlementsQuery.isError || summaryQuery.isError || dailyQuery.isError || playbookQuery.isError;

  const entitlements = entitlementsQuery.data ?? EMPTY_ENTITLEMENTS;
  const summary = summaryQuery.data ?? EMPTY_SUMMARY;
  const dailyUsage = dailyQuery.data ?? [];
  const playbookUsage = playbookQuery.data ?? [];
  const totalCost = toNumber(summary.total_cost_usd);
  const usageLimits = entitlements.usage_limits;
  const usageAlerts = buildUsageAlerts(usageLimits);

  const handleRetry = () => {
    void entitlementsQuery.refetch();
    void summaryQuery.refetch();
    void dailyQuery.refetch();
    void playbookQuery.refetch();
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>Usage</h1>
        <p>Monitor hosted storage, eval activity, managed inference, and plan readiness</p>
      </div>

      <div className={styles.accountGrid}>
        <Card variant="default" padding="lg" className={styles.accountCard}>
          <div className={styles.chartHeader}>
            <h3>Current Plan</h3>
          </div>
          <div className={styles.accountList}>
            <AccountMetric label="Tier" value={formatTier(user?.subscription_tier)} />
            <AccountMetric label="Status" value={formatStatus(user?.subscription_status)} />
            <AccountMetric
              label="Trial"
              value={user?.trial_ends_at ? formatTrial(user.trial_ends_at) : 'No active trial'}
            />
          </div>
        </Card>

        <Card variant="default" padding="lg" className={styles.accountCard}>
          <div className={styles.chartHeader}>
            <h3>Account Readiness</h3>
          </div>
          <div className={styles.accountList}>
            <AccountMetric
              label="Payment Method"
              value={user?.has_payment_method ? 'On file' : 'Not on file'}
            />
            <AccountMetric
              label="Email Verification"
              value={user?.email_verified ? 'Verified' : 'Pending verification'}
            />
            <AccountMetric label="Dashboard Access" value={hasPaidAccess ? 'Active' : 'Upgrade required'} />
          </div>
        </Card>
      </div>

      {isLoading ? (
        <div className={styles.loading}>
          <div className={styles.spinner} />
          <span>Loading usage data...</span>
        </div>
      ) : !hasPaidAccess || hasSubscriptionError ? (
        <SubscriptionState />
      ) : isError ? (
        <ErrorState onRetry={handleRetry} />
      ) : (
        <>
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
                usageLimits.storage_bytes.current,
                usageLimits.storage_bytes.hard_limit,
                formatBytes
              )}
              color="primary"
              hint="Live hosted content across playbooks, versions, and outcomes"
            />
            <SummaryCard
              icon={<FlaskConical />}
              label="Hosted Evals"
              value={formatUsageWithLimit(
                usageLimits.hosted_eval_runs.current,
                usageLimits.hosted_eval_runs.hard_limit,
                formatInteger
              )}
              color="primary"
              hint="Runs launched in the current billing period"
            />
            <SummaryCard
              icon={<Cpu />}
              label="Managed Inference"
              value={formatInteger(usageLimits.managed_inference_requests.current)}
              color="success"
              hint={`${formatInteger(usageLimits.managed_inference_tokens.current)} tokens this period`}
            />
            <SummaryCard
              icon={<TrendingUp />}
              label="Inference Spend"
              value={formatUsageWithLimit(
                toNumber(usageLimits.current_cost_usd),
                toNullableNumber(usageLimits.monthly_cost_limit_usd),
                formatCurrency
              )}
              color="primary"
              hint={`${formatCurrency(totalCost)} logged across current usage analytics`}
            />
          </div>

          <div className={styles.contentGrid}>
            <Card variant="default" padding="lg" className={styles.chartCard}>
              <div className={styles.chartHeader}>
                <h3>Daily Managed Inference</h3>
                <span className={styles.chartPeriod}>Last 30 days</span>
              </div>
              <div className={styles.chart}>
                {dailyUsage.length > 0 ? (
                  <UsageChart data={dailyUsage} />
                ) : (
                  <div className={styles.noData}>
                    <AlertCircle size={24} />
                    <span>No usage recorded yet</span>
                  </div>
                )}
              </div>
              <div className={styles.chartLegend}>
                <span className={styles.legendItem}>
                  <span className={`${styles.legendDot} ${styles.usage}`} />
                  Total tokens per day
                </span>
              </div>
            </Card>

            <Card variant="default" padding="lg" className={styles.playbookCard}>
              <div className={styles.chartHeader}>
                <h3>Managed Inference by Playbook</h3>
              </div>
              <div className={styles.playbookList}>
                {playbookUsage.length > 0 ? (
                  playbookUsage.map((entry) => (
                    <UsagePlaybookItem
                      key={entry.playbook_id}
                      entry={entry}
                      totalTokens={summary.total_tokens}
                    />
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

          <div className={styles.periodInfo}>
            <span>
              Showing data from {new Date(summary.start_date).toLocaleDateString()} to{' '}
              {new Date(summary.end_date).toLocaleDateString()}
            </span>
          </div>
        </>
      )}
    </div>
  );
}

interface SummaryCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  color: 'primary' | 'success' | 'error';
  hint?: string;
}

function SummaryCard({ icon, label, value, color, hint }: SummaryCardProps) {
  return (
    <Card variant="default" className={styles.summaryCard}>
      <div className={`${styles.summaryIcon} ${styles[color]}`}>{icon}</div>
      <div className={styles.summaryContent}>
        <span className={styles.summaryLabel}>{label}</span>
        <span className={styles.summaryValue}>{value}</span>
        {hint ? <span className={styles.summaryHint}>{hint}</span> : null}
      </div>
    </Card>
  );
}

function UsageChart({ data }: { data: DailyUsage[] }) {
  const chartData = data.slice(-14);

  if (chartData.length === 0) {
    return null;
  }

  const maxTokens = Math.max(...chartData.map((day) => day.total_tokens), 1);

  return (
    <div className={styles.barChart}>
      {chartData.map((day, index) => {
        const usageHeight = maxTokens > 0 ? (day.total_tokens / maxTokens) * 100 : 0;
        const date = new Date(day.date);
        const dayLabel = date.toLocaleDateString('en-US', { weekday: 'short' });

        return (
          <div key={day.date} className={styles.barColumn}>
            <div className={styles.barWrapper}>
              {day.total_tokens > 0 ? (
                <div
                  className={`${styles.bar} ${styles.usage}`}
                  style={{
                    height: `${usageHeight}%`,
                    animationDelay: `${index * 50}ms`,
                  }}
                  title={`${formatInteger(day.total_tokens)} tokens`}
                />
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

function UsagePlaybookItem({
  entry,
  totalTokens,
}: {
  entry: PlaybookUsage;
  totalTokens: number;
}) {
  const navigate = useNavigate();
  const tokenShare =
    totalTokens > 0 ? `${Math.round((entry.total_tokens / totalTokens) * 100)}% of total tokens` : 'No usage yet';

  return (
    <div className={styles.playbookItem} onClick={() => navigate(`/playbooks/${entry.playbook_id}`)}>
      <div className={styles.playbookIcon}>
        <BookOpen size={16} />
      </div>
      <div className={styles.playbookInfo}>
        <span className={styles.playbookName}>{entry.playbook_name}</span>
        <span className={styles.playbookStats}>
          {formatInteger(entry.request_count)} request{entry.request_count !== 1 ? 's' : ''} ·{' '}
          {formatInteger(entry.total_tokens)} tokens
        </span>
        <span className={styles.playbookLastRun}>
          {tokenShare} · {formatCurrency(toNumber(entry.cost_usd))}
        </span>
      </div>
    </div>
  );
}

function AccountMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.accountMetric}>
      <span className={styles.accountLabel}>{label}</span>
      <span className={styles.accountValue}>{value}</span>
    </div>
  );
}

function SubscriptionState() {
  const navigate = useNavigate();

  return (
    <div className={styles.emptyState}>
      <div className={styles.emptyIcon}>
        <CreditCard size={48} />
      </div>
      <h2>Start Your Free Trial</h2>
      <p>Usage insights unlock after you start a paid plan or trial for your hosted personal account.</p>
      <button className={styles.emptyButton} onClick={() => navigate('/pricing')}>
        Start Free Trial
      </button>
    </div>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  return (
    <div className={styles.emptyState}>
      <div className={styles.emptyIcon}>
        <AlertCircle size={48} />
      </div>
      <h2>Couldn&apos;t Load Usage</h2>
      <p>Something went wrong while loading usage data. Please try again.</p>
      <button className={styles.emptyButton} onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}

const EMPTY_SUMMARY: UsageSummary = {
  start_date: new Date().toISOString(),
  end_date: new Date().toISOString(),
  total_requests: 0,
  total_prompt_tokens: 0,
  total_completion_tokens: 0,
  total_tokens: 0,
  total_cost_usd: 0,
};

const EMPTY_ENTITLEMENTS: WorkspaceEntitlements = {
  workspace_id: 'me',
  plan: 'personal',
  deployment_mode: 'cloud',
  seat_limit: 1,
  enabled_features: [],
  access: {
    subscription_tier: 'free',
    subscription_status: 'none',
    effective_tier: 'free',
    has_feature_access: false,
    is_trialing: false,
  },
  entitlements: {
    cloud_sync: false,
    hosted_backups: false,
    managed_inference: false,
    hosted_evals: false,
    invite_members: false,
    shared_workspace: false,
    approvals: false,
    rbac: false,
    sso: false,
    audit_logs: false,
  },
  usage_limits: {
    monthly_evolution_runs: null,
    current_evolution_runs: 0,
    remaining_evolution_runs: null,
    monthly_cost_limit_usd: null,
    current_cost_usd: 0,
    remaining_cost_usd: null,
    current_total_tokens: 0,
    max_playbooks: null,
    storage_bytes: {
      current: 0,
      soft_limit: null,
      hard_limit: null,
      remaining_soft: null,
      remaining_hard: null,
      status: 'ok',
    },
    hosted_eval_runs: {
      current: 0,
      soft_limit: null,
      hard_limit: null,
      remaining_soft: null,
      remaining_hard: null,
      status: 'ok',
    },
    managed_inference_requests: {
      current: 0,
      soft_limit: null,
      hard_limit: null,
      remaining_soft: null,
      remaining_hard: null,
      status: 'ok',
    },
    managed_inference_tokens: {
      current: 0,
      soft_limit: null,
      hard_limit: null,
      remaining_soft: null,
      remaining_hard: null,
      status: 'ok',
    },
    warning_fields: [],
    blocked_fields: [],
    is_within_limits: true,
    limit_exceeded: null,
  },
};

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

function formatTier(tier: string | null | undefined) {
  if (!tier) {
    return 'Free';
  }

  return tier.charAt(0).toUpperCase() + tier.slice(1);
}

function formatStatus(status: string | undefined) {
  if (!status || status === 'none') {
    return 'Not subscribed';
  }

  return status
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function formatTrial(trialEndsAt: string) {
  const endDate = new Date(trialEndsAt);
  if (Number.isNaN(endDate.getTime())) {
    return 'Unknown';
  }

  const now = new Date();
  if (endDate <= now) {
    return 'Expired';
  }

  const daysRemaining = Math.ceil((endDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  return `${daysRemaining} day${daysRemaining !== 1 ? 's' : ''} remaining`;
}

function toNumber(value: string | number) {
  if (typeof value === 'number') {
    return value;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function toNullableNumber(value: string | number | null) {
  if (value == null) {
    return null;
  }

  return toNumber(value);
}

function buildUsageAlerts(usageLimits: WorkspaceEntitlements['usage_limits']) {
  const alerts: string[] = [];

  if (usageLimits.storage_bytes.status !== 'ok') {
    alerts.push('Hosted storage is at or above the included limit. Trim old content or upgrade.');
  }

  if (usageLimits.hosted_eval_runs.status === 'blocked') {
    alerts.push('Hosted eval quota is exhausted for this billing period.');
  }

  const managedInferenceLimit = toNullableNumber(usageLimits.monthly_cost_limit_usd);
  if (
    managedInferenceLimit != null &&
    toNumber(usageLimits.current_cost_usd) >= managedInferenceLimit
  ) {
    alerts.push('Managed inference spend has reached the current billing-period limit.');
  }

  return alerts;
}
