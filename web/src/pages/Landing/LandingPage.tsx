import { Link } from 'react-router-dom';
import { Logo } from '../../components/Logo';
import styles from './LandingPage.module.css';

const TRUST_BADGES = ['Claude Code', 'Codex', 'MCP'];

const PAIN_POINTS = [
  'Great prompts disappear between sessions.',
  'Output quality drifts from task to task.',
  'You spend too much time fixing repeated misses.',
];

const OUTCOMES = [
  'Capture what worked and what failed automatically.',
  'Generate focused evolutions from real execution history.',
  'Get high-signal playbook improvements generated from your real outcomes.',
];

const STEPS = [
  {
    title: 'Connect your workflow',
    description: 'Plug ACE into your MCP-compatible environment in minutes.',
  },
  {
    title: 'Run your normal tasks',
    description: 'Code, research, write, and ship exactly how you already work.',
  },
  {
    title: 'Receive evolved playbooks',
    description: 'ACE creates improved playbook versions as your outcomes accumulate.',
  },
];

const USE_CASES = [
  {
    title: 'Ship cleaner code faster',
    description: 'Reduce repeat bugs by turning review feedback into reusable patterns.',
  },
  {
    title: 'Deliver consistent client work',
    description: 'Keep docs, analysis, and deliverables aligned to your quality bar.',
  },
  {
    title: 'Build your personal AI system',
    description: 'Convert one-off wins into durable playbooks that compound over time.',
  },
];

const METRICS = [
  {
    label: 'Repeat errors',
    value: 'Down',
    description: 'Track recurring misses and shrink them with each evolution run.',
  },
  {
    label: 'Task cycle time',
    value: 'Faster',
    description: 'Measure how quickly you move from prompt to production-ready output.',
  },
  {
    label: 'First-pass quality',
    value: 'Higher',
    description: 'Increase how often outputs are usable without extensive rewrites.',
  },
];

const FAQS = [
  {
    question: 'How long does setup take?',
    answer: 'Most users can connect ACE to an MCP workflow in about 5 minutes.',
  },
  {
    question: 'How are changes applied?',
    answer: 'Evolutions generate new playbook versions automatically, and you can inspect version history in the app.',
  },
  {
    question: 'Will this work with my current AI toolchain?',
    answer: 'ACE is built to layer onto MCP-compatible tools instead of replacing them.',
  },
  {
    question: 'Is this only for coding?',
    answer: 'No. ACE works for coding and broader knowledge workflows like research, writing, and analysis.',
  },
];

export function LandingPage() {
  const currentYear = new Date().getFullYear();

  return (
    <div className={styles.page}>
      <div className={styles.background}>
        <div className={styles.glowTop} />
        <div className={styles.glowBottom} />
        <div className={styles.gridPattern} />
      </div>

      <div className={styles.shell}>
        <header className={styles.nav}>
          <Link to="/" className={styles.brand}>
            <Logo variant="card" size="md" />
            <span className={styles.brandText}>ACE</span>
          </Link>

          <nav className={styles.navLinks} aria-label="Main navigation">
            <a href="#how-it-works">How it works</a>
            <a href="#use-cases">Use cases</a>
            <a href="#pricing">Pricing</a>
            <a href="https://docs.aceagent.io/docs/getting-started/quick-start/" target="_blank" rel="noreferrer">
              Docs
            </a>
            <Link to="/login" className={styles.navGhost}>
              Sign in
            </Link>
            <Link to="/register" className={styles.navCta}>
              Start free
            </Link>
          </nav>
        </header>

        <main>
          <section className={styles.hero}>
            <div className={styles.heroCopy}>
              <p className={styles.eyebrow}>Agentic Context Engineer</p>
              <h1>Your AI workflow gets better after every task.</h1>
              <p className={styles.heroSubhead}>
                ACE captures what worked, what failed, and what to improve so your assistant becomes more reliable with real use.
              </p>

              <div className={styles.heroActions}>
                <Link to="/register" className={styles.primaryAction}>
                  Start free
                </Link>
                <a
                  className={styles.secondaryAction}
                  href="https://docs.aceagent.io/docs/getting-started/quick-start/"
                  target="_blank"
                  rel="noreferrer"
                >
                  See 2-min setup
                </a>
              </div>

              <p className={styles.microCopy}>Works with MCP-enabled workflows.</p>
            </div>

            <div className={styles.heroVisual} aria-hidden="true">
              <video autoPlay loop muted playsInline preload="metadata" className={styles.heroVideo}>
                <source src="/landing-hero-video.mp4" type="video/mp4" />
              </video>
              <div className={styles.metricPanel}>
                <p>Latest improvement</p>
                <strong>Fewer repeat bugs</strong>
                <span>ACE turns recurring issues into rules your agent follows.</span>
              </div>
            </div>
          </section>

          <section className={styles.trustStrip} aria-label="Integrations">
            <span>Built for people shipping real work with AI</span>
            <div className={styles.badges}>
              {TRUST_BADGES.map((badge) => (
                <span key={badge}>{badge}</span>
              ))}
            </div>
          </section>

          <section className={styles.problemOutcome}>
            <div className={styles.panel}>
              <h2>Stop restarting from scratch every session.</h2>
              <ul>
                {PAIN_POINTS.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            </div>

            <div className={styles.panel}>
              <h2>ACE makes improvement a personal system.</h2>
              <ul>
                {OUTCOMES.map((outcome) => (
                  <li key={outcome}>{outcome}</li>
                ))}
              </ul>
            </div>
          </section>

          <section id="how-it-works" className={styles.section}>
            <div className={styles.sectionHeader}>
              <h2>How it works</h2>
              <p>Simple workflow, compounding results.</p>
            </div>
            <div className={styles.stepGrid}>
              {STEPS.map((step, index) => (
                <article key={step.title} className={styles.stepCard}>
                  <span className={styles.stepNumber}>0{index + 1}</span>
                  <h3>{step.title}</h3>
                  <p>{step.description}</p>
                </article>
              ))}
            </div>
          </section>

          <section id="use-cases" className={styles.section}>
            <div className={styles.sectionHeader}>
              <h2>Where individuals see immediate lift</h2>
              <p>From coding tasks to general knowledge work, ACE compounds what you learn.</p>
            </div>
            <div className={styles.useCaseGrid}>
              {USE_CASES.map((useCase) => (
                <article key={useCase.title} className={styles.useCaseCard}>
                  <h3>{useCase.title}</h3>
                  <p>{useCase.description}</p>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <h2>Measure compounding gains</h2>
              <p>Track these signals to verify that ACE is improving your workflow over time.</p>
            </div>
            <div className={styles.metricGrid}>
              {METRICS.map((metric) => (
                <article key={metric.label} className={styles.metricCard}>
                  <p className={styles.metricLabel}>{metric.label}</p>
                  <h3>{metric.value}</h3>
                  <p>{metric.description}</p>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <h2>Built for production-minded individuals</h2>
            </div>
            <div className={styles.controlList}>
              <p>Versioned playbooks let you inspect every evolution run over time.</p>
              <p>Scoped API access with a clear audit trail of evolution activity.</p>
              <p>Works with your existing stack instead of forcing a platform rewrite.</p>
            </div>
          </section>

          <section id="pricing" className={styles.section}>
            <div className={styles.sectionHeader}>
              <h2>Start free, upgrade when you need more power</h2>
            </div>
            <div className={styles.pricingGrid}>
              <article className={styles.priceCard}>
                <h3>Starter</h3>
                <div className={styles.priceBlock}>
                  <p className={styles.price}>$9/mo</p>
                  <p className={styles.yearlyPrice}>
                    $90/yr <span className={styles.yearlyDiscount}>17% off</span>
                  </p>
                </div>
                <p>For individuals building momentum with AI.</p>
                <ul>
                  <li>100 evolution runs / month</li>
                  <li>5 playbooks</li>
                  <li>Premium AI models</li>
                </ul>
              </article>
              <article className={`${styles.priceCard} ${styles.priceCardFeatured}`}>
                <p className={styles.popularTag}>Most popular</p>
                <h3>Pro</h3>
                <div className={styles.priceBlock}>
                  <p className={styles.price}>$29/mo</p>
                  <p className={styles.yearlyPrice}>
                    $290/yr <span className={styles.yearlyDiscount}>17% off</span>
                  </p>
                </div>
                <p>For power users shipping every day.</p>
                <ul>
                  <li>500 evolution runs / month</li>
                  <li>20 playbooks</li>
                  <li>Data export</li>
                </ul>
              </article>
              <article className={styles.priceCard}>
                <h3>Ultra</h3>
                <div className={styles.priceBlock}>
                  <p className={styles.price}>$79/mo</p>
                  <p className={styles.yearlyPrice}>
                    $790/yr <span className={styles.yearlyDiscount}>17% off</span>
                  </p>
                </div>
                <p>For heavy individual workflows.</p>
                <ul>
                  <li>2,000 evolution runs / month</li>
                  <li>100 playbooks</li>
                  <li>Data export</li>
                </ul>
              </article>
            </div>
            <div className={styles.pricingActions}>
              <Link to="/register" className={styles.primaryAction}>
                Start free
              </Link>
              <Link to="/login" className={styles.secondaryAction}>
                Sign in
              </Link>
            </div>
          </section>

          <section className={styles.section}>
            <div className={styles.sectionHeader}>
              <h2>FAQ</h2>
            </div>
            <div className={styles.faqList}>
              {FAQS.map((faq) => (
                <article key={faq.question} className={styles.faqItem}>
                  <h3>{faq.question}</h3>
                  <p>{faq.answer}</p>
                </article>
              ))}
            </div>
          </section>

          <section className={styles.finalCta}>
            <h2>Make your AI improve continuously</h2>
            <p>Turn today&apos;s tasks into tomorrow&apos;s better results.</p>
            <div className={styles.heroActions}>
              <Link to="/register" className={styles.primaryAction}>
                Start free
              </Link>
              <a
                className={styles.secondaryAction}
                href="https://docs.aceagent.io/docs/getting-started/quick-start/"
                target="_blank"
                rel="noreferrer"
              >
                Open quick start
              </a>
            </div>
          </section>
        </main>

        <footer className={styles.footer}>
          <span>&copy; {currentYear} ACE</span>
          <div>
            <Link to="/terms">Terms</Link>
            <Link to="/privacy">Privacy</Link>
            <a href="https://docs.aceagent.io" target="_blank" rel="noreferrer">
              Docs
            </a>
          </div>
        </footer>
      </div>
    </div>
  );
}
