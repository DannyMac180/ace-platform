import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import styles from './Legal.module.css';

export function TermsOfService() {
  return (
    <div className={styles.container}>
      <div className={styles.content}>
        <Link to="/login" className={styles.backLink}>
          <ArrowLeft size={16} />
          Back
        </Link>

        <div className={styles.card}>
          <h1>Terms of Service</h1>
          <p className={styles.effectiveDate}>Effective date: February 6, 2026</p>

          <h2>1. Acceptance of Terms</h2>
          <p>
            By accessing or using the ACE Platform ("Service") operated by ACE Platform
            ("we", "us", or "our"), you agree to be bound by these Terms of Service.
            If you do not agree to these terms, do not use the Service.
          </p>

          <h2>2. Description of Service</h2>
          <p>
            ACE Platform provides a hosted playbook management service that enables
            users to create, manage, and evolve AI-assisted playbooks through an API
            and web dashboard. The Service includes playbook creation, version management,
            outcome recording, and automated evolution capabilities.
          </p>

          <h2>3. Account Registration</h2>
          <p>
            To use the Service, you must create an account and provide accurate, complete
            information. You are responsible for maintaining the confidentiality of your
            account credentials and for all activity that occurs under your account.
          </p>

          <h2>4. Acceptable Use</h2>
          <p>You agree not to:</p>
          <ul>
            <li>Use the Service for any unlawful purpose or in violation of any applicable laws</li>
            <li>Attempt to gain unauthorized access to the Service or its related systems</li>
            <li>Interfere with or disrupt the integrity or performance of the Service</li>
            <li>Use the Service to transmit harmful, offensive, or infringing content</li>
            <li>Reverse engineer, decompile, or disassemble any aspect of the Service</li>
          </ul>

          <h2>5. Subscription and Billing</h2>
          <p>
            Certain features of the Service require a paid subscription. By subscribing,
            you agree to pay the applicable fees. Subscriptions renew automatically unless
            canceled before the renewal date. Refunds are handled in accordance with our
            refund policy.
          </p>

          <h2>6. API Keys and Access</h2>
          <p>
            API keys provided to you are confidential and should be treated as passwords.
            You are responsible for all API usage associated with your keys. We reserve the
            right to revoke API keys that are misused or compromised.
          </p>

          <h2>7. Intellectual Property</h2>
          <p>
            You retain ownership of all content you create using the Service, including
            playbooks and outcomes. We retain ownership of the Service itself, including
            its software, design, and documentation. You grant us a limited license to
            use your content solely to provide and improve the Service.
          </p>

          <h2>8. Data and Privacy</h2>
          <p>
            Your use of the Service is also governed by our{' '}
            <Link to="/privacy">Privacy Policy</Link>, which describes how we collect,
            use, and protect your information.
          </p>

          <h2>9. Service Availability</h2>
          <p>
            We strive to maintain high availability but do not guarantee uninterrupted
            access to the Service. We may perform scheduled maintenance and will provide
            reasonable notice when possible. We are not liable for any downtime or
            service interruptions.
          </p>

          <h2>10. Limitation of Liability</h2>
          <p>
            To the maximum extent permitted by law, the Service is provided "as is"
            without warranties of any kind. We shall not be liable for any indirect,
            incidental, special, or consequential damages arising from your use of
            the Service.
          </p>

          <h2>11. Termination</h2>
          <p>
            We may suspend or terminate your access to the Service at any time for
            violation of these terms. You may delete your account at any time through
            the Settings page. Upon termination, your right to use the Service ceases
            immediately.
          </p>

          <h2>12. Changes to Terms</h2>
          <p>
            We may update these Terms of Service from time to time. We will notify you
            of material changes by email or through the Service. Continued use of the
            Service after changes constitutes acceptance of the updated terms.
          </p>

          <h2>13. Contact</h2>
          <p>
            If you have questions about these Terms of Service, please contact us at
            support@aceagent.io.
          </p>

          <div className={styles.footer}>
            <Link to="/privacy" className={styles.footerLink}>
              Privacy Policy
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
