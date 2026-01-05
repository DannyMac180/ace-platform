import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { setTokens } from '../../utils/api';
import { useAuth } from '../../contexts/AuthContext';
import styles from './OAuthCallback.module.css';

export function OAuthCallback() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { refreshUser } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handleCallback = async () => {
      const errorParam = searchParams.get('error');
      if (errorParam) {
        setError(errorParam);
        return;
      }

      const accessToken = searchParams.get('access_token');
      const refreshToken = searchParams.get('refresh_token');

      if (!accessToken || !refreshToken) {
        setError('Invalid OAuth response');
        return;
      }

      // Store tokens
      setTokens({
        access_token: accessToken,
        refresh_token: refreshToken,
        token_type: 'bearer',
      });

      // Refresh user data
      try {
        await refreshUser();
        // Redirect to dashboard
        navigate('/dashboard', { replace: true });
      } catch {
        setError('Failed to load user data');
      }
    };

    handleCallback();
  }, [searchParams, navigate, refreshUser]);

  if (error) {
    return (
      <div className={styles.container}>
        <div className={styles.card}>
          <div className={styles.iconError}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
          </div>
          <h2>Authentication Failed</h2>
          <p className={styles.errorMessage}>{error}</p>
          <button className={styles.button} onClick={() => navigate('/login')}>
            Back to Login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <div className={styles.spinner} />
        <p>Completing authentication...</p>
      </div>
    </div>
  );
}
