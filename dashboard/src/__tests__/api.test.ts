/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import '@testing-library/jest-dom/jest-globals';

import MagneetarAPI from '@/lib/api';

const mockFetch = jest.fn<(...args: any[]) => any>();

beforeEach(() => {
  mockFetch.mockReset();
  (global as any).fetch = mockFetch;
  sessionStorage.clear();
});

describe('MagneetarAPI headers — session fallback', () => {
  it('sends the session JWT as Bearer when the instance has no key (user mode)', async () => {
    sessionStorage.setItem('mt_auth_mode', 'user');
    sessionStorage.setItem('mt_api_key', 'session-jwt');
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({ devices: [] }) });

    // Constructed without credentials — mirrors getAPI() called with no args
    // before useDevices() sets credentials on the singleton (the Sidebar 401 bug).
    const api = new MagneetarAPI('https://api.magneetar.me');
    await api.getDevices();

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.magneetar.me/api/dashboard/devices',
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: 'Bearer session-jwt',
        }),
      })
    );
  });

  it('sends the session API key as x-api-key in apikey mode', async () => {
    sessionStorage.setItem('mt_auth_mode', 'apikey');
    sessionStorage.setItem('mt_api_key', 'sk-session');
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({ devices: [] }) });

    const api = new MagneetarAPI('https://api.magneetar.me');
    await api.getDevices();

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.magneetar.me/api/dashboard/devices',
      expect.objectContaining({
        headers: expect.objectContaining({ 'x-api-key': 'sk-session' }),
      })
    );
  });

  it('prefers explicitly set credentials over the session token', async () => {
    sessionStorage.setItem('mt_auth_mode', 'user');
    sessionStorage.setItem('mt_api_key', 'session-jwt');
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({ devices: [] }) });

    const api = new MagneetarAPI('https://api.magneetar.me', 'explicit-key');
    await api.getDevices();

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.magneetar.me/api/dashboard/devices',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer explicit-key' }),
      })
    );
  });

  it('still sends an empty Bearer when nothing is configured (logged out)', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({ devices: [] }) });

    const api = new MagneetarAPI('https://api.magneetar.me');
    await api.getDevices();

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.magneetar.me/api/dashboard/devices',
      expect.objectContaining({
        headers: expect.objectContaining({ 'x-api-key': '' }),
      })
    );
  });
});
