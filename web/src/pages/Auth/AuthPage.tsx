import { useState, type FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { OAuthButtons } from '../../components/OAuthButtons/OAuthButtons';
import styles from './AuthPage.module.css';

type AuthMode = 'login' | 'register';

export function AuthPage() {
  const [mode, setMode] = useState<AuthMode>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { login, register } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');

    if (mode === 'register' && password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }

    setIsLoading(true);
    try {
      if (mode === 'login') {
        await login(email, password);
      } else {
        await register(email, password);
      }
      navigate('/dashboard');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'An error occurred';
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const toggleMode = () => {
    setMode(mode === 'login' ? 'register' : 'login');
    setError('');
  };

  return (
    <div className={styles.container}>
      {/* Animated background */}
      <div className={styles.background}>
        <div className={styles.orb1} />
        <div className={styles.orb2} />
        <div className={styles.orb3} />
        <div className={styles.grid} />
      </div>

      <div className={styles.content}>
        {/* Left side - Branding */}
        <div className={styles.branding}>
          <div className={styles.logoSection}>
            <div className={styles.logo}>
              <svg viewBox="0 0 48 48" fill="none" className={styles.logoIcon}>
                <path
                  d="M24 4L4 14v20l20 10 20-10V14L24 4z"
                  stroke="currentColor"
                  strokeWidth="2"
                  fill="none"
                />
                <path
                  d="M24 24L4 14M24 24l20-10M24 24v20"
                  stroke="currentColor"
                  strokeWidth="2"
                />
                <circle cx="24" cy="24" r="4" fill="currentColor" />
              </svg>
            </div>
            <h1 className={styles.brandName}>ACE</h1>
            <p className={styles.tagline}>Agentic Context Engineer</p>
          </div>

          <div className={styles.features}>
            <div className={styles.feature}>
              <div className={styles.featureIcon}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
                </svg>
              </div>
              <div className={styles.featureText}>
                <h3>Living Playbooks</h3>
                <p>Context that evolves with your real-world outcomes</p>
              </div>
            </div>
            <div className={styles.feature}>
              <div className={styles.featureIcon}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
                </svg>
              </div>
              <div className={styles.featureText}>
                <h3>Continuous Evolution</h3>
                <p>AI-powered refinement based on successes and failures</p>
              </div>
            </div>
            <div className={styles.feature}>
              <div className={styles.featureIcon}>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <path d="M3 9h18M9 21V9" />
                </svg>
              </div>
              <div className={styles.featureText}>
                <h3>MCP Integration</h3>
                <p>Seamlessly connect with Claude and other AI tools</p>
              </div>
            </div>
          </div>
        </div>

        {/* Right side - Auth form */}
        <div className={styles.formSection}>
          <div className={styles.formCard}>
            <div className={styles.formHeader}>
              <h2>{mode === 'login' ? 'Welcome back' : 'Create account'}</h2>
              <p>
                {mode === 'login'
                  ? 'Sign in to continue to your dashboard'
                  : 'Start building evolving playbooks today'}
              </p>
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
              />

              <Input
                type="password"
                label="Password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              />

              {mode === 'register' && (
                <Input
                  type="password"
                  label="Confirm Password"
                  placeholder="••••••••"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  autoComplete="new-password"
                />
              )}

              {error && <div className={styles.error}>{error}</div>}

              <Button type="submit" isLoading={isLoading} className={styles.submitButton}>
                {mode === 'login' ? 'Sign in' : 'Create account'}
              </Button>
            </form>

            <OAuthButtons />

            <div className={styles.formFooter}>
              <span>
                {mode === 'login' ? "Don't have an account?" : 'Already have an account?'}
              </span>
              <button type="button" onClick={toggleMode} className={styles.toggleButton}>
                {mode === 'login' ? 'Create one' : 'Sign in'}
              </button>
            </div>

            {mode === 'login' && (
              <Link to="/forgot-password" className={styles.forgotPassword}>
                Forgot your password?
              </Link>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
