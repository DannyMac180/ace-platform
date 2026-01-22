import { useQuery } from '@tanstack/react-query';
import { usageApi } from '../../utils/api';
import { Card } from '../../components/ui/Card';
import {
  Zap,
  DollarSign,
  Activity,
  TrendingUp,
  AlertCircle,
  BookOpen,
} from 'lucide-react';
import type { DailyUsage, PlaybookUsage } from '../../types';
import styles from './Usage.module.css';

export function Usage() {
  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['usage-summary'],
    queryFn: usageApi.getSummary,
  });

  const { data: dailyUsage, isLoading: dailyLoading } = useQuery({
    queryKey: ['usage-daily'],
    queryFn: () => usageApi.getDaily(30),
  });

  const { data: playbookUsage, isLoading: playbookLoading } = useQuery({
    queryKey: ['usage-by-playbook'],
    queryFn: usageApi.getByPlaybook,
  });

  const isLoading = summaryLoading || dailyLoading || playbookLoading;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>Usage Statistics</h1>
        <p>Monitor your platform usage and costs</p>
      </div>

      {isLoading ? (
        <div className={styles.loading}>
          <div className={styles.spinner} />
          <span>Loading usage data...</span>
        </div>
      ) : (
        <>
          {/* Summary Cards */}
          <div className={styles.summaryGrid}>
            <SummaryCard
              icon={<Zap />}
              label="Total Tokens"
              value={formatNumber(summary?.total_tokens || 0)}
              trend="+12%"
              trendUp
            />
            <SummaryCard
              icon={<DollarSign />}
              label="Total Cost"
              value={`$${(summary?.total_cost_usd || 0).toFixed(2)}`}
              trend="+8%"
              trendUp={false}
            />
            <SummaryCard
              icon={<Activity />}
              label="Operations"
              value={formatNumber(summary?.total_requests || 0)}
              trend="+15%"
              trendUp
            />
          </div>

          {/* Charts Section */}
          <div className={styles.chartsGrid}>
            {/* Daily Usage Chart */}
            <Card variant="default" padding="lg" className={styles.chartCard}>
              <div className={styles.chartHeader}>
                <h3>Daily Usage</h3>
                <span className={styles.chartPeriod}>Last 30 days</span>
              </div>
              <div className={styles.chart}>
                {dailyUsage && dailyUsage.length > 0 ? (
                  <UsageChart data={dailyUsage} />
                ) : (
                  <div className={styles.noData}>
                    <AlertCircle size={24} />
                    <span>No usage data available</span>
                  </div>
                )}
              </div>
            </Card>

            {/* Playbook Usage */}
            <Card variant="default" padding="lg" className={styles.chartCard}>
              <div className={styles.chartHeader}>
                <h3>Usage by Playbook</h3>
              </div>
              <div className={styles.playbookList}>
                {playbookUsage && playbookUsage.length > 0 ? (
                  playbookUsage.map((pb) => (
                    <PlaybookUsageItem key={pb.playbook_id} usage={pb} />
                  ))
                ) : (
                  <div className={styles.noData}>
                    <BookOpen size={24} />
                    <span>No playbook usage data</span>
                  </div>
                )}
              </div>
            </Card>
          </div>

          {/* Period Info */}
          {summary && (
            <div className={styles.periodInfo}>
              <span>
                Billing period: {new Date(summary.start_date).toLocaleDateString()} -{' '}
                {new Date(summary.end_date).toLocaleDateString()}
              </span>
            </div>
          )}
        </>
      )}
    </div>
  );
}

interface SummaryCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  trend: string;
  trendUp: boolean;
}

function SummaryCard({ icon, label, value, trend, trendUp }: SummaryCardProps) {
  return (
    <Card variant="default" className={styles.summaryCard}>
      <div className={styles.summaryIcon}>{icon}</div>
      <div className={styles.summaryContent}>
        <span className={styles.summaryLabel}>{label}</span>
        <span className={styles.summaryValue}>{value}</span>
      </div>
      <div className={`${styles.summaryTrend} ${trendUp ? styles.trendUp : styles.trendDown}`}>
        <TrendingUp size={14} style={{ transform: trendUp ? 'none' : 'rotate(180deg)' }} />
        <span>{trend}</span>
      </div>
    </Card>
  );
}

function UsageChart({ data }: { data: DailyUsage[] }) {
  const maxTokens = Math.max(...data.map((d) => d.total_tokens));

  return (
    <div className={styles.barChart}>
      {data.slice(-14).map((day, index) => {
        const height = maxTokens > 0 ? (day.total_tokens / maxTokens) * 100 : 0;
        const date = new Date(day.date);
        const dayLabel = date.toLocaleDateString('en-US', { weekday: 'short' });

        return (
          <div key={day.date} className={styles.barColumn}>
            <div className={styles.barWrapper}>
              <div
                className={styles.bar}
                style={{
                  height: `${height}%`,
                  animationDelay: `${index * 50}ms`,
                }}
              />
            </div>
            <span className={styles.barLabel}>{dayLabel}</span>
          </div>
        );
      })}
    </div>
  );
}

function PlaybookUsageItem({ usage }: { usage: PlaybookUsage }) {
  return (
    <div className={styles.playbookItem}>
      <div className={styles.playbookIcon}>
        <BookOpen size={16} />
      </div>
      <div className={styles.playbookInfo}>
        <span className={styles.playbookName}>{usage.playbook_name}</span>
        <span className={styles.playbookStats}>
          {formatNumber(usage.total_tokens)} tokens · ${usage.cost_usd.toFixed(2)}
        </span>
      </div>
      <div className={styles.playbookOps}>
        <Activity size={14} />
        <span>{usage.request_count}</span>
      </div>
    </div>
  );
}

function formatNumber(num: number): string {
  if (num >= 1000000) {
    return (num / 1000000).toFixed(1) + 'M';
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'K';
  }
  return num.toString();
}
