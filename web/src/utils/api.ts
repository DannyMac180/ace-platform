import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import type {
  ApiKey,
  ApiKeyCreate,
  ApiKeyCreateResponse,
  DailyUsage,
  EvolutionJob,
  Outcome,
  OutcomeCreate,
  PaginatedResponse,
  Playbook,
  PlaybookCreate,
  PlaybookListItem,
  PlaybookUpdate,
  PlaybookUsage,
  PlaybookVersion,
  TokenResponse,
  UsageSummary,
  User,
} from '../types';

// Use empty string for proxy in dev, or VITE_API_URL in production
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Token management
let accessToken: string | null = localStorage.getItem('access_token');
let refreshToken: string | null = localStorage.getItem('refresh_token');

export const setTokens = (tokens: TokenResponse) => {
  accessToken = tokens.access_token;
  refreshToken = tokens.refresh_token;
  localStorage.setItem('access_token', tokens.access_token);
  localStorage.setItem('refresh_token', tokens.refresh_token);
};

export const clearTokens = () => {
  accessToken = null;
  refreshToken = null;
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
};

export const getAccessToken = () => accessToken;

// Request interceptor to add auth header
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
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

    // Only attempt refresh if: 401 error, have refresh token, have original request, not already retried
    if (
      error.response?.status === 401 &&
      refreshToken &&
      originalRequest &&
      !originalRequest._retry
    ) {
      originalRequest._retry = true;

      try {
        // Reuse existing refresh promise to prevent race conditions
        if (!refreshPromise) {
          refreshPromise = axios
            .post<TokenResponse>(`${API_BASE_URL}/auth/refresh`, {
              refresh_token: refreshToken,
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
    const response = await api.post<TokenResponse>('/auth/refresh', {
      refresh_token: refreshToken,
    });
    setTokens(response.data);
    return response.data;
  },

  getMe: async (): Promise<User> => {
    const response = await api.get<User>('/auth/me');
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
