import { useState } from 'react';
import { CreditCard, AlertCircle } from 'lucide-react';
import { Button } from '../ui/Button';
import { billingApi } from '../../utils/api';
import styles from './CardSetupBanner.module.css';

interface CardSetupBannerProps {
  /** Message to show in the banner */
  message?: string;
  /** Called when card setup is initiated */
  onSetupInitiated?: () => void;
}

/**
 * Banner component prompting users to add a payment method.
 * Shows when FREE tier users need a card to trigger evolutions.
 */
export function CardSetupBanner({
  message = 'A payment method is required to trigger evolutions. Add a card to unlock this feature.',
  onSetupInitiated,
}: CardSetupBannerProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSetupCard = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const result = await billingApi.setupCard();

      if (result.success && result.checkout_url) {
        onSetupInitiated?.();
        // Redirect to Stripe Checkout
        window.location.href = result.checkout_url;
      } else if (result.success && !result.checkout_url) {
        // User already has a card - refresh the page
        window.location.reload();
      } else {
        setError('Failed to initiate card setup. Please try again.');
      }
    } catch (err) {
      setError('Failed to initiate card setup. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className={styles.banner}>
      <div className={styles.iconWrapper}>
        <CreditCard size={24} className={styles.icon} />
      </div>
      <div className={styles.content}>
        <p className={styles.message}>{message}</p>
        {error && (
          <p className={styles.error}>
            <AlertCircle size={14} />
            {error}
          </p>
        )}
      </div>
      <Button
        onClick={handleSetupCard}
        isLoading={isLoading}
        icon={<CreditCard size={16} />}
      >
        Add Card
      </Button>
    </div>
  );
}
