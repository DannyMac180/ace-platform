import { useState, useEffect, type FormEvent, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { accountApi, api, authApi } from '../../utils/api';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import type { AuditLogItem } from '../../types';
import styles from './Settings.module.css';

interface LinkedAccounts {
  google: boolean;
  github: boolean;
  has_password: boolean;
}

interface OAuthProviders {
  google: boolean;
  github: boolean;
}

export function Settings() {
  const { user, refreshUser, logout } = useAuth();
  const navigate = useNavigate();

  // Refresh user data on mount to get latest verification status
  useEffect(() => {
    refreshUser();
  }, [refreshUser]);
  const [linkedAccounts, setLinkedAccounts] = useState<LinkedAccounts | null>(null);
  const [providers, setProviders] = useState<OAuthProviders | null>(null);
  const [loading, setLoading] = useState(true);
  const [unlinking, setUnlinking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [managingSubscription, setManagingSubscription] = useState(false);
  const [sendingVerification, setSendingVerification] = useState(false);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [exportingData, setExportingData] = useState(false);
  const [showSetPasswordModal, setShowSetPasswordModal] = useState(false);
  const [showChangePasswordModal, setShowChangePasswordModal] = useState(false);
  const [showDeleteAccountModal, setShowDeleteAccountModal] = useState(false);
  const [auditLogs, setAuditLogs] = useState<AuditLogItem[]>([]);
  const [auditLogsLoading, setAuditLogsLoading] = useState(false);
  const [auditLogsError, setAuditLogsError] = useState<string | null>(null);
  const [auditLogsPage, setAuditLogsPage] = useState(1);
  const [auditLogsTotalPages, setAuditLogsTotalPages] = useState(1);
  const [showAllAuditLogs, setShowAllAuditLogs] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [accountsRes, providersRes] = await Promise.all([
          api.get<LinkedAccounts>('/auth/oauth/accounts'),
          api.get<OAuthProviders>('/auth/oauth/providers'),
        ]);
        setLinkedAccounts(accountsRes.data);
        setProviders(providersRes.data);
      } catch {
        // OAuth might not be configured
        setLinkedAccounts({ google: false, github: false, has_password: true });
        setProviders({ google: false, github: false });
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, []);

  useEffect(() => {
    const fetchAuditLogs = async () => {
      setAuditLogsLoading(true);
      setAuditLogsError(null);

      try {
        const res = await accountApi.listAuditLogs(1, 20);
        setAuditLogs(res.items);
        setAuditLogsPage(res.page);
        setAuditLogsTotalPages(res.total_pages);
      } catch {
        setAuditLogsError('Failed to load security activity.');
      } finally {
        setAuditLogsLoading(false);
      }
    };

    fetchAuditLogs();
  }, []);

  const loadMoreAuditLogs = async () => {
    if (auditLogsLoading || auditLogsPage >= auditLogsTotalPages) return;

    setAuditLogsLoading(true);
    setAuditLogsError(null);

    try {
      const nextPage = auditLogsPage + 1;
      const res = await accountApi.listAuditLogs(nextPage, 20);
      setAuditLogs((prev) => [...prev, ...res.items]);
      setAuditLogsPage(res.page);
      setAuditLogsTotalPages(res.total_pages);
    } catch {
      setAuditLogsError('Failed to load more activity.');
    } finally {
      setAuditLogsLoading(false);
    }
  };

  const handleSetPassword = async (newPassword: string) => {
    const res = await authApi.setPassword(newPassword);
    setLinkedAccounts((prev) => (prev ? { ...prev, has_password: true } : prev));
    setSuccess(res.message);
    setShowSetPasswordModal(false);
  };

  const handleChangePassword = async (currentPassword: string, newPassword: string) => {
    const res = await authApi.changePassword(currentPassword, newPassword);
    setSuccess(res.message);
    setShowChangePasswordModal(false);
  };

  const handleDownloadData = async () => {
    if (exportingData) return;

    setExportingData(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await accountApi.exportData();
      const blob = response.data as Blob;
      const url = window.URL.createObjectURL(blob);

      const contentDisposition = response.headers?.['content-disposition'] as string | undefined;
      const filename = contentDisposition ? extractFilename(contentDisposition) : null;

      const link = document.createElement('a');
      link.href = url;
      link.download = filename || `ace-export-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);

      setSuccess('Download started.');
    } catch {
      setError('Failed to download your data. Please try again.');
    } finally {
      setExportingData(false);
    }
  };

  const handleConnect = async (provider: 'google' | 'github') => {
    if (connecting) return;

    setConnecting(provider);
    setError(null);

    try {
      // Get CSRF token first
      const csrfToken = await authApi.getOAuthCsrfToken();

      // Redirect with CSRF token
      const apiBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      window.location.href = `${apiBaseUrl}/auth/oauth/${provider}/login?csrf_token=${encodeURIComponent(csrfToken)}`;
    } catch {
      setError('Failed to initiate connection. Please try again.');
      setConnecting(null);
    }
  };

  const handleUnlink = async (provider: 'google' | 'github') => {
    if (!linkedAccounts) return;

    // UX optimization - show error immediately without network round-trip.
    // The backend enforces this rule definitively in oauth_service.py
    const otherProvider = provider === 'google' ? 'github' : 'google';
    if (!linkedAccounts.has_password && !linkedAccounts[otherProvider]) {
      setError('Cannot unlink your only sign-in method. Add a password or connect another account first.');
      return;
    }

    setUnlinking(provider);
    setError(null);
    setSuccess(null);

    try {
      await api.delete(`/auth/oauth/accounts/${provider}`);
      setLinkedAccounts(prev => prev ? { ...prev, [provider]: false } : null);
      setSuccess(`${provider.charAt(0).toUpperCase() + provider.slice(1)} account unlinked`);
    } catch (err) {
      setError('Failed to unlink account. Please try again.');
    } finally {
      setUnlinking(null);
    }
  };

  const handleManageSubscription = async () => {
    setManagingSubscription(true);
    setError(null);

    try {
      const response = await api.post<{ url: string }>('/billing/portal');
      window.location.href = response.data.url;
    } catch {
      setError('Failed to open billing portal. Please try again.');
      setManagingSubscription(false);
    }
  };

  const handleSendVerification = async () => {
    setSendingVerification(true);
    setError(null);
    setSuccess(null);

    try {
      await api.post('/auth/send-verification-email');
      setSuccess('Verification email sent! Please check your inbox.');
    } catch (err: unknown) {
      // Extract error message from API response
      let message = 'Failed to send verification email. Please try again.';
      if (err && typeof err === 'object' && 'response' in err) {
        const response = (err as { response?: { data?: { error?: { message?: string } } } }).response;
        if (response?.data?.error?.message) {
          message = response.data.error.message;
        }
      }
      setError(message);
    } finally {
      setSendingVerification(false);
    }
  };

  const showOAuthSection = providers && (providers.google || providers.github);
  const hasSubscription = user?.subscription_tier && user?.subscription_status === 'active';
  const hasPassword = linkedAccounts?.has_password ?? true;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>Settings</h1>
        <p>Manage your account settings and preferences</p>
      </div>

      {/* Account Section */}
      <section className={styles.section}>
        <h2>Account</h2>
        {error && <div className={styles.error}>{error}</div>}
        {success && <div className={styles.success}>{success}</div>}
        <div className={styles.card}>
          <div className={styles.field}>
            <label>Email</label>
            <span>{user?.email}</span>
          </div>
          <div className={styles.field}>
            <label>Email Status</label>
            <div className={styles.verificationStatus}>
              {user?.email_verified ? (
                <span className={styles.verifiedBadge}>
                  <CheckIcon />
                  Verified
                </span>
              ) : (
                <>
                  <span className={styles.unverifiedBadge}>
                    <WarningIcon />
                    Not verified
                  </span>
                  <button
                    className={styles.resendButton}
                    onClick={handleSendVerification}
                    disabled={sendingVerification}
                  >
                    {sendingVerification ? 'Sending...' : 'Resend'}
                  </button>
                </>
              )}
            </div>
          </div>
          <div className={styles.field}>
            <label>Subscription</label>
            <span className={styles.badge}>{user?.subscription_tier || 'Free'}</span>
          </div>
          {hasSubscription && (
            <div className={styles.field}>
              <label>Billing</label>
              <button
                className={styles.manageButton}
                onClick={handleManageSubscription}
                disabled={managingSubscription}
              >
                {managingSubscription ? 'Opening...' : 'Manage Subscription'}
              </button>
            </div>
          )}
        </div>
      </section>

      {/* Linked Accounts Section */}
      {showOAuthSection && (
        <section className={styles.section}>
          <h2>Linked Accounts</h2>
          <p className={styles.sectionDescription}>
            Connect additional sign-in methods to your account
          </p>

          {error && <div className={styles.error}>{error}</div>}
          {success && <div className={styles.success}>{success}</div>}

          <div className={styles.card}>
            {loading ? (
              <div className={styles.loading}>Loading...</div>
            ) : (
              <div className={styles.providers}>
                {providers?.google && (
                  <div className={styles.provider}>
                    <div className={styles.providerInfo}>
                      <GoogleIcon />
                      <div>
                        <span className={styles.providerName}>Google</span>
                        <span className={styles.providerStatus}>
                          {linkedAccounts?.google ? 'Connected' : 'Not connected'}
                        </span>
                      </div>
                    </div>
                    {linkedAccounts?.google ? (
                      <button
                        className={styles.unlinkButton}
                        onClick={() => handleUnlink('google')}
                        disabled={unlinking === 'google'}
                      >
                        {unlinking === 'google' ? 'Unlinking...' : 'Unlink'}
                      </button>
                    ) : (
                      <button
                        className={styles.connectButton}
                        onClick={() => handleConnect('google')}
                        disabled={connecting === 'google'}
                      >
                        {connecting === 'google' ? 'Connecting...' : 'Connect'}
                      </button>
                    )}
                  </div>
                )}

                {providers?.github && (
                  <div className={styles.provider}>
                    <div className={styles.providerInfo}>
                      <GitHubIcon />
                      <div>
                        <span className={styles.providerName}>GitHub</span>
                        <span className={styles.providerStatus}>
                          {linkedAccounts?.github ? 'Connected' : 'Not connected'}
                        </span>
                      </div>
                    </div>
                    {linkedAccounts?.github ? (
                      <button
                        className={styles.unlinkButton}
                        onClick={() => handleUnlink('github')}
                        disabled={unlinking === 'github'}
                      >
                        {unlinking === 'github' ? 'Unlinking...' : 'Unlink'}
                      </button>
                    ) : (
                      <button
                        className={styles.connectButton}
                        onClick={() => handleConnect('github')}
                        disabled={connecting === 'github'}
                      >
                        {connecting === 'github' ? 'Connecting...' : 'Connect'}
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          {linkedAccounts && !linkedAccounts.has_password && (
            <p className={styles.warning}>
              You don't have a password set. You must keep at least one sign-in method connected.
            </p>
          )}
        </section>
      )}

      {/* Security Section */}
      <section className={styles.section}>
        <h2>Security</h2>
        <p className={styles.sectionDescription}>Manage your password and account security</p>

        <div className={styles.card}>
          <div className={styles.field}>
            <label>Password</label>
            <div className={styles.fieldActions}>
              <span>{hasPassword ? 'Set' : 'Not set'}</span>
              {hasPassword ? (
                <button className={styles.manageButton} onClick={() => setShowChangePasswordModal(true)}>
                  Change
                </button>
              ) : (
                <button className={styles.manageButton} onClick={() => setShowSetPasswordModal(true)}>
                  Set
                </button>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Data & Privacy Section */}
      <section className={styles.section}>
        <h2>Data & Privacy</h2>
        <p className={styles.sectionDescription}>Download your data or delete your account</p>

        <div className={styles.card}>
          <div className={styles.field}>
            <label>Data export</label>
            <button className={styles.manageButton} onClick={handleDownloadData} disabled={exportingData}>
              {exportingData ? 'Preparing…' : 'Download my data'}
            </button>
          </div>
        </div>
      </section>

      {/* Recent Security Activity */}
      <section className={styles.section}>
        <h2>Recent Security Activity</h2>
        <p className={styles.sectionDescription}>Review recent account and security events</p>

        {auditLogsError && <div className={styles.error}>{auditLogsError}</div>}

        <div className={styles.card}>
          {auditLogsLoading && auditLogs.length === 0 ? (
            <div className={styles.loading}>Loading...</div>
          ) : auditLogs.length === 0 ? (
            <div className={styles.loading}>No recent activity.</div>
          ) : (
            <>
              <div className={styles.auditList}>
                {(showAllAuditLogs ? auditLogs : auditLogs.slice(0, 10)).map((log) => (
                  <div key={log.id} className={styles.auditRow}>
                    <div className={styles.auditEvent}>{formatAuditEvent(log.event_type)}</div>
                    <div className={styles.auditMeta}>
                      <span className={styles.auditSeverity}>{log.severity}</span>
                      <span className={styles.auditTime}>
                        {new Date(log.created_at).toLocaleString()}
                      </span>
                    </div>
                  </div>
                ))}
              </div>

              <div className={styles.auditActions}>
                <button
                  className={styles.manageButton}
                  onClick={() => setShowAllAuditLogs((prev) => !prev)}
                >
                  {showAllAuditLogs ? 'Show less' : 'View all'}
                </button>
                {showAllAuditLogs && auditLogsPage < auditLogsTotalPages && (
                  <button
                    className={styles.manageButton}
                    onClick={loadMoreAuditLogs}
                    disabled={auditLogsLoading}
                  >
                    {auditLogsLoading ? 'Loading…' : 'Load more'}
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </section>

      {/* Danger Zone */}
      <section className={styles.section}>
        <h2>Danger Zone</h2>
        <p className={styles.sectionDescription}>Delete your account and all associated data</p>

        <div className={styles.card}>
          <div className={styles.dangerRow}>
            <div>
              <div className={styles.dangerTitle}>Delete account</div>
              <div className={styles.dangerDescription}>
                This permanently deletes your account, playbooks, outcomes, and API keys.
              </div>
            </div>
            <Button variant="danger" onClick={() => setShowDeleteAccountModal(true)}>
              Delete
            </Button>
          </div>
        </div>
      </section>

      {showSetPasswordModal && (
        <SetPasswordModal
          onClose={() => setShowSetPasswordModal(false)}
          onSave={handleSetPassword}
        />
      )}

      {showChangePasswordModal && (
        <ChangePasswordModal
          onClose={() => setShowChangePasswordModal(false)}
          onSave={handleChangePassword}
        />
      )}

      {showDeleteAccountModal && (
        <DeleteAccountModal
          requiresPassword={hasPassword}
          onClose={() => setShowDeleteAccountModal(false)}
          onDelete={async (password) => {
            await accountApi.deleteAccount('DELETE', password);
            logout();
            navigate('/register', { replace: true });
          }}
        />
      )}
    </div>
  );
}

function extractFilename(contentDisposition: string): string | null {
  // Example: attachment; filename="ace-export-2026-02-03.json"
  const match = /filename\*?=(?:UTF-8''|")?([^";]+)"?/i.exec(contentDisposition);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

function formatAuditEvent(eventType: string): string {
  return eventType
    .replace(/_/g, ' ')
    .split(' ')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div className={styles.modalOverlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h2>{title}</h2>
        {children}
      </div>
    </div>
  );
}

function SetPasswordModal({
  onClose,
  onSave,
}: {
  onClose: () => void;
  onSave: (newPassword: string) => Promise<void>;
}) {
  const [newPassword, setNewPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);

    try {
      await onSave(newPassword);
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to set password. Please try again.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="Set password" onClose={onClose}>
      <form onSubmit={handleSubmit} className={styles.modalForm}>
        {error && <div className={styles.modalError}>{error}</div>}
        <Input
          label="New password"
          name="new_password"
          type="password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          required
          minLength={8}
          autoComplete="new-password"
        />
        <div className={styles.modalActions}>
          <Button variant="ghost" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" isLoading={saving} disabled={newPassword.length < 8}>
            Set password
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function ChangePasswordModal({
  onClose,
  onSave,
}: {
  onClose: () => void;
  onSave: (currentPassword: string, newPassword: string) => Promise<void>;
}) {
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSaving(true);

    try {
      await onSave(currentPassword, newPassword);
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to change password. Please try again.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="Change password" onClose={onClose}>
      <form onSubmit={handleSubmit} className={styles.modalForm}>
        {error && <div className={styles.modalError}>{error}</div>}
        <Input
          label="Current password"
          name="current_password"
          type="password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          required
          autoComplete="current-password"
        />
        <Input
          label="New password"
          name="new_password"
          type="password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          required
          minLength={8}
          autoComplete="new-password"
        />
        <div className={styles.modalActions}>
          <Button variant="ghost" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" isLoading={saving} disabled={newPassword.length < 8}>
            Change password
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function DeleteAccountModal({
  requiresPassword,
  onClose,
  onDelete,
}: {
  requiresPassword: boolean;
  onClose: () => void;
  onDelete: (password?: string) => Promise<void>;
}) {
  const [confirmText, setConfirmText] = useState('');
  const [password, setPassword] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canDelete =
    confirmText === 'DELETE' && (!requiresPassword || (requiresPassword && password.length > 0));

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setDeleting(true);

    try {
      await onDelete(requiresPassword ? password : undefined);
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Failed to delete account. Please try again.'));
      setDeleting(false);
    }
  };

  return (
    <Modal title="Delete account" onClose={onClose}>
      <form onSubmit={handleSubmit} className={styles.modalForm}>
        <p className={styles.modalDescription}>
          This is permanent. Type <strong>DELETE</strong> to confirm.
        </p>
        {error && <div className={styles.modalError}>{error}</div>}
        <Input
          label="Confirmation"
          name="confirm"
          value={confirmText}
          onChange={(e) => setConfirmText(e.target.value)}
          placeholder="DELETE"
          required
        />
        {requiresPassword && (
          <Input
            label="Password"
            name="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        )}
        <div className={styles.modalActions}>
          <Button variant="ghost" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" type="submit" isLoading={deleting} disabled={!canDelete}>
            Delete account
          </Button>
        </div>
      </form>
    </Modal>
  );
}

function getErrorMessage(err: unknown, fallback: string): string {
  if (!err || typeof err !== 'object') return fallback;
  if (!('response' in err)) return fallback;

  const response = (err as { response?: { data?: { error?: { message?: string } } } }).response;
  const message = response?.data?.error?.message;
  return message || fallback;
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" width="24" height="24" className={styles.providerIcon}>
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
      />
    </svg>
  );
}

function GitHubIcon() {
  return (
    <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor" className={styles.providerIcon}>
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5">
      <path d="M20 6L9 17l-5-5" />
    </svg>
  );
}

function WarningIcon() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  );
}
