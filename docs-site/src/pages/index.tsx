import React from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import Layout from '@theme/Layout';
import styles from './index.module.css';

function HomepageHeader() {
  const {siteConfig} = useDocusaurusContext();
  const appUrl = siteConfig.customFields?.appUrl as string || 'https://app.aceagent.io';
  return (
    <header className={clsx('hero', styles.heroBanner)}>
      <div className="container">
        <h1 className={styles.heroTitle}>
          {siteConfig.title}
        </h1>
        <p className={styles.heroSubtitle}>{siteConfig.tagline}</p>
        <div className={styles.buttons}>
          <Link
            className={clsx('button button--primary button--lg', styles.heroButton)}
            to="/docs/">
            Choose Your Path
          </Link>
          <Link
            className={clsx('button button--secondary button--lg', styles.heroButton)}
            to="/docs/getting-started/oss-local-start">
            ACE OSS & Local Start
          </Link>
          <Link
            className={clsx('button button--secondary button--lg', styles.heroButton)}
            href={`${appUrl}/login`}>
            ACE Cloud Sign In
          </Link>
        </div>
      </div>
    </header>
  );
}

type FeatureItem = {
  title: string;
  icon: string;
  description: React.ReactNode;
};

const FeatureList: FeatureItem[] = [
  {
    title: 'ACE OSS',
    icon: '♠',
    description: (
      <>
        Run ACE locally or on your own infrastructure with your own model keys,
        storage, and operational control.
      </>
    ),
  },
  {
    title: 'ACE Cloud Personal',
    icon: '♥',
    description: (
      <>
        Get hosted convenience for one user with sync, backups, and managed
        background execution.
      </>
    ),
  },
  {
    title: 'ACE Cloud Team',
    icon: '♦',
    description: (
      <>
        Add shared workspaces, invites, approvals, and team-level visibility
        when multiple people need the same ACE workflow.
      </>
    ),
  },
  {
    title: 'ACE Enterprise',
    icon: '♣',
    description: (
      <>
        Add governance, compliance, and private deployment options for
        organizations with stronger control requirements.
      </>
    ),
  },
];

function Feature({title, icon, description}: FeatureItem) {
  return (
    <div className={clsx('col col--6', styles.feature)}>
      <div className={styles.featureIcon}>{icon}</div>
      <h3 className={styles.featureTitle}>{title}</h3>
      <p className={styles.featureDescription}>{description}</p>
    </div>
  );
}

function HomepageFeatures() {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className="row">
          {FeatureList.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}

function HomepageQuickLinks() {
  return (
    <section className={styles.quickLinks}>
      <div className="container">
        <h2 className={styles.sectionTitle}>Quick Links</h2>
        <div className={clsx('row', styles.linkCards)}>
          <div className="col col--6">
            <Link to="/docs/getting-started/quick-start" className={styles.linkCard}>
              <h3>ACE Cloud Quick Start</h3>
              <p>Hosted onboarding for Personal, Team, and Enterprise paths</p>
            </Link>
          </div>
          <div className="col col--6">
            <Link to="/docs/getting-started/oss-local-start" className={styles.linkCard}>
              <h3>ACE OSS & Local Start</h3>
              <p>Find the local runtime, OSS overview, and self-hosted entry points</p>
            </Link>
          </div>
          <div className="col col--6">
            <Link to="/docs/user-guides/billing-subscriptions" className={styles.linkCard}>
              <h3>ACE Cloud Plans</h3>
              <p>Compare Personal, Team, and Enterprise hosted plans</p>
            </Link>
          </div>
          <div className="col col--6">
            <Link to="/docs/developer-guides/mcp-integration/overview" className={styles.linkCard}>
              <h3>MCP Integration</h3>
              <p>Connect ACE to Claude Desktop, Claude Code, and related clients</p>
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

export default function Home(): React.JSX.Element {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout
      title={`${siteConfig.title} Documentation`}
      description="Documentation for ACE's OSS, hosted personal, team, and enterprise product paths.">
      <HomepageHeader />
      <main>
        <HomepageFeatures />
        <HomepageQuickLinks />
      </main>
    </Layout>
  );
}
