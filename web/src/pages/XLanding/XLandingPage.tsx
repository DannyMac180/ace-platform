import { useEffect } from 'react';
import { Link } from 'react-router-dom';
import { appendAttributionParams } from '../../lib/attribution';
import { trackAcquisitionEvent } from '../../lib/analytics';
import styles from './XLandingPage.module.css';

const STEPS = [
  {
    title: 'Connect your workflow',
    description: 'Plug ACE into your MCP stack in a few minutes.',
  },
  {
    title: 'Run normal tasks',
    description: 'Keep coding and shipping while ACE observes outcomes.',
  },
  {
    title: 'Get better playbooks',
    description: 'ACE evolves your playbooks from what actually worked.',
  },
];

export function XLandingPage() {
  useEffect(() => {
    trackAcquisitionEvent('landing_view', {
      surface: 'spa_x',
      path: '/x',
    });
  }, []);

  const registerHref = appendAttributionParams('/register');
  const loginHref = appendAttributionParams('/login');

  return (
    <div className={styles.page}>
      <div className={styles.background} />
      <header className={styles.nav}>
        <Link to="/" className={styles.brand}>ACE</Link>
        <div className={styles.navActions}>
          <Link to={loginHref} className={styles.navLink}>Sign in</Link>
          <a
            href="https://docs.aceagent.io/docs/getting-started/quick-start/"
            target="_blank"
            rel="noreferrer"
            className={styles.navLink}
          >
            Docs
          </a>
        </div>
      </header>

      <main className={styles.main}>
        <section className={styles.hero}>
          <p className={styles.eyebrow}>From X to first value</p>
          <h1>Your AI workflow should improve after every task.</h1>
          <p>
            ACE turns real outcomes into evolving playbooks so your next run is cleaner,
            faster, and more reliable.
          </p>
        </section>

        <section className={styles.socialProof} aria-label="Social proof">
          <span>Built for Claude Code</span>
          <span>Works with Codex</span>
          <span>MCP-native</span>
        </section>

        <section className={styles.steps}>
          {STEPS.map((step, index) => (
            <article key={step.title} className={styles.stepCard}>
              <p className={styles.stepNumber}>0{index + 1}</p>
              <h2>{step.title}</h2>
              <p>{step.description}</p>
            </article>
          ))}
        </section>
      </main>

      <div className={styles.stickyCta}>
        <Link
          to={registerHref}
          className={styles.primaryCta}
          onClick={() => {
            trackAcquisitionEvent('register_start', {
              source: 'x_landing_sticky_cta',
            });
          }}
        >
          Start free trial
        </Link>
      </div>
    </div>
  );
}
