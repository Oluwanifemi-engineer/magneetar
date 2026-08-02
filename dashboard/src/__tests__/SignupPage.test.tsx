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

import SignupPage from '@/app/signup/page';

const mockFetch = jest.fn<(...args: any[]) => any>();

beforeAll(() => {
  (global as any).fetch = mockFetch;
});

async function renderPage() {
  await act(async () => {
    render(<SignupPage />);
  });
}

function fillValidForm() {
  fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new@example.com' } });
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'StrongPass1' } });
  fireEvent.change(screen.getByLabelText('Confirm Password'), { target: { value: 'StrongPass1' } });
}

describe('Signup Page', () => {
  beforeEach(() => {
    sessionStorage.clear();
    mockFetch.mockClear();
    mockSetCredentials.mockClear();
    mockSetConnected.mockClear();
  });

  it('renders the signup page with brand panel and perks', async () => {
    await renderPage();
    expect(screen.getByText('Create your account')).toBeInTheDocument();
    expect(screen.getByText('One account.')).toBeInTheDocument();
    expect(
      screen.getByText(/Track unlimited smart devices under one email/)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Forensic-grade PDF reports for recovery/)
    ).toBeInTheDocument();
    expect(await screen.findByDisplayValue('https://api.magneetar.me')).toBeInTheDocument();
  });

  it('rejects a password shorter than 8 characters', async () => {
    await renderPage();
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'a@b.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'short' } });
    fireEvent.change(screen.getByLabelText('Confirm Password'), { target: { value: 'short' } });

    await act(async () => {
      fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    });
    expect(screen.getByRole('alert')).toHaveTextContent(
      'Password must be at least 8 characters.'
    );
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('rejects mismatched passwords', async () => {
    await renderPage();
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'a@b.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'StrongPass1' } });
    fireEvent.change(screen.getByLabelText('Confirm Password'), { target: { value: 'Different1' } });

    await act(async () => {
      fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    });
    expect(screen.getByRole('alert')).toHaveTextContent('Passwords do not match.');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('rejects submission without an email', async () => {
    await renderPage();
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'StrongPass1' } });
    fireEvent.change(screen.getByLabelText('Confirm Password'), { target: { value: 'StrongPass1' } });

    await act(async () => {
      fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    });
    expect(screen.getByRole('alert')).toHaveTextContent('Please enter your email and password.');
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('registers a new account, stores the session, and redirects', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ token: 'user-jwt', refresh_token: 'rt' }),
    });
    await renderPage();
    fillValidForm();

    await act(async () => {
      fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    });

    expect(mockFetch).toHaveBeenCalledWith(
      'https://api.magneetar.me/api/auth/register',
      expect.objectContaining({
        method: 'POST',
        // JSON.stringify omits the undefined display_name — assert the concrete wire format.
        body: '{"email":"new@example.com","password":"StrongPass1"}',
      })
    );
    expect(sessionStorage.getItem('mt_auth_mode')).toBe('user');
    expect(sessionStorage.getItem('mt_api_key')).toBe('user-jwt');
    expect(mockSetCredentials).toHaveBeenCalledWith('https://api.magneetar.me', 'user-jwt');
    expect(mockSetConnected).toHaveBeenCalledWith(true);
  });

  it('shows a readable error when registration fails', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'Email already registered' }),
    });
    await renderPage();
    fillValidForm();

    await act(async () => {
      fireEvent.submit(document.querySelector('form') as HTMLFormElement);
    });

    expect(await screen.findByRole('alert')).toHaveTextContent('Email already registered');
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
