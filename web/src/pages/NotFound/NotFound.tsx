import { Link } from 'react-router-dom';
import styles from './NotFound.module.css';

export function NotFound() {
  return (
    <div className={styles.container}>
      <div className={styles.card}>
        <span className={styles.code}>404</span>
        <h1 className={styles.title}>Page not found</h1>
        <p className={styles.message}>
          The page you are looking for does not exist or has been moved.
        </p>
        <Link to="/dashboard" className={styles.link}>
          Back to Dashboard
        </Link>
      </div>
    </div>
  );
}
