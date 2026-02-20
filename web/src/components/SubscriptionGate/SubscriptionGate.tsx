import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { billingApi } from '../../utils/api';
import styles from './SubscriptionGate.module.css';

interface SubscriptionGateProps {
  children: React.ReactNode;
  /** Optional custom message for the modal */
  featureName?: string;
}

/**
 * Wraps interactive elements to gate them behind subscription.
 * Shows appropriate modal based on user's trial status.
 */
export function SubscriptionGate({ children, featureName = 'this feature' }: SubscriptionGateProps) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [showModal, setShowModal] = useState(false);
  const [isStartingTrial, setIsStartingTrial] = useState(false);
  const [trialError, setTrialError] = useState<string | null>(null);

  const hasActiveSubscription = user?.subscription_status === 'active' && user?.subscription_tier;
  const hasUsedTrial = user?.has_used_trial ?? false;

  // If user has subscription, render children directly
  if (hasActiveSubscription) {
    return <>{children}</>;
  }

  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setShowModal(true);
    setTrialError(null);
  };

  const handleStartTrial = async () => {
    if (hasUsedTrial) {
      setShowModal(false);
      navigate('/pricing');
      return;
    }

    setIsStartingTrial(true);
    setTrialError(null);

    try {
      const result = await billingApi.startStarterTrial();
      if (result.success && result.checkout_url) {
        window.location.href = result.checkout_url;
        return;
      }

      setTrialError(result.message || 'Failed to start trial. Please try again.');
    } catch {
      setTrialError('Failed to start trial. Please try again.');
    } finally {
      setIsStartingTrial(false);
    }
  };

  const handleViewPlans = () => {
    setShowModal(false);
    navigate('/pricing');
  };

  const handleClose = () => {
    setShowModal(false);
    setTrialError(null);
    setIsStartingTrial(false);
  };

  return (
    <>
      <div onClickCapture={handleClick} className={styles.gatedWrapper}>
        {children}
      </div>

      {showModal && (
        <div className={styles.modalOverlay} onClick={handleClose}>
          <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
            <button className={styles.closeButton} onClick={handleClose}>
              &times;
            </button>

            <div className={styles.modalContent}>
              {hasUsedTrial ? (
                <>
                  <div className={styles.icon}>
                    <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M12 2L15.09 8.26L22 9.27L17 14.14L18.18 21.02L12 17.77L5.82 21.02L7 14.14L2 9.27L8.91 8.26L12 2Z" />
                    </svg>
                  </div>
                  <h2>Upgrade to Access {featureName}</h2>
                  <p>
                    Your free trial has ended. Upgrade your plan to continue using {featureName} and unlock all features.
                  </p>
                  <button className={styles.primaryButton} onClick={handleStartTrial}>
                    View Plans
                  </button>
                </>
              ) : (
                <>
                  <div className={styles.icon}>
                    <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <h2>Start Your Free Trial</h2>
                  <p>
                    To use {featureName}, start your 7-day free trial. Card required, no charge today.
                    Your trial includes 1 playbook and 5 evolutions.
                  </p>
                  {trialError && <p className={styles.error}>{trialError}</p>}
                  <div className={styles.actions}>
                    <button
                      className={styles.primaryButton}
                      onClick={handleStartTrial}
                      disabled={isStartingTrial}
                    >
                      {isStartingTrial ? 'Starting trial...' : 'Start Free Trial'}
                    </button>
                    <button
                      className={styles.secondaryButton}
                      onClick={handleViewPlans}
                      disabled={isStartingTrial}
                    >
                      See all plans
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
