import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Navigate, useNavigate } from 'react-router-dom';
import { adminApi } from '../../utils/api';
import { useAuth } from '../../contexts/AuthContext';
import { Card } from '../../components/ui/Card';
import {
  Search,
  ChevronLeft,
  ChevronRight,
  Shield,
  AlertCircle,
  ArrowLeft,
} from 'lucide-react';
import type { AdminUserItem, PaginatedResponse } from '../../types';
import styles from './AdminUsers.module.css';

export function AdminUsers() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isAdmin = user?.is_admin === true;
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [tier, setTier] = useState('');
  const [searchInput, setSearchInput] = useState('');

  const usersQuery = useQuery<PaginatedResponse<AdminUserItem>>({
    queryKey: ['admin-users', page, search, tier],
    queryFn: () => adminApi.getUsers(page, search || undefined, tier || undefined),
    enabled: isAdmin,
  });

  if (!isAdmin) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setSearch(searchInput);
    setPage(1);
  };

  const data = usersQuery.data;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <button className={styles.backButton} onClick={() => navigate('/admin')}>
          <ArrowLeft size={18} />
          Back to Admin
        </button>
        <div className={styles.headerTitle}>
          <Shield size={24} />
          <h1>Users</h1>
        </div>
        <p>{data ? `${data.total} total users` : 'Loading...'}</p>
      </div>

      {/* Filters */}
      <Card variant="default" padding="md" className={styles.filtersCard}>
        <form onSubmit={handleSearch} className={styles.filters}>
          <div className={styles.searchWrapper}>
            <Search size={18} className={styles.searchIcon} />
            <input
              type="text"
              placeholder="Search by email..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className={styles.searchInput}
            />
          </div>
          <select
            value={tier}
            onChange={(e) => { setTier(e.target.value); setPage(1); }}
            className={styles.filterSelect}
          >
            <option value="">All Tiers</option>
            <option value="free">Free</option>
            <option value="starter">Starter</option>
            <option value="pro">Pro</option>
            <option value="ultra">Ultra</option>
            <option value="enterprise">Enterprise</option>
          </select>
          <button type="submit" className={styles.searchButton}>Search</button>
        </form>
      </Card>

      {/* Users Table */}
      {usersQuery.isLoading ? (
        <div className={styles.loading}>
          <div className={styles.spinner} />
          <span>Loading users...</span>
        </div>
      ) : usersQuery.isError ? (
        <div className={styles.emptyState}>
          <AlertCircle size={48} />
          <h2>Failed to load users</h2>
          <button className={styles.retryButton} onClick={() => usersQuery.refetch()}>
            Retry
          </button>
        </div>
      ) : data && data.items.length > 0 ? (
        <>
          <Card variant="default" padding="none">
            <div className={styles.tableWrapper}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Email</th>
                    <th>Status</th>
                    <th>Tier</th>
                    <th>Playbooks</th>
                    <th>Cost (MTD)</th>
                    <th>Joined</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((u) => (
                    <tr
                      key={u.id}
                      className={styles.clickableRow}
                      onClick={() => navigate(`/admin/users/${u.id}`)}
                    >
                      <td>
                        <div className={styles.emailCell}>
                          <span>{u.email}</span>
                          {u.is_admin && <span className={styles.adminBadge}>Admin</span>}
                        </div>
                      </td>
                      <td>
                        <span className={`${styles.statusBadge} ${u.is_active ? styles.active : styles.inactive}`}>
                          {u.is_active ? 'Active' : 'Inactive'}
                        </span>
                      </td>
                      <td>
                        <span className={styles.tierBadge}>
                          {u.subscription_tier || 'free'}
                        </span>
                      </td>
                      <td>{u.playbook_count}</td>
                      <td>${u.total_cost_usd}</td>
                      <td>{new Date(u.created_at).toLocaleDateString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          {/* Pagination */}
          {data.total_pages > 1 && (
            <div className={styles.pagination}>
              <button
                className={styles.pageButton}
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                <ChevronLeft size={18} />
                Previous
              </button>
              <span className={styles.pageInfo}>
                Page {data.page} of {data.total_pages}
              </span>
              <button
                className={styles.pageButton}
                disabled={page >= data.total_pages}
                onClick={() => setPage(page + 1)}
              >
                Next
                <ChevronRight size={18} />
              </button>
            </div>
          )}
        </>
      ) : (
        <div className={styles.emptyState}>
          <h2>No users found</h2>
          <p>Try adjusting your search or filters.</p>
        </div>
      )}
    </div>
  );
}
