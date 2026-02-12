import { type ReactNode } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import {
  BookOpen,
  Key,
  BarChart3,
  Settings,
  LogOut,
  Menu,
  X,
  CreditCard,
  FileText,
  ExternalLink,
} from 'lucide-react';
import { useState } from 'react';
import { Logo } from '../Logo';
import styles from './Layout.module.css';

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  // Calculate trial days remaining
  const getTrialDaysRemaining = () => {
    if (!user?.trial_ends_at) return null;
    const trialEnd = new Date(user.trial_ends_at);
    const now = new Date();
    const diffTime = trialEnd.getTime() - now.getTime();
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    return diffDays > 0 ? diffDays : null;
  };

  const trialDaysRemaining = getTrialDaysRemaining();

  const docsUrl = import.meta.env.VITE_DOCS_URL || 'https://docs.aceagent.io/docs';

  const navItems = [
    { to: '/dashboard', icon: BookOpen, label: 'Playbooks' },
    { to: '/api-keys', icon: Key, label: 'API Keys' },
    { to: '/usage', icon: BarChart3, label: 'Usage' },
    { to: '/pricing', icon: CreditCard, label: 'Pricing' },
    { to: '/settings', icon: Settings, label: 'Settings' },
  ];

  return (
    <div className={styles.layout}>
      {/* Mobile header */}
      <header className={styles.mobileHeader}>
        <button
          className={styles.menuButton}
          onClick={() => setIsSidebarOpen(!isSidebarOpen)}
          aria-label={isSidebarOpen ? 'Close navigation menu' : 'Open navigation menu'}
        >
          {isSidebarOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
        <div className={styles.mobileLogo}>
          <Logo variant="full" size="sm" />
        </div>
      </header>

      {/* Sidebar */}
      <aside className={`${styles.sidebar} ${isSidebarOpen ? styles.open : ''}`}>
        <div className={styles.sidebarContent}>
          {/* Logo */}
          <div className={styles.logo}>
            <Logo variant="full" size="md" />
          </div>

          {/* Navigation */}
          <nav className={styles.nav}>
            {navItems.map(({ to, icon: Icon, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `${styles.navLink} ${isActive ? styles.active : ''}`
                }
                onClick={() => setIsSidebarOpen(false)}
              >
                <Icon size={20} />
                <span>{label}</span>
              </NavLink>
            ))}
            {/* External docs link */}
            <a
              href={docsUrl}
              target="_blank"
              rel="noopener noreferrer"
              className={styles.navLink}
              onClick={() => setIsSidebarOpen(false)}
            >
              <FileText size={20} />
              <span>Docs</span>
              <ExternalLink size={14} className={styles.externalIcon} />
            </a>
          </nav>

          {/* Trial banner */}
          {trialDaysRemaining !== null && (
            <div className={styles.trialBanner}>
              <span className={styles.trialText}>
                {trialDaysRemaining} day{trialDaysRemaining !== 1 ? 's' : ''} left in trial
              </span>
            </div>
          )}

          {/* User section */}
          <div className={styles.userSection}>
            <div className={styles.userInfo}>
              <div className={styles.avatar}>
                {user?.email?.charAt(0).toUpperCase()}
              </div>
              <div className={styles.userDetails}>
                <span className={styles.userEmail}>{user?.email}</span>
                <span className={styles.userTier}>
                  {user?.subscription_tier || 'Free'}
                  {trialDaysRemaining !== null && ' (Trial)'}
                </span>
              </div>
            </div>
            <button className={styles.logoutButton} onClick={handleLogout} aria-label="Log out">
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </aside>

      {/* Overlay for mobile */}
      {isSidebarOpen && (
        <div
          className={styles.overlay}
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* Main content */}
      <main className={styles.main}>
        {children}
      </main>
    </div>
  );
}
