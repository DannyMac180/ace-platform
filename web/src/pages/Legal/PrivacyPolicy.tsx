import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import styles from './Legal.module.css';

export function PrivacyPolicy() {
  return (
    <div className={styles.container}>
      <div className={styles.content}>
        <Link to="/login" className={styles.backLink}>
          <ArrowLeft size={16} />
          Back
        </Link>

        <div className={styles.card}>
          <h1>Privacy Policy</h1>
          <p className={styles.effectiveDate}>Effective date: February 6, 2026</p>

          <h2>1. Introduction</h2>
          <p>
            ACE Platform ("we", "us", or "our") is committed to protecting your privacy.
            This Privacy Policy explains how we collect, use, disclose, and safeguard your
            information when you use our Service.
          </p>

          <h2>2. Information We Collect</h2>
          <p>We collect the following types of information:</p>
          <ul>
            <li>
              <strong>Account information:</strong> Email address and password (hashed)
              when you register, or profile data from OAuth providers (Google, GitHub)
              if you choose social sign-in.
            </li>
            <li>
              <strong>Playbook content:</strong> The playbooks, versions, and outcomes
              you create and store within the Service.
            </li>
            <li>
              <strong>Usage data:</strong> API call counts, feature usage, and interaction
              patterns to improve the Service.
            </li>
            <li>
              <strong>Billing information:</strong> Payment details are processed securely
              by Stripe. We do not store your full credit card number.
            </li>
          </ul>

          <h2>3. How We Use Your Information</h2>
          <p>We use your information to:</p>
          <ul>
            <li>Provide, maintain, and improve the Service</li>
            <li>Process your transactions and manage your subscription</li>
            <li>Send you service-related communications (e.g., email verification, password resets)</li>
            <li>Analyze usage patterns to enhance the user experience</li>
            <li>Comply with legal obligations</li>
          </ul>

          <h2>4. Playbook Evolution and AI Processing</h2>
          <p>
            When you use the evolution feature, your playbook content and recorded outcomes
            are processed by AI models to generate improved playbook versions. This
            processing is performed solely to provide the evolution functionality you
            requested. We do not use your playbook content to train AI models.
          </p>

          <h2>5. Data Sharing</h2>
          <p>
            We do not sell your personal information. We may share your information with:
          </p>
          <ul>
            <li>
              <strong>Service providers:</strong> Third-party services that help us
              operate the Service (e.g., Stripe for payments, cloud hosting providers).
            </li>
            <li>
              <strong>Legal requirements:</strong> When required by law, regulation,
              or legal process.
            </li>
          </ul>

          <h2>6. Data Security</h2>
          <p>
            We implement appropriate technical and organizational measures to protect
            your information, including encryption in transit (TLS) and at rest,
            secure password hashing, and access controls. However, no method of
            transmission over the Internet is completely secure.
          </p>

          <h2>7. Data Retention</h2>
          <p>
            We retain your information for as long as your account is active or as
            needed to provide the Service. When you delete your account, we remove
            your personal data within 30 days, except where retention is required
            by law.
          </p>

          <h2>8. Your Rights</h2>
          <p>You have the right to:</p>
          <ul>
            <li>Access and download your data through the Settings page</li>
            <li>Correct inaccurate information in your account</li>
            <li>Delete your account and associated data</li>
            <li>Object to certain processing of your data</li>
          </ul>

          <h2>9. Cookies</h2>
          <p>
            The Service uses essential cookies and local storage for authentication
            and session management. We do not use third-party tracking cookies or
            advertising cookies.
          </p>

          <h2>10. Children's Privacy</h2>
          <p>
            The Service is not intended for users under the age of 16. We do not
            knowingly collect information from children under 16.
          </p>

          <h2>11. Changes to This Policy</h2>
          <p>
            We may update this Privacy Policy from time to time. We will notify you
            of material changes by email or through the Service. The effective date
            at the top of this page indicates when the policy was last revised.
          </p>

          <h2>12. Contact</h2>
          <p>
            If you have questions about this Privacy Policy, please contact us at
            privacy@aceagent.io.
          </p>

          <div className={styles.footer}>
            <Link to="/terms" className={styles.footerLink}>
              Terms of Service
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
