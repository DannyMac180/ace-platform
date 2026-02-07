import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import type {
  ApiKey,
  ApiKeyCreate,
  ApiKeyCreateResponse,
  AuditLogItem,
  DailyEvolution,
  DailyUsage,
  EvolutionJob,
  EvolutionSummary,
  Outcome,
  OutcomeCreate,
  PaginatedResponse,
  Playbook,
  PlaybookCreate,
  PlaybookEvolutionStats,
  PlaybookListItem,
  PlaybookUpdate,
  PlaybookUsage,
  PlaybookVersion,
  RecentEvolution,
  TokenResponse,
  UsageSummary,
  User,
  VersionCreate,
} from '../types';

// Use empty string for proxy in dev, or VITE_API_URL in production
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Token management - localStorage is the source of truth
export const setTokens = (tokens: TokenResponse) => {
  localStorage.setItem('access_token', tokens.access_token);
  localStorage.setItem('refresh_token', tokens.refresh_token);
};

export const clearTokens = () => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
};

export const getAccessToken = () => localStorage.getItem('access_token');

// Request interceptor to add auth header
// Always read fresh from localStorage to ensure we have the latest token
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  // Always read from localStorage to ensure we have the most current token
  // This prevents stale token issues after page refresh or HMR
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Token refresh promise to prevent race conditions
let refreshPromise: Promise<TokenResponse> | null = null;

// Extend AxiosRequestConfig to include retry flag
interface RetryableRequest extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

// Response interceptor for token refresh
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetryableRequest | undefined;
    // Always read refresh token fresh from localStorage
    const currentRefreshToken = localStorage.getItem('refresh_token');

    // Only attempt refresh if: 401 error, have refresh token, have original request, not already retried
    if (
      error.response?.status === 401 &&
      currentRefreshToken &&
      originalRequest &&
      !originalRequest._retry
    ) {
      originalRequest._retry = true;

      try {
        // Reuse existing refresh promise to prevent race conditions
        if (!refreshPromise) {
          refreshPromise = axios
            .post<TokenResponse>(`${API_BASE_URL}/auth/refresh`, {
              refresh_token: currentRefreshToken,
            })
            .then((res) => res.data)
            .finally(() => {
              refreshPromise = null;
            });
        }

        const tokens = await refreshPromise;
        setTokens(tokens);
        originalRequest.headers.Authorization = `Bearer ${tokens.access_token}`;
        return api(originalRequest);
      } catch {
        clearTokens();
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

// Auth API
export const authApi = {
  register: async (email: string, password: string): Promise<TokenResponse> => {
    const response = await api.post<TokenResponse>('/auth/register', { email, password });
    setTokens(response.data);
    return response.data;
  },

  login: async (email: string, password: string): Promise<TokenResponse> => {
    const response = await api.post<TokenResponse>('/auth/login', { email, password });
    setTokens(response.data);
    return response.data;
  },

  logout: () => {
    clearTokens();
  },

  refresh: async (): Promise<TokenResponse> => {
    const currentRefreshToken = localStorage.getItem('refresh_token');
    const response = await api.post<TokenResponse>('/auth/refresh', {
      refresh_token: currentRefreshToken,
    });
    setTokens(response.data);
    return response.data;
  },

  getMe: async (): Promise<User> => {
    const response = await api.get<User>('/auth/me');
    return response.data;
  },

  forgotPassword: async (email: string): Promise<{ message: string }> => {
    const response = await api.post<{ message: string }>('/auth/forgot-password', { email });
    return response.data;
  },

  resetPassword: async (token: string, newPassword: string): Promise<{ message: string }> => {
    const response = await api.post<{ message: string }>('/auth/reset-password', {
      token,
      new_password: newPassword,
    });
    return response.data;
  },

  setPassword: async (newPassword: string): Promise<{ message: string }> => {
    const response = await api.post<{ message: string }>('/auth/set-password', {
      new_password: newPassword,
    });
    return response.data;
  },

  changePassword: async (
    currentPassword: string,
    newPassword: string
  ): Promise<{ message: string }> => {
    const response = await api.post<{ message: string }>('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
    return response.data;
  },

  getOAuthCsrfToken: async (): Promise<string> => {
    // NOTE: We use native fetch instead of axios here because:
    // 1. CSRF tokens require session cookies (credentials: 'include')
    // 2. Axios is configured for JWT auth (Authorization header), not session cookies
    // 3. The OAuth flow uses session-based state, separate from JWT auth
    // This ensures the session cookie is sent/received for CSRF token storage.
    const apiBaseUrl = import.meta.env.VITE_API_URL || '';
    const response = await fetch(`${apiBaseUrl}/auth/oauth/csrf-token`, {
      method: 'GET',
      credentials: 'include',
    });
    if (!response.ok) {
      throw new Error('Failed to get CSRF token');
    }
    const data = await response.json();
    return data.csrf_token;
  },
};

// Account API
export const accountApi = {
  exportData: async () => {
    return api.get('/account/export', { responseType: 'blob' });
  },

  deleteAccount: async (confirm: string, password?: string): Promise<{ message: string }> => {
    const response = await api.delete<{ message: string }>('/account', {
      data: { confirm, password },
    });
    return response.data;
  },

  listAuditLogs: async (
    page = 1,
    pageSize = 20
  ): Promise<PaginatedResponse<AuditLogItem>> => {
    const response = await api.get<PaginatedResponse<AuditLogItem>>(
      `/account/audit-logs?page=${page}&page_size=${pageSize}`
    );
    return response.data;
  },
};

// API Keys API
export const apiKeysApi = {
  list: async (): Promise<ApiKey[]> => {
    const response = await api.get<ApiKey[]>('/auth/api-keys');
    return response.data;
  },

  create: async (data: ApiKeyCreate): Promise<ApiKeyCreateResponse> => {
    const response = await api.post<ApiKeyCreateResponse>('/auth/api-keys', data);
    return response.data;
  },

  delete: async (keyId: string): Promise<void> => {
    await api.delete(`/auth/api-keys/${keyId}`);
  },
};

// Playbooks API
export const playbooksApi = {
  list: async (
    page = 1,
    pageSize = 20,
    status?: string
  ): Promise<PaginatedResponse<PlaybookListItem>> => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (status) params.set('status_filter', status);
    const response = await api.get<PaginatedResponse<PlaybookListItem>>(
      `/playbooks?${params}`
    );
    return response.data;
  },

  get: async (id: string): Promise<Playbook> => {
    const response = await api.get<Playbook>(`/playbooks/${id}`);
    return response.data;
  },

  create: async (data: PlaybookCreate): Promise<Playbook> => {
    const response = await api.post<Playbook>('/playbooks', data);
    return response.data;
  },

  update: async (id: string, data: PlaybookUpdate): Promise<Playbook> => {
    const response = await api.put<Playbook>(`/playbooks/${id}`, data);
    return response.data;
  },

  delete: async (id: string): Promise<void> => {
    await api.delete(`/playbooks/${id}`);
  },

  getVersions: async (
    id: string,
    page = 1,
    pageSize = 20
  ): Promise<PaginatedResponse<PlaybookVersion>> => {
    const response = await api.get<PaginatedResponse<PlaybookVersion>>(
      `/playbooks/${id}/versions?page=${page}&page_size=${pageSize}`
    );
    return response.data;
  },

  getVersion: async (id: string, versionNumber: number): Promise<PlaybookVersion> => {
    const response = await api.get<PlaybookVersion>(
      `/playbooks/${id}/versions/${versionNumber}`
    );
    return response.data;
  },

  createVersion: async (id: string, data: VersionCreate): Promise<PlaybookVersion> => {
    const response = await api.post<PlaybookVersion>(`/playbooks/${id}/versions`, data);
    return response.data;
  },

  getOutcomes: async (
    id: string,
    page = 1,
    pageSize = 20
  ): Promise<PaginatedResponse<Outcome>> => {
    const response = await api.get<PaginatedResponse<Outcome>>(
      `/playbooks/${id}/outcomes?page=${page}&page_size=${pageSize}`
    );
    return response.data;
  },

  createOutcome: async (id: string, data: OutcomeCreate): Promise<Outcome> => {
    const response = await api.post<Outcome>(`/playbooks/${id}/outcomes`, data);
    return response.data;
  },

  getEvolutions: async (
    id: string,
    page = 1,
    pageSize = 20
  ): Promise<PaginatedResponse<EvolutionJob>> => {
    const response = await api.get<PaginatedResponse<EvolutionJob>>(
      `/playbooks/${id}/evolutions?page=${page}&page_size=${pageSize}`
    );
    return response.data;
  },

  triggerEvolution: async (id: string): Promise<{ job_id: string; is_new: boolean; status: string }> => {
    const response = await api.post<{ job_id: string; is_new: boolean; status: string }>(
      `/playbooks/${id}/evolve`
    );
    return response.data;
  },
};

// Usage API
export const usageApi = {
  getSummary: async (): Promise<UsageSummary> => {
    const response = await api.get<UsageSummary>('/usage/summary');
    return response.data;
  },

  getDaily: async (days = 30): Promise<DailyUsage[]> => {
    const response = await api.get<DailyUsage[]>(`/usage/daily?days=${days}`);
    return response.data;
  },

  getByPlaybook: async (): Promise<PlaybookUsage[]> => {
    const response = await api.get<PlaybookUsage[]>('/usage/by-playbook');
    return response.data;
  },
};

// Billing API
export const billingApi = {
  setupCard: async (): Promise<{ success: boolean; checkout_url: string | null; message: string }> => {
    const response = await api.post<{ success: boolean; checkout_url: string | null; message: string }>(
      '/billing/setup-card'
    );
    return response.data;
  },

  getCardStatus: async (): Promise<{ has_payment_method: boolean; payment_method_id: string | null }> => {
    const response = await api.get<{ has_payment_method: boolean; payment_method_id: string | null }>(
      '/billing/card-status'
    );
    return response.data;
  },
};

// Evolution Statistics API
export const evolutionsApi = {
  getSummary: async (): Promise<EvolutionSummary> => {
    const response = await api.get<EvolutionSummary>('/evolutions/summary');
    return response.data;
  },

  getDaily: async (days = 30): Promise<DailyEvolution[]> => {
    const response = await api.get<DailyEvolution[]>(`/evolutions/daily?days=${days}`);
    return response.data;
  },

  getByPlaybook: async (limit = 10): Promise<PlaybookEvolutionStats[]> => {
    const response = await api.get<PlaybookEvolutionStats[]>(
      `/evolutions/by-playbook?limit=${limit}`
    );
    return response.data;
  },

  getRecent: async (limit = 10): Promise<RecentEvolution[]> => {
    const response = await api.get<RecentEvolution[]>(`/evolutions/recent?limit=${limit}`);
    return response.data;
  },
};
