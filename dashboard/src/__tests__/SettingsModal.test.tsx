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
  }),
}));

jest.mock('lucide-react', () => {
  const stub = (name: string) => {
    const Comp = (props: any) => <span data-testid={`icon-${name}`} {...props} />;
    Comp.displayName = name;
    return Comp;
  };
  return { X: stub('X'), Trash2: stub('Trash2'), ShieldAlert: stub('ShieldAlert') };
});

import { SettingsModal } from '@/components/layout/SettingsModal';

describe('SettingsModal — portal + danger zone', () => {
  const onClose = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    mockServerUrl = 'https://api.magneetar.me';
    mockDeleteAccount.mockResolvedValue({ status: 'ok' });
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

  it('closes when the backdrop is clicked', () => {
    render(<SettingsModal onClose={onClose} />);
    const backdrop = screen.getByRole('dialog').querySelector('.absolute.inset-0');
    fireEvent.click(backdrop!);
    expect(onClose).toHaveBeenCalled();
  });
});
