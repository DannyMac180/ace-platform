import { useState, type FormEvent } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import { AxiosError } from 'axios';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Logo } from '../../components/Logo';
import { authApi } from '../../utils/api';
import styles from './ResetPassword.module.css';

export function ResetPassword() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token');

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [isSuccess, setIsSuccess] = useState(false);

  // No token provided
  if (!token) {
    return (
      <div className={styles.container}>
        <div className={styles.background}>
          <div className={styles.orb1} />
          <div className={styles.orb2} />
          <div className={styles.grid} />
        </div>

        <div className={styles.content}>
          <div className={styles.formCard}>
            <div className={styles.logoSection}>
              <Logo variant="card" size="lg" />
            </div>
            <div className={styles.errorState}>
              <div className={styles.errorIcon}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
              </div>
              <h2>Invalid reset link</h2>
              <p>This password reset link is invalid or missing the required token.</p>
              <Link to="/forgot-password" className={styles.actionLink}>
                Request a new reset link
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }

    setIsLoading(true);

    try {
      await authApi.resetPassword(token, password);
      setIsSuccess(true);
      // Redirect to login after 3 seconds
      setTimeout(() => navigate('/login'), 3000);
    } catch (err: unknown) {
      let message = 'An error occurred. Please try again.';
      if (err instanceof AxiosError && err.response?.data) {
        const data = err.response.data;
        message = data.error?.message || data.detail || message;
      } else if (err instanceof Error) {
        message = err.message;
      }
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.background}>
        <div className={styles.orb1} />
        <div className={styles.orb2} />
        <div className={styles.grid} />
      </div>

      <div className={styles.content}>
        <div className={styles.formCard}>
          <div className={styles.logoSection}>
            <Logo variant="card" size="lg" />
          </div>

          {isSuccess ? (
            <div className={styles.successState}>
              <div className={styles.successIcon}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
              </div>
              <h2>Password reset successful</h2>
              <p>Your password has been updated. Redirecting to sign in...</p>
              <Link to="/login" className={styles.actionLink}>
                Sign in now
              </Link>
            </div>
          ) : (
            <>
              <div className={styles.formHeader}>
                <h2>Reset your password</h2>
                <p>Enter your new password below</p>
              </div>

              <form onSubmit={handleSubmit} className={styles.form}>
                <Input
                  type="password"
                  label="New Password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  autoComplete="new-password"
                  autoFocus
                />

                <Input
                  type="password"
                  label="Confirm Password"
                  placeholder="••••••••"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  autoComplete="new-password"
                />

                {error && <div className={styles.error}>{error}</div>}

                <Button type="submit" isLoading={isLoading} className={styles.submitButton}>
                  Reset password
                </Button>
              </form>

              <div className={styles.formFooter}>
                <Link to="/login" className={styles.backLink}>
                  Back to sign in
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
