import { Check } from 'lucide-react';
import styles from './Pricing.module.css';

export interface PricingTier {
  id: string;
  name: string;
  price: number;
  period: string;
  buttonPeriodLabel?: string;
  description: string;
  features: string[];
  highlighted?: string[];
  isPopular?: boolean;
  discountLabel?: string;
  monthlyEquivalent?: number;
}

interface PricingCardProps {
  tier: PricingTier;
  isCurrentPlan: boolean;
  isLoading: boolean;
  onSubscribe: (tierId: string) => void;
  showTrialCTA?: boolean;  // Show "Start 7-Day Free Trial" for Starter tier
}

export function PricingCard({ tier, isCurrentPlan, isLoading, onSubscribe, showTrialCTA }: PricingCardProps) {
  const formatPrice = (price: number) => {
    return Number.isInteger(price) ? `${price}` : price.toFixed(2);
  };

  const getButtonText = () => {
    if (isLoading) return 'Processing...';
    if (isCurrentPlan) return 'Current Plan';
    if (showTrialCTA && tier.id === 'starter') return 'Start 7-Day Free Trial';
    return `Subscribe - $${formatPrice(tier.price)}/${tier.buttonPeriodLabel || tier.period}`;
  };

  const getButtonClass = () => {
    if (isCurrentPlan) return `${styles.ctaButton} ${styles.ctaCurrent}`;
    if (tier.isPopular) return `${styles.ctaButton} ${styles.ctaPrimary}`;
    return `${styles.ctaButton} ${styles.ctaSecondary}`;
  };

  return (
    <div className={`${styles.card} ${tier.isPopular ? styles.cardPopular : ''}`}>
      {tier.isPopular && <span className={styles.popularBadge}>Most Popular</span>}

      <div className={styles.cardHeader}>
        <h3 className={styles.tierName}>{tier.name}</h3>
        <div className={styles.price}>
          <span className={styles.priceAmount}>${formatPrice(tier.price)}</span>
          <span className={styles.pricePeriod}>/{tier.period}</span>
        </div>
        {tier.discountLabel && (
          <span className={styles.discountBadge}>{tier.discountLabel}</span>
        )}
        {tier.monthlyEquivalent && (
          <p className={styles.monthlyEquivalent}>
            ${formatPrice(tier.monthlyEquivalent)}/month equivalent
          </p>
        )}
        <p className={styles.cardDescription}>{tier.description}</p>
        {isCurrentPlan && (
          <span className={styles.currentPlanBadge}>
            <Check size={12} />
            Active
          </span>
        )}
      </div>

      <div className={styles.features}>
        {tier.features.map((feature, index) => (
          <div key={index} className={styles.featureItem}>
            <Check size={18} className={styles.featureIcon} />
            <span
              className={`${styles.featureText} ${
                tier.highlighted?.includes(feature) ? styles.featureHighlight : ''
              }`}
            >
              {feature}
            </span>
          </div>
        ))}
      </div>

      {showTrialCTA && tier.id === 'starter' && (
        <div className={styles.trialBanner}>
          <strong>7-day free trial</strong> — Card required, no charge today.
          <div className={styles.trialBannerDetail}>
            Trial includes 1 playbook and 5 evolutions. Full Starter limits unlock after trial.
          </div>
        </div>
      )}

      <button
        className={getButtonClass()}
        onClick={() => onSubscribe(tier.id)}
        disabled={isCurrentPlan || isLoading}
      >
        {getButtonText()}
      </button>
    </div>
  );
}
