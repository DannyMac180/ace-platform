import { useQuery } from '@tanstack/react-query';
import { evolutionsApi } from '../../utils/api';
import { Card } from '../../components/ui/Card';
import {
  Activity,
  BookOpen,
  CheckCircle,
  XCircle,
  TrendingUp,
  AlertCircle,
  Clock,
} from 'lucide-react';
import type {
  EvolutionSummary,
  DailyEvolution,
  PlaybookEvolutionStats,
  RecentEvolution,
} from '../../types';
import styles from './Usage.module.css';
import { useNavigate } from 'react-router-dom';

export function Usage() {
  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['evolution-summary'],
    queryFn: evolutionsApi.getSummary,
  });

  const { data: dailyEvolutions, isLoading: dailyLoading } = useQuery({
    queryKey: ['evolution-daily'],
    queryFn: () => evolutionsApi.getDaily(30),
  });

  const { data: playbookStats, isLoading: playbookLoading } = useQuery({
    queryKey: ['evolution-by-playbook'],
    queryFn: () => evolutionsApi.getByPlaybook(5),
  });

  const { data: recentEvolutions, isLoading: recentLoading } = useQuery({
    queryKey: ['evolution-recent'],
    queryFn: () => evolutionsApi.getRecent(10),
  });

  const isLoading = summaryLoading || dailyLoading || playbookLoading || recentLoading;

  const hasAnyData = summary && summary.total_evolutions > 0;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>Usage Activity</h1>
        <p>Track your evolution runs and playbook activity</p>
      </div>

      {isLoading ? (
        <div className={styles.loading}>
          <div className={styles.spinner} />
          <span>Loading activity data...</span>
        </div>
      ) : !hasAnyData ? (
        <EmptyState />
      ) : (
        <>
          {/* Summary Cards */}
          <div className={styles.summaryGrid}>
            <SummaryCard
              icon={<Activity />}
              label="Total Evolutions"
              value={summary.total_evolutions.toString()}
              color="primary"
            />
            <SummaryCard
              icon={<CheckCircle />}
              label="Successful"
              value={summary.completed_evolutions.toString()}
              color="success"
            />
            <SummaryCard
              icon={<XCircle />}
              label="Failed"
              value={summary.failed_evolutions.toString()}
              color="error"
            />
            <SummaryCard
              icon={<TrendingUp />}
              label="Success Rate"
              value={`${Math.round(summary.success_rate * 100)}%`}
              color="success"
            />
          </div>

          {/* Main Content Grid */}
          <div className={styles.contentGrid}>
            {/* Evolution Activity Chart */}
            <Card variant="default" padding="lg" className={styles.chartCard}>
              <div className={styles.chartHeader}>
                <h3>Evolution Activity</h3>
                <span className={styles.chartPeriod}>Last 30 days</span>
              </div>
              <div className={styles.chart}>
                {dailyEvolutions && dailyEvolutions.length > 0 ? (
                  <EvolutionChart data={dailyEvolutions} />
                ) : (
                  <div className={styles.noData}>
                    <AlertCircle size={24} />
                    <span>No evolution data available</span>
                  </div>
                )}
              </div>
              <div className={styles.chartLegend}>
                <span className={styles.legendItem}>
                  <span className={`${styles.legendDot} ${styles.completed}`} />
                  Completed
                </span>
                <span className={styles.legendItem}>
                  <span className={`${styles.legendDot} ${styles.failed}`} />
                  Failed
                </span>
                <span className={styles.legendItem}>
                  <span className={`${styles.legendDot} ${styles.running}`} />
                  Running
                </span>
              </div>
            </Card>

            {/* Playbook Activity */}
            <Card variant="default" padding="lg" className={styles.playbookCard}>
              <div className={styles.chartHeader}>
                <h3>Playbook Activity</h3>
              </div>
              <div className={styles.playbookList}>
                {playbookStats && playbookStats.length > 0 ? (
                  playbookStats.map((stats) => (
                    <PlaybookActivityItem key={stats.playbook_id} stats={stats} />
                  ))
                ) : (
                  <div className={styles.noData}>
                    <BookOpen size={24} />
                    <span>No playbook activity</span>
                  </div>
                )}
              </div>
            </Card>
          </div>

          {/* Recent Activity Timeline */}
          {recentEvolutions && recentEvolutions.length > 0 && (
            <Card variant="default" padding="lg" className={styles.timelineCard}>
              <div className={styles.chartHeader}>
                <h3>Recent Activity</h3>
              </div>
              <div className={styles.timeline}>
                {recentEvolutions.map((evolution) => (
                  <RecentActivityItem key={evolution.id} evolution={evolution} />
                ))}
              </div>
            </Card>
          )}

          {/* Period Info */}
          {summary && (
            <div className={styles.periodInfo}>
              <span>
                Showing data from {new Date(summary.start_date).toLocaleDateString()} to{' '}
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

function EvolutionChart({ data }: { data: DailyEvolution[] }) {
  // Show last 14 days
  const chartData = data.slice(-14);

  if (chartData.length === 0) {
    return null;
  }

  const maxEvolutions = Math.max(...chartData.map((d) => d.total_evolutions), 1);

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

  const handleClick = () => {
    navigate(`/playbooks/${stats.playbook_id}`);
  };

  const timeSince = stats.last_evolution_at
    ? formatTimeAgo(new Date(stats.last_evolution_at))
    : 'Never';

  return (
    <div className={styles.playbookItem} onClick={handleClick}>
      <div className={styles.playbookIcon}>
        <BookOpen size={16} />
      </div>
      <div className={styles.playbookInfo}>
        <span className={styles.playbookName}>{stats.playbook_name}</span>
        <span className={styles.playbookStats}>
          {stats.total_evolutions} evolution{stats.total_evolutions !== 1 ? 's' : ''} ·{' '}
          {Math.round(stats.success_rate * 100)}% success
        </span>
        <span className={styles.playbookLastRun}>Last run: {timeSince}</span>
      </div>
    </div>
  );
}

function RecentActivityItem({ evolution }: { evolution: RecentEvolution }) {
  const navigate = useNavigate();

  const handleClick = () => {
    navigate(`/playbooks/${evolution.playbook_id}`);
  };

  const getStatusIcon = () => {
    switch (evolution.status) {
      case 'completed':
        return <CheckCircle size={20} className={styles.statusIconSuccess} />;
      case 'failed':
        return <XCircle size={20} className={styles.statusIconError} />;
      case 'running':
        return <Clock size={20} className={styles.statusIconRunning} />;
      case 'queued':
        return <Clock size={20} className={styles.statusIconQueued} />;
    }
  };

  const getStatusText = () => {
    switch (evolution.status) {
      case 'completed':
        return 'evolved successfully';
      case 'failed':
        return 'evolution failed';
      case 'running':
        return 'evolution running';
      case 'queued':
        return 'evolution queued';
    }
  };

  const timeSince = evolution.started_at ? formatTimeAgo(new Date(evolution.started_at)) : 'Unknown';

  const versionText =
    evolution.from_version_number && evolution.to_version_number
      ? ` · v${evolution.from_version_number} → v${evolution.to_version_number}`
      : '';

  return (
    <div className={styles.timelineItem} onClick={handleClick}>
      <div className={styles.timelineIcon}>{getStatusIcon()}</div>
      <div className={styles.timelineContent}>
        <div className={styles.timelineHeader}>
          <span className={styles.timelinePlaybook}>{evolution.playbook_name}</span>
          <span className={styles.timelineStatus}>{getStatusText()}</span>
        </div>
        <div className={styles.timelineMeta}>
          {timeSince} · {evolution.outcomes_processed} outcome
          {evolution.outcomes_processed !== 1 ? 's' : ''} processed
          {versionText}
        </div>
        {evolution.error_message && (
          <div className={styles.timelineError}>Error: {evolution.error_message}</div>
        )}
      </div>
    </div>
  );
}

function EmptyState() {
  const navigate = useNavigate();

  return (
    <div className={styles.emptyState}>
      <div className={styles.emptyIcon}>
        <Activity size={48} />
      </div>
      <h2>No Evolution Runs Yet</h2>
      <p>
        Your playbooks haven't been evolved yet. Add outcomes to your playbooks and click "Evolve"
        to see activity here.
      </p>
      <button className={styles.emptyButton} onClick={() => navigate('/dashboard')}>
        Go to Playbooks
      </button>
    </div>
  );
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

  const diffInWeeks = Math.floor(diffInDays / 7);
  if (diffInWeeks < 4) {
    return `${diffInWeeks} week${diffInWeeks !== 1 ? 's' : ''} ago`;
  }

  return date.toLocaleDateString();
}
