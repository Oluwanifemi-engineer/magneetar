/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach, beforeAll } from '@jest/globals';
import { render, screen, act, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/jest-globals';

jest.mock('next/link', () => {
  const Link = ({ href, children, ...props }: any) => (
    <a href={href} {...props}>{children}</a>
  );
  return Link;
});

// useSearchParams needs a router context — return controllable query params.
let mockParams: URLSearchParams;
jest.mock('next/navigation', () => ({
  useSearchParams: () => mockParams,
}));

const mockSetCredentials = jest.fn();
const mockSetConnected = jest.fn();
jest.mock('@/store/useStore', () => ({
  useStore: () => ({
    setCredentials: mockSetCredentials,
    setConnected: mockSetConnected,
  }),
}));

import ResetPasswordPage from '@/app/reset-password/page';

const mockFetch = jest.fn<(...args: any[]) => any>();

beforeAll(() => {
  (global as any).fetch = mockFetch;
});

async function renderPage() {
  await act(async () => {
    render(<ResetPasswordPage />);
  });
}

describe('Reset Password Page', () => {
  beforeEach(() => {
    sessionStorage.clear();
    mockFetch.mockClear();
    mockSetCredentials.mockClear();
    mockSetConnected.mockClear();
    mockParams = new URLSearchParams('email=user@example.com&token=reset-token-123');
  });

  it('renders the new-password form from the emailed link', async () => {
    await renderPage();
    expect(screen.getByText('Choose a new password')).toBeInTheDocument();
    expect(screen.getByText(/user@example.com/i)).toBeInTheDocument();
  });

  it('shows the broken-link state when email/token are missing', async () => {
    mockParams = new URLSearchParams('');
    await renderPage();
    expect(await screen.findByText('Broken reset link')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /request a new link/i })).toHaveAttribute('href', '/forgot-password');
  });

  it('rejects a weak password', async () => {
    await renderPage();
    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'weak' } });
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'weak' } });
    await act(async () => {
      fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    });
    expect(screen.getByRole('alert')).toHaveTextContent('at least 8 characters');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('rejects mismatched confirmation', async () => {
    await renderPage();
    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'StrongPass123' } });
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'DifferentPass123' } });
    await act(async () => {
      fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    });
    expect(screen.getByRole('alert')).toHaveTextContent('Passwords do not match');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('resets the password, stores the returned tokens and shows success', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ token: 'new-jwt', refresh_token: 'rt-2' }),
    });
    await renderPage();
    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'StrongPass123' } });
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'StrongPass123' } });
    await act(async () => {
      fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    });

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.magneetar.me/api/auth/reset-password',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ email: 'user@example.com', token: 'reset-token-123', new_password: 'StrongPass123' }),
      })
    );
    expect(await screen.findByText('Password updated')).toBeInTheDocument();
    expect(sessionStorage.getItem('mt_api_key')).toBe('new-jwt');
    expect(sessionStorage.getItem('mt_auth_mode')).toBe('user');
    expect(mockSetCredentials).toHaveBeenCalledWith('https://api.magneetar.me', 'new-jwt');
  });

  it('shows a clear message for an expired link (401)', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Invalid or expired token' }),
    });
    await renderPage();
    fireEvent.change(screen.getByLabelText('New password'), { target: { value: 'StrongPass123' } });
    fireEvent.change(screen.getByLabelText('Confirm password'), { target: { value: 'StrongPass123' } });
    await act(async () => {
      fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    });
    expect(await screen.findByRole('alert')).toHaveTextContent(/invalid or expired/i);
    expect(sessionStorage.getItem('mt_api_key')).toBeNull();
  });
});
