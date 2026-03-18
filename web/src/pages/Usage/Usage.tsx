import { AxiosError } from 'axios';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { usageApi } from '../../utils/api';
import { Card } from '../../components/ui/Card';
import { useAuth } from '../../contexts/AuthContext';
import {
  BarChart3,
  BookOpen,
  Coins,
  CreditCard,
  TrendingUp,
  AlertCircle,
} from 'lucide-react';
import type {
  UsageSummary,
  DailyUsage,
  PlaybookUsage,
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

  const queryErrors = [summaryQuery.error, dailyQuery.error, playbookQuery.error];
  const hasSubscriptionError = queryErrors.some(
    (err) => err instanceof AxiosError && err.response?.status === 402
  );
  const isLoading = isAuthLoading || summaryQuery.isLoading || dailyQuery.isLoading || playbookQuery.isLoading;
  const isError = summaryQuery.isError || dailyQuery.isError || playbookQuery.isError;

  const summary = summaryQuery.data ?? EMPTY_SUMMARY;
  const dailyUsage = dailyQuery.data ?? [];
  const playbookUsage = playbookQuery.data ?? [];
  const totalCost = toNumber(summary.total_cost_usd);

  const handleRetry = () => {
    void summaryQuery.refetch();
    void dailyQuery.refetch();
    void playbookQuery.refetch();
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>Usage</h1>
        <p>Monitor hosted requests, token consumption, and plan readiness</p>
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
          <div className={styles.summaryGrid}>
            <SummaryCard
              icon={<BarChart3 />}
              label="Total Requests"
              value={formatInteger(summary.total_requests)}
              color="primary"
            />
            <SummaryCard
              icon={<Coins />}
              label="Total Tokens"
              value={formatInteger(summary.total_tokens)}
              color="primary"
            />
            <SummaryCard
              icon={<TrendingUp />}
              label="Estimated Spend"
              value={formatCurrency(totalCost)}
              color="success"
            />
            <SummaryCard
              icon={<BookOpen />}
              label="Active Playbooks"
              value={formatInteger(playbookUsage.length)}
              color="primary"
            />
          </div>

          <div className={styles.contentGrid}>
            <Card variant="default" padding="lg" className={styles.chartCard}>
              <div className={styles.chartHeader}>
                <h3>Daily Usage</h3>
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
                <h3>Usage by Playbook</h3>
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
