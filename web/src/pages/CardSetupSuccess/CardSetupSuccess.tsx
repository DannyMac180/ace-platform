import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { CheckCircle } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { Button } from '../../components/ui/Button';
import styles from './CardSetupSuccess.module.css';

export function CardSetupSuccess() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { refreshUser } = useAuth();
  const sessionId = searchParams.get('session_id');

  useEffect(() => {
    // Refresh user data to get updated has_payment_method status
    refreshUser();
  }, [refreshUser]);

  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <div className={styles.iconWrapper}>
          <CheckCircle size={64} className={styles.icon} />
        </div>
        <h1>Card Added Successfully</h1>
        <p>Your payment method has been saved. You can now trigger evolutions on your playbooks.</p>
        {sessionId && (
          <p className={styles.sessionId}>Session ID: {sessionId.slice(0, 20)}...</p>
        )}
        <Button onClick={() => navigate('/dashboard')}>Go to Dashboard</Button>
      </div>
    </div>
  );
}
