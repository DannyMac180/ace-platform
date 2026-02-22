import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useNavigate, Link, useLocation } from 'react-router-dom';
import { AxiosError } from 'axios';
import { useAuth } from '../../contexts/AuthContext';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Logo } from '../../components/Logo';
import { OAuthButtons } from '../../components/OAuthButtons/OAuthButtons';
import { getAnonymousId } from '../../lib/anonymousId';
import { appendAttributionParams, getAttributionSnapshot } from '../../lib/attribution';
import { trackAcquisitionEvent } from '../../lib/analytics';
import { getTrialDisclosureVariant } from '../../lib/experiments';
import styles from './AuthPage.module.css';

type AuthMode = 'login' | 'register';

function getIsMobileLayout(): boolean {
  return typeof window !== 'undefined' && window.matchMedia('(max-width: 900px)').matches;
}

export function AuthPage() {
  const location = useLocation();
  const isRegisterPath = location.pathname === '/register';
  const [mode, setMode] = useState<AuthMode>(isRegisterPath ? 'register' : 'login');
  const [registerStep, setRegisterStep] = useState<1 | 2>(1);
  const [isMobileLayout, setIsMobileLayout] = useState(getIsMobileLayout);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const { login, register } = useAuth();
  const navigate = useNavigate();
  const trialDisclosureVariant = getTrialDisclosureVariant();
  const registerStartTrackedRef = useRef(false);

  const showEarlyTrialDisclosure = trialDisclosureVariant === 'control';
  const isMobileRegisterFlow = isMobileLayout && mode === 'register';

  useEffect(() => {
    const mql = window.matchMedia('(max-width: 900px)');
    const onChange = () => setIsMobileLayout(mql.matches);
    onChange();
    mql.addEventListener('change', onChange);
    return () => mql.removeEventListener('change', onChange);
  }, []);

  useEffect(() => {
    setMode(isRegisterPath ? 'register' : 'login');
    setError('');

    if (!isRegisterPath) {
      setRegisterStep(1);
      registerStartTrackedRef.current = false;
    }
  }, [isRegisterPath]);

  useEffect(() => {
    if (mode === 'register' && !registerStartTrackedRef.current) {
      trackAcquisitionEvent(
        'register_start',
        {
          source: 'auth_page',
          path: location.pathname,
        },
        {
          experiment_variant: trialDisclosureVariant,
        },
      );
      registerStartTrackedRef.current = true;
    }
  }, [location.pathname, mode, trialDisclosureVariant]);

  const handleContinueToStepTwo = () => {
    if (!email.includes('@')) {
      setError('Enter a valid email address');
      return;
    }

    setError('');
    setRegisterStep(2);
    trackAcquisitionEvent(
      'register_step_transition',
      {
        from_step: 'email',
        to_step: 'password',
        surface: 'auth_mobile',
      },
      {
        experiment_variant: trialDisclosureVariant,
      },
    );
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');

    if (isMobileRegisterFlow && registerStep === 1) {
      handleContinueToStepTwo();
      return;
    }

    if (mode === 'register') {
      if (password !== confirmPassword) {
        setError('Passwords do not match');
        return;
      }

      trackAcquisitionEvent(
        'register_submit',
        {
          source: 'auth_page',
          path: location.pathname,
          device: isMobileLayout ? 'mobile' : 'desktop',
        },
        {
          experiment_variant: trialDisclosureVariant,
        },
      );
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
        await register(email, password, {
          anonymous_id: getAnonymousId(),
          attribution: getAttributionSnapshot(),
          experiment_variant: trialDisclosureVariant,
        });

        trackAcquisitionEvent(
          'register_success',
          {
            source: 'auth_page',
            method: 'email',
          },
          {
            experiment_variant: trialDisclosureVariant,
          },
        );
      }
      navigate('/dashboard');
    } catch (err: unknown) {
      let message = 'An error occurred';
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

  const toggleMode = () => {
    const nextMode: AuthMode = mode === 'login' ? 'register' : 'login';
    setMode(nextMode);
    setError('');
    setRegisterStep(1);
    registerStartTrackedRef.current = false;
    navigate(appendAttributionParams(nextMode === 'register' ? '/register' : '/login'));
  };

  const stickySwitchHref = appendAttributionParams(mode === 'login' ? '/register' : '/login');

  return (
    <div className={styles.container}>
      <div className={styles.mobileTopBar}>
        <Link to={stickySwitchHref} className={styles.mobileTopLink}>
          {mode === 'login' ? 'New here? Start free' : 'Already have an account? Sign in'}
        </Link>
      </div>

      <div className={styles.background}>
        <div className={styles.orb1} />
        <div className={styles.orb2} />
        <div className={styles.orb3} />
        <div className={styles.grid} />
      </div>

      <div className={styles.content}>
        <div className={styles.branding}>
          <div className={styles.logoSection}>
            <Logo variant="card" size="xl" />
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

        <div className={styles.formSection}>
          <div className={styles.formCard}>
            <div className={styles.formHeader}>
              <h2>{mode === 'login' ? 'Welcome back' : 'Create account'}</h2>
              <p>
                {mode === 'login'
                  ? 'Sign in to continue to your dashboard'
                  : 'Start building evolving playbooks today'}
              </p>
              {mode === 'register' && isMobileRegisterFlow && (
                <p className={styles.stepLabel}>Step {registerStep} of 2</p>
              )}
              {mode === 'register' && showEarlyTrialDisclosure && (
                <p className={styles.trialDisclosure}>7-day trial is card-required, no charge today.</p>
              )}
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

              {(mode === 'login' || !isMobileRegisterFlow || registerStep === 2) && (
                <>
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
                </>
              )}

              {error && (
                <div className={styles.error}>
                  {error}
                  {mode === 'login' && error.toLowerCase().includes('invalid') && (
                    <div className={styles.errorHelp}>
                      New here?{' '}
                      <button type="button" onClick={toggleMode} className={styles.errorLink}>
                        Create an account
                      </button>
                      {' · '}
                      <Link to="/forgot-password" className={styles.errorLink}>
                        Reset password
                      </Link>
                    </div>
                  )}
                </div>
              )}

              <div className={styles.stickySubmitArea}>
                {isMobileRegisterFlow && registerStep === 2 && (
                  <button
                    type="button"
                    className={styles.backButton}
                    onClick={() => setRegisterStep(1)}
                  >
                    Back
                  </button>
                )}

                <Button type="submit" isLoading={isLoading} className={styles.submitButton}>
                  {mode === 'login'
                    ? 'Sign in'
                    : isMobileRegisterFlow && registerStep === 1
                      ? 'Continue'
                      : 'Create account'}
                </Button>
              </div>
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

            <div className={styles.legalLinks}>
              <Link to="/terms">Terms of Service</Link>
              <span className={styles.legalSeparator}>|</span>
              <Link to="/privacy">Privacy Policy</Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
