import { useEffect, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import { api } from '../../utils/api';
import { useAuth } from '../../contexts/AuthContext';
import { Logo } from '../../components/Logo';
import styles from './VerifyEmail.module.css';

type VerificationState = 'loading' | 'success' | 'error';

export function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token');
  const [state, setState] = useState<VerificationState>(token ? 'loading' : 'error');
  const [errorMessage, setErrorMessage] = useState(token ? '' : 'No verification token provided');
  const { refreshUser } = useAuth();

  useEffect(() => {
    if (!token) {
      return;
    }

    const verifyEmail = async () => {
      try {
        await api.post('/auth/verify-email', { token });
        // Refresh user data so verification status is updated globally
        await refreshUser();
        setState('success');
      } catch (err: unknown) {
        setState('error');
        // Extract error message from API response
        if (err && typeof err === 'object' && 'response' in err) {
          const response = (err as { response?: { data?: { detail?: string; error?: { message?: string } } } }).response;
          setErrorMessage(
            response?.data?.error?.message ||
            response?.data?.detail ||
            'Verification failed. The link may have expired.'
          );
        } else {
          setErrorMessage('Verification failed. Please try again.');
        }
      }
    };

    verifyEmail();
  }, [token, refreshUser]);

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <Logo variant="card" size="lg" />

        {state === 'loading' && (
          <>
            <h1>Verifying your email...</h1>
            <p className={styles.subtitle}>Please wait a moment</p>
            <div className={styles.spinner} />
          </>
        )}

        {state === 'success' && (
          <>
            <div className={styles.iconSuccess}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M20 6L9 17l-5-5" />
              </svg>
            </div>
            <h1>Email verified!</h1>
            <p className={styles.subtitle}>
              Your email has been successfully verified. You now have full access to all features.
            </p>
            <Link to="/dashboard" className={styles.button}>
              Go to Dashboard
            </Link>
          </>
        )}

        {state === 'error' && (
          <>
            <div className={styles.iconError}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <line x1="15" y1="9" x2="9" y2="15" />
                <line x1="9" y1="9" x2="15" y2="15" />
              </svg>
            </div>
            <h1>Verification failed</h1>
            <p className={styles.subtitle}>{errorMessage}</p>
            <div className={styles.actions}>
              <Link to="/settings" className={styles.button}>
                Resend verification email
              </Link>
              <Link to="/dashboard" className={styles.buttonSecondary}>
                Go to Dashboard
              </Link>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
