import { useState, useEffect } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { api } from '../../utils/api';
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
  const { user } = useAuth();
  const [linkedAccounts, setLinkedAccounts] = useState<LinkedAccounts | null>(null);
  const [providers, setProviders] = useState<OAuthProviders | null>(null);
  const [loading, setLoading] = useState(true);
  const [unlinking, setUnlinking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

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

  const handleConnect = (provider: 'google' | 'github') => {
    const apiBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    window.location.href = `${apiBaseUrl}/auth/oauth/${provider}/login`;
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

  const showOAuthSection = providers && (providers.google || providers.github);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>Settings</h1>
        <p>Manage your account settings and preferences</p>
      </div>

      {/* Account Section */}
      <section className={styles.section}>
        <h2>Account</h2>
        <div className={styles.card}>
          <div className={styles.field}>
            <label>Email</label>
            <span>{user?.email}</span>
          </div>
          <div className={styles.field}>
            <label>Subscription</label>
            <span className={styles.badge}>{user?.subscription_tier || 'Free'}</span>
          </div>
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
                      >
                        Connect
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
                      >
                        Connect
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
    </div>
  );
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
