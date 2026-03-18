import { beforeEach, describe, expect, it, vi } from 'vitest';

import { api, authApi, clearTokens, getAccessToken, setTokens } from './api';

describe('authApi hosted routes', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    clearTokens();
  });

  it('uses hosted login and stores returned tokens', async () => {
    vi.spyOn(api, 'post').mockResolvedValue({
      data: {
        access_token: 'access-token',
        refresh_token: 'refresh-token',
        token_type: 'bearer',
      },
    });

    const response = await authApi.login('user@example.com', 'password123');

    expect(api.post).toHaveBeenCalledWith('/v1/auth/login', {
      email: 'user@example.com',
      password: 'password123',
    });
    expect(response.access_token).toBe('access-token');
    expect(getAccessToken()).toBe('access-token');
    expect(localStorage.getItem('refresh_token')).toBe('refresh-token');
  });

  it('uses hosted refresh and replaces stored tokens', async () => {
    setTokens({
      access_token: 'stale-access',
      refresh_token: 'stale-refresh',
      token_type: 'bearer',
    });
    vi.spyOn(api, 'post').mockResolvedValue({
      data: {
        access_token: 'fresh-access',
        refresh_token: 'fresh-refresh',
        token_type: 'bearer',
      },
    });

    const response = await authApi.refresh();

    expect(api.post).toHaveBeenCalledWith('/v1/auth/refresh', {
      refresh_token: 'stale-refresh',
    });
    expect(response.access_token).toBe('fresh-access');
    expect(getAccessToken()).toBe('fresh-access');
    expect(localStorage.getItem('refresh_token')).toBe('fresh-refresh');
  });

  it('calls hosted logout before clearing local tokens', async () => {
    setTokens({
      access_token: 'access-token',
      refresh_token: 'refresh-token',
      token_type: 'bearer',
    });
    vi.spyOn(api, 'post').mockResolvedValue({ data: { message: 'Logged out' } });

    await authApi.logout();

    expect(api.post).toHaveBeenCalledWith('/v1/auth/logout');
    expect(getAccessToken()).toBeNull();
    expect(localStorage.getItem('refresh_token')).toBeNull();
  });

  it('loads the current user from the hosted profile endpoint', async () => {
    vi.spyOn(api, 'get').mockResolvedValue({
      data: {
        id: 'user-1',
        email: 'user@example.com',
      },
    });

    const response = await authApi.getMe();

    expect(api.get).toHaveBeenCalledWith('/v1/me');
    expect(response.email).toBe('user@example.com');
  });
});
