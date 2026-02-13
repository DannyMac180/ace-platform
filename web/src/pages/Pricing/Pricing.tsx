import { useState } from 'react';
import { AlertCircle, Clock } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { api } from '../../utils/api';
import { PricingCard, type PricingTier } from './PricingCard';
import styles from './Pricing.module.css';

type BillingInterval = 'month' | 'year';

interface PricingTierTemplate extends Omit<PricingTier, 'price' | 'period'> {
  monthlyPrice: number;
  yearlyPrice: number;
}

const PRICING_TIERS: PricingTierTemplate[] = [
  {
    id: 'starter',
    name: 'Starter',
    monthlyPrice: 9,
    yearlyPrice: 90,
    description: 'Perfect for individuals getting started',
    features: [
      '100 evolution runs/month',
      '5 playbooks',
      'Premium AI models',
      'Data export',
    ],
    highlighted: ['100 evolution runs/month', '5 playbooks'],
  },
  {
    id: 'pro',
    name: 'Pro',
    monthlyPrice: 29,
    yearlyPrice: 290,
    description: 'For professionals who need more power',
    features: [
      '500 evolution runs/month',
      '20 playbooks',
      'Premium AI models',
      'Data export',
    ],
    highlighted: ['500 evolution runs/month', '20 playbooks'],
    isPopular: true,
  },
  {
    id: 'ultra',
    name: 'Ultra',
    monthlyPrice: 79,
    yearlyPrice: 790,
    description: 'Maximum power for demanding workflows',
    features: [
      '2,000 evolution runs/month',
      '100 playbooks',
      'Premium AI models',
      'Data export',
    ],
    highlighted: ['2,000 evolution runs/month', '100 playbooks'],
  },
];

const getDisplayTiers = (interval: BillingInterval): PricingTier[] => {
  return PRICING_TIERS.map((tier) => {
    if (interval === 'month') {
      return {
        ...tier,
        price: tier.monthlyPrice,
        period: 'month',
        buttonPeriodLabel: 'mo',
      };
    }

    return {
      ...tier,
      price: tier.yearlyPrice,
      period: 'year',
      buttonPeriodLabel: 'yr',
      discountLabel: '17% off',
      monthlyEquivalent: Number((tier.yearlyPrice / 12).toFixed(2)),
    };
  });
};

interface SubscribeResponse {
  success: boolean;
  message: string;
  checkout_url: string | null;
  subscription: unknown | null;
}

export function Pricing() {
  const { user } = useAuth();
  const [billingInterval, setBillingInterval] = useState<BillingInterval>('month');
  const [loadingTier, setLoadingTier] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const currentTier = user?.subscription_tier?.toLowerCase() || 'free';
  const canUseTrial = !user?.has_used_trial;
  const displayedTiers = getDisplayTiers(billingInterval);

  // Check if user is currently on a free trial
  const getTrialDaysRemaining = () => {
    if (!user?.trial_ends_at) return null;
    const trialEnd = new Date(user.trial_ends_at);
    const now = new Date();
    const diffTime = trialEnd.getTime() - now.getTime();
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    return diffDays > 0 ? diffDays : null;
  };
  const trialDaysRemaining = getTrialDaysRemaining();
  const isOnTrial = trialDaysRemaining !== null;

  const handleSubscribe = async (tierId: string) => {
    setError(null);
    setLoadingTier(tierId);

    try {
      const response = await api.post<SubscribeResponse>('/billing/subscribe', {
        tier: tierId,
        interval: billingInterval,
      });

      if (response.data.checkout_url) {
        // Redirect to Stripe checkout
        window.location.href = response.data.checkout_url;
      } else if (response.data.success) {
        // Free tier or immediate subscription succeeded
        window.location.reload();
      } else {
        // Checkout creation failed - show error
        setError(response.data.message || 'Failed to create checkout session');
      }
    } catch (err: unknown) {
      const errorMessage =
        err instanceof Error
          ? err.message
          : (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
            'Failed to process subscription. Please try again.';
      setError(errorMessage);
    } finally {
      setLoadingTier(null);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h1>Choose Your Plan</h1>
        <p>Scale your playbook evolution with the right plan for your needs</p>
      </div>

      <div className={styles.billingToggle} role="group" aria-label="Billing interval">
        <button
          type="button"
          className={`${styles.toggleOption} ${
            billingInterval === 'month' ? styles.toggleOptionActive : ''
          }`}
          onClick={() => setBillingInterval('month')}
        >
          Monthly
        </button>
        <button
          type="button"
          className={`${styles.toggleOption} ${
            billingInterval === 'year' ? styles.toggleOptionActive : ''
          }`}
          onClick={() => setBillingInterval('year')}
        >
          Yearly
          <span className={styles.toggleDiscount}>Save 17%</span>
        </button>
      </div>

      {trialDaysRemaining !== null && (
        <div className={styles.trialLimitsBanner}>
          <Clock size={18} />
          <span>
            You&apos;re on a free trial ({trialDaysRemaining} day{trialDaysRemaining !== 1 ? 's' : ''} remaining) with limited access: 1 playbook and 5 evolutions. Subscribe to unlock more.
          </span>
        </div>
      )}

      {error && (
        <div className={styles.error}>
          <AlertCircle size={20} />
          <span>{error}</span>
        </div>
      )}

      <div className={styles.grid}>
        {displayedTiers.map((tier) => (
          <PricingCard
            key={tier.id}
            tier={tier}
            isCurrentPlan={currentTier === tier.id && !isOnTrial}
            isLoading={loadingTier === tier.id}
            onSubscribe={handleSubscribe}
            showTrialCTA={canUseTrial}
          />
        ))}
      </div>

    </div>
  );
}
