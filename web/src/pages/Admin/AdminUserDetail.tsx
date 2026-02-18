import { useQuery } from '@tanstack/react-query';
import { Navigate, useParams, useNavigate } from 'react-router-dom';
import { adminApi } from '../../utils/api';
import { useAuth } from '../../contexts/AuthContext';
import { Card } from '../../components/ui/Card';
import {
  ArrowLeft,
  Shield,
  Mail,
  Calendar,
  CreditCard,
  Activity,
  Hash,
  DollarSign,
  AlertCircle,
  CheckCircle,
  XCircle,
} from 'lucide-react';
import type { AdminUserDetail as AdminUserDetailType } from '../../types';
import styles from './AdminUserDetail.module.css';

export function AdminUserDetail() {
  const { user: currentUser } = useAuth();
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const isAdmin = currentUser?.is_admin === true;

  const userQuery = useQuery<AdminUserDetailType>({
    queryKey: ['admin-user', userId],
    queryFn: () => adminApi.getUser(userId!),
    enabled: !!userId && isAdmin,
  });

  if (!isAdmin) {
    return <Navigate to="/dashboard" replace />;
  }

  const detail = userQuery.data;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <button className={styles.backButton} onClick={() => navigate('/admin/users')}>
          <ArrowLeft size={18} />
          Back to Users
        </button>
        {detail && (
          <>
            <div className={styles.headerTitle}>
              <h1>{detail.email}</h1>
              {detail.is_admin && <span className={styles.adminBadge}>Admin</span>}
            </div>
            <p>User detail view</p>
          </>
        )}
      </div>

      {userQuery.isLoading ? (
        <div className={styles.loading}>
          <div className={styles.spinner} />
          <span>Loading user details...</span>
        </div>
      ) : userQuery.isError ? (
        <div className={styles.emptyState}>
          <AlertCircle size={48} />
          <h2>Failed to load user</h2>
          <button className={styles.retryButton} onClick={() => userQuery.refetch()}>
            Retry
          </button>
        </div>
      ) : detail ? (
        <>
          {/* User Info Cards */}
          <div className={styles.infoGrid}>
            <Card variant="default" padding="lg">
              <h3 className={styles.sectionTitle}>Account</h3>
              <div className={styles.fieldList}>
                <InfoField icon={<Mail size={16} />} label="Email" value={detail.email} />
                <InfoField
                  icon={<Shield size={16} />}
                  label="Status"
                  value={
                    <span className={`${styles.statusBadge} ${detail.is_active ? styles.active : styles.inactive}`}>
                      {detail.is_active ? 'Active' : 'Inactive'}
                    </span>
                  }
                />
                <InfoField
                  icon={detail.email_verified ? <CheckCircle size={16} /> : <XCircle size={16} />}
                  label="Email Verified"
                  value={detail.email_verified ? 'Yes' : 'No'}
                />
                <InfoField
                  icon={<Calendar size={16} />}
                  label="Joined"
                  value={new Date(detail.created_at).toLocaleDateString('en-US', {
                    year: 'numeric', month: 'long', day: 'numeric',
                  })}
                />
                <InfoField
                  icon={<Calendar size={16} />}
                  label="Last Updated"
                  value={new Date(detail.updated_at).toLocaleDateString('en-US', {
                    year: 'numeric', month: 'long', day: 'numeric',
                  })}
                />
              </div>
            </Card>

            <Card variant="default" padding="lg">
              <h3 className={styles.sectionTitle}>Subscription</h3>
              <div className={styles.fieldList}>
                <InfoField
                  icon={<CreditCard size={16} />}
                  label="Tier"
                  value={
                    <span className={styles.tierBadge}>
                      {detail.subscription_tier || 'free'}
                    </span>
                  }
                />
                <InfoField
                  icon={<Activity size={16} />}
                  label="Status"
                  value={detail.subscription_status}
                />
                <InfoField
                  icon={<CreditCard size={16} />}
                  label="Payment Method"
                  value={detail.has_payment_method ? 'On file' : 'None'}
                />
                <InfoField
                  icon={<Activity size={16} />}
                  label="Used Trial"
                  value={detail.has_used_trial ? 'Yes' : 'No'}
                />
              </div>
            </Card>
          </div>

          {/* Usage Summary */}
          <Card variant="default" padding="lg" className={styles.usageCard}>
            <h3 className={styles.sectionTitle}>Usage Summary (Last 30 Days)</h3>
            <div className={styles.usageGrid}>
              <div className={styles.usageStat}>
                <Hash size={20} className={styles.usageIcon} />
                <div>
                  <span className={styles.usageLabel}>Total Requests</span>
                  <span className={styles.usageValue}>
                    {detail.usage_summary.total_requests.toLocaleString()}
                  </span>
                </div>
              </div>
              <div className={styles.usageStat}>
                <Activity size={20} className={styles.usageIcon} />
                <div>
                  <span className={styles.usageLabel}>Total Tokens</span>
                  <span className={styles.usageValue}>
                    {detail.usage_summary.total_tokens.toLocaleString()}
                  </span>
                </div>
              </div>
              <div className={styles.usageStat}>
                <DollarSign size={20} className={styles.usageIcon} />
                <div>
                  <span className={styles.usageLabel}>Total Cost</span>
                  <span className={styles.usageValue}>
                    ${detail.usage_summary.total_cost_usd}
                  </span>
                </div>
              </div>
            </div>
            <div className={styles.usagePeriod}>
              {new Date(detail.usage_summary.start_date).toLocaleDateString()} -{' '}
              {new Date(detail.usage_summary.end_date).toLocaleDateString()}
            </div>
          </Card>
        </>
      ) : null}
    </div>
  );
}

function InfoField({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className={styles.field}>
      <div className={styles.fieldIcon}>{icon}</div>
      <span className={styles.fieldLabel}>{label}</span>
      <span className={styles.fieldValue}>{value}</span>
    </div>
  );
}
