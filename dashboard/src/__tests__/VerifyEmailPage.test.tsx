/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach, beforeAll } from '@jest/globals';
import { render, screen, act } from '@testing-library/react';
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

import VerifyEmailPage from '@/app/verify-email/page';

const mockFetch = jest.fn<(...args: any[]) => any>();

beforeAll(() => {
  (global as any).fetch = mockFetch;
});

async function renderPage() {
  await act(async () => {
    render(<VerifyEmailPage />);
  });
}

describe('Verify Email Page', () => {
  beforeEach(() => {
    sessionStorage.clear();
    mockFetch.mockClear();
    mockParams = new URLSearchParams('token=verify-token-abc');
  });

  it('verifies the email with the emailed token and shows success', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ status: 'ok', message: 'Email verified' }),
    });
    await renderPage();
    expect(await screen.findByText('Email verified')).toBeInTheDocument();
    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.magneetar.me/api/auth/verify-email',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ token: 'verify-token-abc' }),
      })
    );
  });

  it('shows the broken-link state when the token is missing', async () => {
    mockParams = new URLSearchParams('');
    await renderPage();
    expect(await screen.findByText('Broken verification link')).toBeInTheDocument();
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('shows the expired state on a 401 response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: 'Invalid or expired verification token' }),
    });
    await renderPage();
    expect(await screen.findByText('Link expired')).toBeInTheDocument();
  });

  it('surfaces a server error message on a 5xx response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({ detail: 'Internal server error' }),
    });
    await renderPage();
    expect(await screen.findByText('Could not verify')).toBeInTheDocument();
    expect(screen.getByText('Internal server error')).toBeInTheDocument();
  });
});
