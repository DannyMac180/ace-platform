import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { Layout } from './components/Layout/Layout';
import { AuthPage } from './pages/Auth/AuthPage';
import { OAuthCallback } from './pages/OAuthCallback/OAuthCallback';
import { VerifyEmail } from './pages/VerifyEmail/VerifyEmail';
import { Dashboard } from './pages/Dashboard/Dashboard';
import { PlaybookDetail } from './pages/PlaybookDetail/PlaybookDetail';
import { PlaybookContentEditor } from './pages/PlaybookContentEditor/PlaybookContentEditor';
import { ApiKeys } from './pages/ApiKeys/ApiKeys';
import { Usage } from './pages/Usage/Usage';
import { Settings } from './pages/Settings/Settings';
import { Pricing } from './pages/Pricing/Pricing';
import { BillingSuccess } from './pages/BillingSuccess/BillingSuccess';
import { BillingCancel } from './pages/BillingCancel/BillingCancel';
import { CardSetupSuccess } from './pages/CardSetupSuccess/CardSetupSuccess';
import './styles/globals.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60 * 5, // 5 minutes
      retry: 1,
    },
  },
});

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="loading-screen">
        <div className="loading-spinner" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <Layout>{children}</Layout>;
}

function PublicRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="loading-screen">
        <div className="loading-spinner" />
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
}

function AppRoutes() {
  return (
    <Routes>
      {/* Public routes */}
      <Route
        path="/login"
        element={
          <PublicRoute>
            <AuthPage />
          </PublicRoute>
        }
      />
      <Route
        path="/register"
        element={
          <PublicRoute>
            <AuthPage />
          </PublicRoute>
        }
      />
      <Route path="/oauth/callback" element={<OAuthCallback />} />
      <Route path="/verify-email" element={<VerifyEmail />} />

      {/* Billing callback routes */}
      <Route
        path="/billing/success"
        element={
          <ProtectedRoute>
            <BillingSuccess />
          </ProtectedRoute>
        }
      />
      <Route
        path="/billing/setup-success"
        element={
          <ProtectedRoute>
            <CardSetupSuccess />
          </ProtectedRoute>
        }
      />
      <Route
        path="/billing/cancel"
        element={
          <ProtectedRoute>
            <BillingCancel />
          </ProtectedRoute>
        }
      />

      {/* Protected routes - accessible by all authenticated users */}
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        }
      />
      <Route
        path="/playbooks/:id"
        element={
          <ProtectedRoute>
            <PlaybookDetail />
          </ProtectedRoute>
        }
      />
      <Route
        path="/playbooks/:id/edit"
        element={
          <ProtectedRoute>
            <PlaybookContentEditor />
          </ProtectedRoute>
        }
      />
      <Route
        path="/api-keys"
        element={
          <ProtectedRoute>
            <ApiKeys />
          </ProtectedRoute>
        }
      />
      <Route
        path="/usage"
        element={
          <ProtectedRoute>
            <Usage />
          </ProtectedRoute>
        }
      />

      {/* Protected routes (no subscription required) */}
      <Route
        path="/settings"
        element={
          <ProtectedRoute>
            <Settings />
          </ProtectedRoute>
        }
      />
      <Route
        path="/pricing"
        element={
          <ProtectedRoute>
            <Pricing />
          </ProtectedRoute>
        }
      />

      {/* Redirects */}
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
