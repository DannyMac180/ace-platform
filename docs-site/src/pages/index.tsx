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
            href={`${appUrl}/login`}>
            Get Started
          </Link>
          <Link
            className={clsx('button button--secondary button--lg', styles.heroButton)}
            to="/docs/developer-guides/mcp-integration/overview">
            MCP Integration
          </Link>
        </div>
      </div>
    </header>
  );
}

type FeatureItem = {
  title: string;
  icon: string;
  description: JSX.Element;
};

const FeatureList: FeatureItem[] = [
  {
    title: 'Self-Improving Playbooks',
    icon: '♠',
    description: (
      <>
        Record outcomes after each task, and ACE automatically evolves
        your playbooks based on real-world results. The more you use them,
        the better they get.
      </>
    ),
  },
  {
    title: 'MCP Integration',
    icon: '♥',
    description: (
      <>
        Connect directly to Claude Desktop, Claude Code, or any MCP-compatible
        agent. Access playbooks without writing integration code.
      </>
    ),
  },
  {
    title: 'Version Control Built-In',
    icon: '♦',
    description: (
      <>
        Every change creates a new version. Compare diffs, understand improvements,
        and roll back if needed. Full history at your fingertips.
      </>
    ),
  },
];

function Feature({title, icon, description}: FeatureItem) {
  return (
    <div className={clsx('col col--4', styles.feature)}>
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
          <div className="col col--4">
            <Link to="/docs/getting-started/quick-start" className={styles.linkCard}>
              <h3>Quick Start</h3>
              <p>Get up and running in 5 minutes</p>
            </Link>
          </div>
          <div className="col col--4">
            <Link to="/docs/developer-guides/mcp-integration/claude-code" className={styles.linkCard}>
              <h3>Claude Code Setup</h3>
              <p>Integrate with Claude Code CLI</p>
            </Link>
          </div>
          <div className="col col--4">
            <Link to="/docs/developer-guides/recording-outcomes" className={styles.linkCard}>
              <h3>Recording Outcomes</h3>
              <p>Feed ACE the feedback it needs to evolve</p>
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}

export default function Home(): JSX.Element {
  const {siteConfig} = useDocusaurusContext();
  return (
    <Layout
      title={`${siteConfig.title} Documentation`}
      description="Documentation for ACE - Playbooks as a Service with self-improving AI instructions">
      <HomepageHeader />
      <main>
        <HomepageFeatures />
        <HomepageQuickLinks />
      </main>
    </Layout>
  );
}
