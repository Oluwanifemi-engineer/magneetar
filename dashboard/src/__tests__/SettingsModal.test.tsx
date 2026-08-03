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
    Crown: stub('Crown'),
    ArrowUpRight: stub('ArrowUpRight'),
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
    });
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
});
