import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { AxiosError } from 'axios';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Logo } from '../../components/Logo';
import { authApi } from '../../utils/api';
import styles from './ForgotPassword.module.css';

export function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [isSubmitted, setIsSubmitted] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      await authApi.forgotPassword(email);
      setIsSubmitted(true);
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
      {/* Animated background */}
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

          {isSubmitted ? (
            <div className={styles.successState}>
              <div className={styles.successIcon}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                  <polyline points="22 4 12 14.01 9 11.01" />
                </svg>
              </div>
              <h2>Check your email</h2>
              <p>
                If an account exists for <strong>{email}</strong>, we've sent a password reset link.
              </p>
              <p className={styles.note}>
                The link will expire in 1 hour. Check your spam folder if you don't see it.
              </p>
              <Link to="/login" className={styles.backLink}>
                Back to sign in
              </Link>
            </div>
          ) : (
            <>
              <div className={styles.formHeader}>
                <h2>Forgot password?</h2>
                <p>Enter your email and we'll send you a reset link</p>
              </div>

              <form onSubmit={handleSubmit} className={styles.form}>
                <Input
                  type="email"
                  label="Email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                  autoFocus
                />

                {error && <div className={styles.error}>{error}</div>}

                <Button type="submit" isLoading={isLoading} className={styles.submitButton}>
                  Send reset link
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
