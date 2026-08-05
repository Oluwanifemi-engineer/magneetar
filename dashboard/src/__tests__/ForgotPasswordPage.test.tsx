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

import ForgotPasswordPage from '@/app/forgot-password/page';

const mockFetch = jest.fn<(...args: any[]) => any>();

beforeAll(() => {
  (global as any).fetch = mockFetch;
});

async function renderPage() {
  await act(async () => {
    render(<ForgotPasswordPage />);
  });
}

describe('Forgot Password Page', () => {
  beforeEach(() => {
    sessionStorage.clear();
    mockFetch.mockClear();
  });

  it('renders the request form', async () => {
    await renderPage();
    expect(screen.getByText('Reset your password')).toBeInTheDocument();
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
  });

  it('requests a reset link and shows the check-your-inbox state', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: 'ok', message: 'If that email is registered, a reset link is on its way.' }),
    });
    await renderPage();
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'user@example.com' } });
    await act(async () => {
      fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    });

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.magneetar.me/api/auth/forgot-password',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ email: 'user@example.com' }),
      })
    );
    // The success state must NOT claim an account exists (no enumeration).
    expect(await screen.findByText('Check your inbox')).toBeInTheDocument();
    expect(screen.getByText(/is on its way/i)).toBeInTheDocument();
  });

  it('validates the email field', async () => {
    await renderPage();
    await act(async () => {
      fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    });
    expect(screen.getByRole('alert')).toHaveTextContent('Please enter your email address.');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('shows a readable error on failure', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'Server error' }),
    });
    await renderPage();
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'user@example.com' } });
    await act(async () => {
      fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    });
    expect(await screen.findByRole('alert')).toHaveTextContent('Server error');
  });
});
