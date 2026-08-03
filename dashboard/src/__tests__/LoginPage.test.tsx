/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach, beforeAll } from '@jest/globals';
import { render, screen, act, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/jest-globals';

// next/link requires a router context in tests — render a plain anchor instead.
jest.mock('next/link', () => {
  const Link = ({ href, children, ...props }: any) => (
    <a href={href} {...props}>{children}</a>
  );
  return Link;
});

const mockSetCredentials = jest.fn();
const mockSetConnected = jest.fn();

jest.mock('@/store/useStore', () => ({
  useStore: () => ({
    setCredentials: mockSetCredentials,
    setConnected: mockSetConnected,
  }),
}));

import LoginPage from '@/app/login/page';

const mockFetch = jest.fn<(...args: any[]) => any>();

beforeAll(() => {
  (global as any).fetch = mockFetch;
});

async function renderPage() {
  await act(async () => {
    render(<LoginPage />);
  });
}

describe('Login Page', () => {
  beforeEach(() => {
    sessionStorage.clear();
    mockFetch.mockClear();
    mockSetCredentials.mockClear();
    mockSetConnected.mockClear();
  });

  it('renders the split layout and defaults to account mode', async () => {
    await renderPage();
    expect(screen.getByText('Welcome back')).toBeInTheDocument();
    expect(screen.getByText('Your devices,')).toBeInTheDocument();
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    // Server URL is prefilled after mount
    expect(await screen.findByDisplayValue('https://api.magneetar.me')).toBeInTheDocument();
  });

  it('switches to API key mode and back', async () => {
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'API Key' }));
    expect(await screen.findByLabelText('API Key')).toBeInTheDocument();
    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Account' }));
    expect(await screen.findByLabelText('Email')).toBeInTheDocument();
    expect(screen.queryByLabelText('API Key')).not.toBeInTheDocument();
  });

  it('validates the server URL', async () => {
    await renderPage();
    const serverUrl = screen.getByLabelText('Server URL');
    await act(async () => {
      fireEvent.change(serverUrl, { target: { value: '' } });
      fireEvent.submit(serverUrl.closest('form') as HTMLFormElement);
    });
    expect(screen.getByRole('alert')).toHaveTextContent('Please enter your server URL.');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('requires email and password in account mode', async () => {
    await renderPage();
    await act(async () => {
      fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    });
    expect(screen.getByRole('alert')).toHaveTextContent('Please enter your email and password.');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('requires an API key in API key mode', async () => {
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'API Key' }));
    await act(async () => {
      fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    });
    expect(screen.getByRole('alert')).toHaveTextContent('Please enter your API key.');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('logs in with an account and redirects to the dashboard', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ token: 'user-jwt', refresh_token: 'rt-1' }),
    });
    await renderPage();
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'user@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'StrongPass1' } });

    await act(async () => {
      fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    });

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.magneetar.me/api/auth/user/login',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: 'user@example.com', password: 'StrongPass1' }),
      })
    );
    expect(sessionStorage.getItem('mt_auth_mode')).toBe('user');
    expect(sessionStorage.getItem('mt_api_key')).toBe('user-jwt');
    expect(sessionStorage.getItem('mt_server_url')).toBe('https://api.magneetar.me');
    expect(mockSetCredentials).toHaveBeenCalledWith('https://api.magneetar.me', 'user-jwt');
    expect(mockSetConnected).toHaveBeenCalledWith(true);
  });

  it('logs in with an API key and redirects (stores the dashboard JWT, not the raw key)', async () => {
    // Security (F-02): the login endpoint exchanges the key for a dashboard
    // JWT. The client must store THAT token — storing the raw key and sending
    // it as x-api-key made anyone with an APK a platform admin.
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ token: 'dashboard-jwt', refresh_token: 'rt-1', token_type: 'bearer' }),
    });
    await renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'API Key' }));
    fireEvent.change(await screen.findByLabelText('API Key'), { target: { value: 'sk-123' } });

    await act(async () => {
      fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    });

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.magneetar.me/api/auth/login',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ api_key: 'sk-123' }),
      })
    );
    expect(sessionStorage.getItem('mt_auth_mode')).toBe('apikey');
    expect(sessionStorage.getItem('mt_api_key')).toBe('dashboard-jwt');
    expect(mockSetCredentials).toHaveBeenCalledWith('https://api.magneetar.me', 'dashboard-jwt');
  });

  it('shows a readable error when login fails', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'Invalid credentials' }),
    });
    await renderPage();
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'user@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong' } });

    await act(async () => {
      fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    });

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid credentials');
  });

  it('toggles password visibility', async () => {
    await renderPage();
    const password = screen.getByLabelText('Password') as HTMLInputElement;
    expect(password).toHaveAttribute('type', 'password');

    fireEvent.click(screen.getByRole('button', { name: 'Show password' }));
    expect(password).toHaveAttribute('type', 'text');

    fireEvent.click(screen.getByRole('button', { name: 'Hide password' }));
    expect(password).toHaveAttribute('type', 'password');
  });
});
