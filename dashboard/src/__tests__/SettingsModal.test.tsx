/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/jest-globals';

// ─── Mutable mock state ───────────────────────────────────────────────────
let mockServerUrl = 'https://api.magneetar.me';
const mockLogout = jest.fn();
const mockDeleteAccount = jest.fn<(...args: any[]) => any>();
const mockFetchMe = jest.fn<(...args: any[]) => any>();
const mockSetupTwoFactor = jest.fn<(...args: any[]) => any>();
const mockEnableTwoFactor = jest.fn<(...args: any[]) => any>();
const mockDisableTwoFactor = jest.fn<(...args: any[]) => any>();
const mockResendVerification = jest.fn<(...args: any[]) => any>();

jest.mock('@/store/useStore', () => ({
  useStore: jest.fn((selector: any) => {
    const state = {
      serverUrl: mockServerUrl,
      logout: mockLogout,
    };
    return selector ? selector(state) : state;
  }),
}));

jest.mock('@/lib/api', () => ({
  getAPI: () => ({
    deleteAccount: mockDeleteAccount,
    fetchMe: mockFetchMe,
    setupTwoFactor: mockSetupTwoFactor,
    enableTwoFactor: mockEnableTwoFactor,
    disableTwoFactor: mockDisableTwoFactor,
    resendVerificationEmail: mockResendVerification,
  }),
}));

jest.mock('lucide-react', () => {
  const stub = (name: string) => {
    const Comp = (props: any) => <span data-testid={`icon-${name}`} {...props} />;
    Comp.displayName = name;
    return Comp;
  };
  return {
    X: stub('X'),
    Trash2: stub('Trash2'),
    ShieldAlert: stub('ShieldAlert'),
    ShieldCheck: stub('ShieldCheck'),
    Crown: stub('Crown'),
    ArrowUpRight: stub('ArrowUpRight'),
    Smartphone: stub('Smartphone'),
    Mail: stub('Mail'),
    RefreshCw: stub('RefreshCw'),
  };
});

import { SettingsModal } from '@/components/layout/SettingsModal';

describe('SettingsModal — portal + danger zone', () => {
  const onClose = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    mockServerUrl = 'https://api.magneetar.me';
    mockDeleteAccount.mockResolvedValue({ status: 'ok' });
    mockFetchMe.mockResolvedValue({
      id: 'usr-test',
      email: 'test@example.com',
      display_name: 'Test User',
      tier: 'free',
      is_active: true,
      created_at: null,
      device_count: 1,
      max_devices: 1,
      email_verified: true,
      totp_enabled: false,
    });
    mockSetupTwoFactor.mockResolvedValue({
      secret: 'ABCDEFGHIJKLMNOP',
      otpauth_uri: 'otpauth://totp/Magneetar:test%40example.com?secret=ABCDEFGHIJKLMNOP',
      qr_svg_data_uri: 'data:image/svg+xml;base64,PHN2Zz4=',
    });
    mockEnableTwoFactor.mockResolvedValue({ status: 'ok', totp_enabled: true });
    mockDisableTwoFactor.mockResolvedValue({ status: 'ok', totp_enabled: false });
    mockResendVerification.mockResolvedValue({ status: 'ok', message: 'Verification email sent', delivered: true });
    sessionStorage.clear();
  });

  it('renders the settings panel through a portal into document.body', () => {
    const { container } = render(<SettingsModal onClose={onClose} />);
    // The portal target is document.body — the modal content must NOT be a
    // child of the component's own container (the regression: it rendered
    // inside the clipped <header> and was invisible).
    expect(container.firstChild).toBeNull();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('SETTINGS')).toBeInTheDocument();
    expect(screen.getByText('Account & security')).toBeInTheDocument();
  });

  it('shows the configured server URL', () => {
    render(<SettingsModal onClose={onClose} />);
    expect(screen.getByText('https://api.magneetar.me')).toBeInTheDocument();
  });

  it('requires a two-step confirm before account deletion', () => {
    render(<SettingsModal onClose={onClose} />);
    fireEvent.click(screen.getByText('Delete Account Permanently'));

    // Deletion must not fire on the first click — an explicit confirmation is
    // required, then the destructive call happens.
    expect(mockDeleteAccount).not.toHaveBeenCalled();
    expect(screen.getByText('Yes, Delete Everything')).toBeInTheDocument();
  });

  it('deletes the account only after the explicit confirmation', async () => {
    render(<SettingsModal onClose={onClose} />);
    fireEvent.click(screen.getByText('Delete Account Permanently'));
    fireEvent.click(screen.getByText('Yes, Delete Everything'));

    await waitFor(() => expect(mockDeleteAccount).toHaveBeenCalled());
    await waitFor(() => expect(mockLogout).toHaveBeenCalled());
  });

  it('shows admin access in API-key mode without fetching the profile', () => {
    render(<SettingsModal onClose={onClose} />);
    expect(screen.getByText('ADMIN · UNLIMITED')).toBeInTheDocument();
    expect(mockFetchMe).not.toHaveBeenCalled();
  });

  it('shows plan usage from the profile in user mode', async () => {
    sessionStorage.setItem('mt_auth_mode', 'user');
    render(<SettingsModal onClose={onClose} />);

    expect(await screen.findByText('FREE')).toBeInTheDocument();
    expect(mockFetchMe).toHaveBeenCalledTimes(1);
    // 1 of 1 device → at the free limit → upgrade prompt + pricing link.
    expect(screen.getByText('1 / 1')).toBeInTheDocument();
    expect(screen.getByText(/Device limit reached/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /see plans & pricing/i })).toHaveAttribute('href', '/#pricing');
  });

  it('closes when the backdrop is clicked', () => {
    render(<SettingsModal onClose={onClose} />);
    const backdrop = screen.getByRole('dialog').querySelector('.absolute.inset-0');
    fireEvent.click(backdrop!);
    expect(onClose).toHaveBeenCalled();
  });

  it('shows an unverified-email banner with a resend action (user mode)', async () => {
    sessionStorage.setItem('mt_auth_mode', 'user');
    mockFetchMe.mockResolvedValueOnce({
      id: 'usr-test',
      email: 'test@example.com',
      display_name: 'Test User',
      tier: 'free',
      is_active: true,
      created_at: null,
      device_count: 1,
      max_devices: 1,
      email_verified: false,
      totp_enabled: false,
    });
    render(<SettingsModal onClose={onClose} />);

    expect(await screen.findByText('RESEND EMAIL')).toBeInTheDocument();
    fireEvent.click(screen.getByText('RESEND EMAIL'));
    await waitFor(() => expect(mockResendVerification).toHaveBeenCalled());
    expect(await screen.findByText('Verification email sent')).toBeInTheDocument();
  });

  it('enables 2FA end-to-end: setup shows the QR + secret, confirm flips the state', async () => {
    sessionStorage.setItem('mt_auth_mode', 'user');
    render(<SettingsModal onClose={onClose} />);

    fireEvent.click(await screen.findByText('ENABLE'));
    await waitFor(() => expect(mockSetupTwoFactor).toHaveBeenCalled());
    expect(await screen.findByText('ABCDEFGHIJKLMNOP')).toBeInTheDocument();
    expect(screen.getByAltText('TOTP setup QR code')).toHaveAttribute('src', 'data:image/svg+xml;base64,PHN2Zz4=');

    fireEvent.change(screen.getByPlaceholderText('Account password'), { target: { value: 'StrongPass1' } });
    fireEvent.change(screen.getByPlaceholderText('6-digit code'), { target: { value: '123456' } });
    fireEvent.click(screen.getByText('Confirm & Enable'));

    await waitFor(() =>
      expect(mockEnableTwoFactor).toHaveBeenCalledWith('StrongPass1', '123456')
    );
    expect(await screen.findByText('ENABLED')).toBeInTheDocument();
  });

  it('disables 2FA with a step-up password', async () => {
    sessionStorage.setItem('mt_auth_mode', 'user');
    mockFetchMe.mockResolvedValueOnce({
      id: 'usr-test',
      email: 'test@example.com',
      display_name: 'Test User',
      tier: 'free',
      is_active: true,
      created_at: null,
      device_count: 1,
      max_devices: 1,
      email_verified: true,
      totp_enabled: true,
    });
    render(<SettingsModal onClose={onClose} />);

    fireEvent.change(await screen.findByPlaceholderText('Account password'), { target: { value: 'StrongPass1' } });
    fireEvent.click(screen.getByText('Disable'));
    await waitFor(() => expect(mockDisableTwoFactor).toHaveBeenCalledWith('StrongPass1'));
  });
});
