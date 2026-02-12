import { useState, type FormEvent } from 'react';
import { useAuth } from '../../contexts/AuthContext';
import { api } from '../../utils/api';
import { Button } from '../../components/ui/Button';
import styles from './Support.module.css';

export function Support() {
  const { user } = useAuth();
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    setSubmitting(true);

    try {
      const res = await api.post<{ message: string }>('/support/contact', {
        subject,
        message,
      });
      setSuccess(res.data.message);
      setSubject('');
      setMessage('');
    } catch (err: unknown) {
      let msg = 'Failed to send message. Please try again.';
      if (err && typeof err === 'object' && 'response' in err) {
        const response = (err as { response?: { status?: number; data?: { error?: { message?: string } } } }).response;
        if (response?.status === 429) {
          msg = 'Too many requests. Please try again later.';
        } else if (response?.data?.error?.message) {
          msg = response.data.error.message;
        }
      }
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>Support</h1>
        <p>Have a question or need help? Send us a message and we'll get back to you.</p>
      </div>

      {success ? (
        <div className={styles.successCard}>
          <div className={styles.successIcon}>
            <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M20 6L9 17l-5-5" />
            </svg>
          </div>
          <h2>Message sent</h2>
          <p>{success}</p>
          <Button
            onClick={() => setSuccess(null)}
            variant="ghost"
          >
            Send another message
          </Button>
        </div>
      ) : (
        <section className={styles.section}>
          {error && <div className={styles.error}>{error}</div>}

          <form onSubmit={handleSubmit} className={styles.form}>
            <div className={styles.field}>
              <label htmlFor="support-email">Your email</label>
              <input
                id="support-email"
                type="email"
                value={user?.email || ''}
                disabled
                className={styles.inputDisabled}
              />
              <span className={styles.hint}>Replies will be sent to this address</span>
            </div>

            <div className={styles.field}>
              <label htmlFor="support-subject">Subject</label>
              <input
                id="support-subject"
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="Brief description of your issue"
                required
                maxLength={200}
                className={styles.input}
              />
            </div>

            <div className={styles.field}>
              <label htmlFor="support-message">Message</label>
              <textarea
                id="support-message"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Describe your issue or question in detail..."
                required
                minLength={10}
                maxLength={5000}
                rows={8}
                className={styles.textarea}
              />
              <span className={styles.charCount}>
                {message.length} / 5,000
              </span>
            </div>

            <div className={styles.actions}>
              <Button
                type="submit"
                isLoading={submitting}
                disabled={!subject.trim() || message.length < 10}
              >
                Send message
              </Button>
            </div>
          </form>
        </section>
      )}
    </div>
  );
}
