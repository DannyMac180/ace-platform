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
} from 'lucide-react';
import { useState } from 'react';
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

  const navItems = [
    { to: '/dashboard', icon: BookOpen, label: 'Playbooks' },
    { to: '/api-keys', icon: Key, label: 'API Keys' },
    { to: '/usage', icon: BarChart3, label: 'Usage' },
    { to: '/settings', icon: Settings, label: 'Settings' },
  ];

  return (
    <div className={styles.layout}>
      {/* Mobile header */}
      <header className={styles.mobileHeader}>
        <button
          className={styles.menuButton}
          onClick={() => setIsSidebarOpen(!isSidebarOpen)}
        >
          {isSidebarOpen ? <X size={24} /> : <Menu size={24} />}
        </button>
        <div className={styles.mobileLogo}>
          <svg viewBox="0 0 32 32" fill="none" className={styles.logoIcon}>
            <path
              d="M16 2L2 9v14l14 7 14-7V9L16 2z"
              stroke="currentColor"
              strokeWidth="1.5"
              fill="none"
            />
            <circle cx="16" cy="16" r="3" fill="currentColor" />
          </svg>
          <span>ACE</span>
        </div>
      </header>

      {/* Sidebar */}
      <aside className={`${styles.sidebar} ${isSidebarOpen ? styles.open : ''}`}>
        <div className={styles.sidebarContent}>
          {/* Logo */}
          <div className={styles.logo}>
            <svg viewBox="0 0 32 32" fill="none" className={styles.logoIcon}>
              <path
                d="M16 2L2 9v14l14 7 14-7V9L16 2z"
                stroke="currentColor"
                strokeWidth="1.5"
                fill="none"
              />
              <path
                d="M16 16L2 9M16 16l14-7M16 16v14"
                stroke="currentColor"
                strokeWidth="1.5"
              />
              <circle cx="16" cy="16" r="3" fill="currentColor" />
            </svg>
            <span className={styles.logoText}>ACE Platform</span>
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
          </nav>

          {/* User section */}
          <div className={styles.userSection}>
            <div className={styles.userInfo}>
              <div className={styles.avatar}>
                {user?.email?.charAt(0).toUpperCase()}
              </div>
              <div className={styles.userDetails}>
                <span className={styles.userEmail}>{user?.email}</span>
                <span className={styles.userTier}>{user?.subscription_tier || 'Free'}</span>
              </div>
            </div>
            <button className={styles.logoutButton} onClick={handleLogout}>
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
