import { useQuery } from '@tanstack/react-query';
import { Navigate, useNavigate } from 'react-router-dom';
import { adminApi } from '../../utils/api';
import { useAuth } from '../../contexts/AuthContext';
import { Card } from '../../components/ui/Card';
import {
  Users,
  UserPlus,
  Activity,
  DollarSign,
  AlertCircle,
  Shield,
} from 'lucide-react';
import type { PlatformStats, DailySignup, TopUser, ConversionFunnel } from '../../types';
import styles from './AdminDashboard.module.css';

export function AdminDashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user?.is_admin === true;

  const statsQuery = useQuery<PlatformStats>({
    queryKey: ['admin-stats'],
    queryFn: adminApi.getStats,
    enabled: isAdmin,
  });

  const signupsQuery = useQuery<DailySignup[]>({
    queryKey: ['admin-signups'],
    queryFn: () => adminApi.getSignups(30),
    enabled: isAdmin,
  });

  const funnelQuery = useQuery<ConversionFunnel>({
    queryKey: ['admin-funnel'],
    queryFn: () => adminApi.getFunnel(30),
    enabled: isAdmin,
  });

  const topUsersQuery = useQuery<TopUser[]>({
    queryKey: ['admin-top-users'],
    queryFn: () => adminApi.getTopUsers(10),
    enabled: isAdmin,
  });

  if (!isAdmin) {
    return <Navigate to="/dashboard" replace />;
  }

  const isLoading = (
    statsQuery.isLoading ||
    signupsQuery.isLoading ||
    funnelQuery.isLoading ||
    topUsersQuery.isLoading
  );
  const isError = (
    statsQuery.isError ||
    signupsQuery.isError ||
    funnelQuery.isError ||
    topUsersQuery.isError
  );

  const stats = statsQuery.data;
  const signups = signupsQuery.data;
  const funnel = funnelQuery.data;
  const topUsers = topUsersQuery.data;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <div className={styles.headerTitle}>
          <Shield size={24} />
          <h1>Admin Dashboard</h1>
        </div>
        <p>Platform overview and user activity</p>
      </div>

      {isLoading ? (
        <div className={styles.loading}>
          <div className={styles.spinner} />
          <span>Loading admin data...</span>
        </div>
      ) : isError ? (
        <div className={styles.emptyState}>
          <AlertCircle size={48} />
          <h2>Failed to load admin data</h2>
          <p>Something went wrong. Please try again.</p>
          <button className={styles.retryButton} onClick={() => {
            statsQuery.refetch();
            signupsQuery.refetch();
            funnelQuery.refetch();
            topUsersQuery.refetch();
          }}>
            Retry
          </button>
        </div>
      ) : (
        <>
          {/* Stats Cards */}
          {stats && (
            <div className={styles.statsGrid}>
              <Card variant="default" className={styles.statCard}>
                <div className={`${styles.statIcon} ${styles.primary}`}>
                  <Users size={24} />
                </div>
                <div className={styles.statContent}>
                  <span className={styles.statLabel}>Total Users</span>
                  <span className={styles.statValue}>{stats.total_users}</span>
                </div>
              </Card>
              <Card variant="default" className={styles.statCard}>
                <div className={`${styles.statIcon} ${styles.success}`}>
                  <Activity size={24} />
                </div>
                <div className={styles.statContent}>
                  <span className={styles.statLabel}>Active Today</span>
                  <span className={styles.statValue}>{stats.active_users_today}</span>
                </div>
              </Card>
              <Card variant="default" className={styles.statCard}>
                <div className={`${styles.statIcon} ${styles.info}`}>
                  <UserPlus size={24} />
                </div>
                <div className={styles.statContent}>
                  <span className={styles.statLabel}>Signups This Week</span>
                  <span className={styles.statValue}>{stats.signups_this_week}</span>
                </div>
              </Card>
              <Card variant="default" className={styles.statCard}>
                <div className={`${styles.statIcon} ${styles.warning}`}>
                  <DollarSign size={24} />
                </div>
                <div className={styles.statContent}>
                  <span className={styles.statLabel}>Cost Today</span>
                  <span className={styles.statValue}>${stats.total_cost_today}</span>
                </div>
              </Card>
            </div>
          )}

          {funnel && (
            <Card variant="default" padding="lg" className={styles.funnelCard}>
              <div className={styles.funnelHeader}>
                <h3 className={styles.sectionTitle}>Signup Funnel (Last {funnel.days} Days)</h3>
                <span className={styles.funnelMeta}>
                  Trial start rate: {funnel.conversion_signup_to_trial_started_pct.toFixed(1)}%
                </span>
              </div>
              <div className={styles.funnelRows}>
                <FunnelRow
                  label="Signups"
                  count={funnel.signups}
                  stepRate={null}
                  overallRate={100}
                />
                <FunnelRow
                  label="Trial Checkout Intent"
                  count={funnel.trial_checkout_intent}
                  stepRate={funnel.conversion_signup_to_checkout_intent_pct}
                  overallRate={funnel.conversion_signup_to_checkout_intent_pct}
                />
                <FunnelRow
                  label="Trial Started"
                  count={funnel.trial_started}
                  stepRate={funnel.conversion_checkout_intent_to_trial_started_pct}
                  overallRate={funnel.conversion_signup_to_trial_started_pct}
                />
                <FunnelRow
                  label="First Playbook Created"
                  count={funnel.first_playbook_created}
                  stepRate={funnel.conversion_trial_started_to_first_playbook_pct}
                  overallRate={
                    funnel.signups > 0
                      ? Number(((funnel.first_playbook_created / funnel.signups) * 100).toFixed(2))
                      : 0
                  }
                />
                <FunnelRow
                  label="Paid Active (Non-trial)"
                  count={funnel.paid_active_non_trial}
                  stepRate={funnel.conversion_first_playbook_to_paid_active_non_trial_pct}
                  overallRate={funnel.conversion_signup_to_paid_active_non_trial_pct}
                />
              </div>
            </Card>
          )}

          <div className={styles.contentGrid}>
            {/* Tier Distribution */}
            {stats && (
              <Card variant="default" padding="lg" className={styles.tierCard}>
                <h3 className={styles.sectionTitle}>Subscription Distribution</h3>
                <div className={styles.tierList}>
                  {Object.entries(stats.tier_distribution)
                    .sort(([, a], [, b]) => b - a)
                    .map(([tier, count]) => {
                      const total = Object.values(stats.tier_distribution).reduce((s, v) => s + v, 0);
                      const percent = total > 0 ? (count / total) * 100 : 0;
                      return (
                        <div key={tier} className={styles.tierItem}>
                          <div className={styles.tierLabel}>
                            <span className={styles.tierName}>{tier}</span>
                            <span className={styles.tierCount}>{count}</span>
                          </div>
                          <div className={styles.tierBar}>
                            <div
                              className={styles.tierFill}
                              style={{ width: `${percent}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                </div>
              </Card>
            )}

            {/* Signups Chart */}
            {signups && signups.length > 0 && (
              <Card variant="default" padding="lg" className={styles.signupsCard}>
                <h3 className={styles.sectionTitle}>Daily Signups</h3>
                <div className={styles.signupsChart}>
                  <SignupsChart data={signups} />
                </div>
              </Card>
            )}
          </div>

          {/* Top Users */}
          {topUsers && topUsers.length > 0 && (
            <Card variant="default" padding="lg">
              <div className={styles.topUsersHeader}>
                <h3 className={styles.sectionTitle}>Top Users by Spend</h3>
                <button
                  className={styles.viewAllButton}
                  onClick={() => navigate('/admin/users')}
                >
                  View All Users
                </button>
              </div>
              <div className={styles.tableWrapper}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th>Email</th>
                      <th>Tier</th>
                      <th>Spend (MTD)</th>
                      <th>Limit</th>
                      <th>Usage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {topUsers.map((u) => (
                      <tr
                        key={u.user_id}
                        className={styles.clickableRow}
                        onClick={() => navigate(`/admin/users/${u.user_id}`)}
                      >
                        <td>{u.email}</td>
                        <td>
                          <span className={styles.tierBadge}>
                            {u.subscription_tier || 'free'}
                          </span>
                        </td>
                        <td>${u.total_cost_usd}</td>
                        <td>{u.cost_limit_usd ? `$${u.cost_limit_usd}` : '-'}</td>
                        <td>
                          {u.percent_of_limit != null ? (
                            <span className={u.percent_of_limit > 80 ? styles.usageHigh : ''}>
                              {u.percent_of_limit.toFixed(1)}%
                            </span>
                          ) : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

function FunnelRow({
  label,
  count,
  stepRate,
  overallRate,
}: {
  label: string;
  count: number;
  stepRate: number | null;
  overallRate: number;
}) {
  const safeRate = Number.isFinite(overallRate) ? Math.max(0, Math.min(100, overallRate)) : 0;
  const widthPct = Math.max(safeRate, count > 0 ? 4 : 0);

  return (
    <div className={styles.funnelRow}>
      <div className={styles.funnelRowHeader}>
        <span className={styles.funnelLabel}>{label}</span>
        <span className={styles.funnelCount}>{count}</span>
      </div>
      <div className={styles.funnelBar}>
        <div className={styles.funnelFill} style={{ width: `${widthPct}%` }} />
      </div>
      <div className={styles.funnelRates}>
        <span>{safeRate.toFixed(1)}% of signups</span>
        <span>{stepRate === null ? 'Baseline' : `${stepRate.toFixed(1)}% step conversion`}</span>
      </div>
    </div>
  );
}

function SignupsChart({ data }: { data: DailySignup[] }) {
  const chartData = data.slice(-14);
  if (chartData.length === 0) return null;

  const maxCount = Math.max(...chartData.map((d) => d.count), 1);

  return (
    <div className={styles.barChart}>
      {chartData.map((day, index) => {
        const height = maxCount > 0 ? (day.count / maxCount) * 100 : 0;
        const date = new Date(day.date);
        const label = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

        return (
          <div key={day.date} className={styles.barColumn}>
            <div className={styles.barWrapper}>
              {day.count > 0 ? (
                <div
                  className={styles.bar}
                  style={{
                    height: `${height}%`,
                    animationDelay: `${index * 50}ms`,
                  }}
                  title={`${day.count} signups`}
                />
              ) : (
                <div className={styles.emptyBar} />
              )}
            </div>
            <span className={styles.barLabel}>{label}</span>
            <span className={styles.barValue}>{day.count}</span>
          </div>
        );
      })}
    </div>
  );
}
