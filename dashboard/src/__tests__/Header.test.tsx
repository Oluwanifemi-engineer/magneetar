/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/jest-globals';

// ─── Mutable mock state ───────────────────────────────────────────────────
let mockIsAuthenticated = true;
let mockIsConnected = true;
let mockServerUrl = 'https://api.magneetar.me';
let mockApiKey = 'test-api-key';
let mockUnreadCount = 0;

const mockSetCredentials = jest.fn();
const mockSetConnected = jest.fn();
const mockLogout = jest.fn();

jest.mock('@/store/useStore', () => ({    useStore: jest.fn((selector: any) => {
    const state = {
      serverUrl: mockServerUrl,
      apiKey: mockApiKey,
      isAuthenticated: mockIsAuthenticated,
      isConnected: mockIsConnected,
      unreadAlertCount: mockUnreadCount,
      setCredentials: mockSetCredentials,
      setConnected: mockSetConnected,
      logout: mockLogout,
    };
    return selector ? selector(state) : state;
  }),
}));

jest.mock('lucide-react', () => ({
  LogOut: () => null,
  Bell: () => null,
  Settings: () => null,
}));

jest.mock('@/lib/api', () => ({
  getAPI: () => ({
    healthCheck: jest.fn<(...args: any[]) => any>().mockResolvedValue({ status: 'ok' }),
  }),
}));

jest.mock('@/lib/utils', () => ({
  cn: (...args: any[]) => args.filter(Boolean).join(' '),
}));

import { Header } from '@/components/layout/Header';

describe('Header Component — Authenticated', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockIsAuthenticated = true;
    mockIsConnected = true;
    mockServerUrl = 'https://api.magneetar.me';
    mockApiKey = 'test-api-key';
    mockUnreadCount = 0;
  });

  it('renders the Magneetar brand name', () => {
    render(<Header />);
    const brandElements = screen.getAllByText('MAGNEETAR');
    expect(brandElements.length).toBeGreaterThanOrEqual(1);
  });

  it('shows connected status when authenticated and connected', () => {
    render(<Header />);
    expect(screen.getByText('CONNECTED')).toBeInTheDocument();
  });

  it('shows DISCONNECTED status when not connected', () => {
    mockIsConnected = false;
    render(<Header />);
    expect(screen.getByText('DISCONNECTED')).toBeInTheDocument();
  });

  it('shows the disconnect button when authenticated', () => {
    render(<Header />);
    const disconnectBtn = screen.getByText('DISCONNECT');
    expect(disconnectBtn).toBeInTheDocument();
  });

  it('calls logout when disconnect is clicked', () => {
    render(<Header />);
    const disconnectBtn = screen.getByText('DISCONNECT');
    fireEvent.click(disconnectBtn);
    expect(mockLogout).toHaveBeenCalledTimes(1);
  });

  it('shows the server URL when authenticated', () => {
    render(<Header />);
    expect(screen.getByText('https://api.magneetar.me')).toBeInTheDocument();
  });

  it('shows alert badge when there are unread alerts', () => {
    mockUnreadCount = 3;
    render(<Header />);
    expect(screen.getByText('3')).toBeInTheDocument();
  });
});

describe('Header Component — Unauthenticated', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockIsAuthenticated = false;
    mockIsConnected = false;
    mockServerUrl = '';
    mockApiKey = '';
  });

  it('shows connection form when not authenticated', () => {
    render(<Header />);

    // Connection form elements should be present
    expect(screen.getByPlaceholderText('https://api.magneetar.me')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('API Key')).toBeInTheDocument();
    expect(screen.getByText('CONNECT')).toBeInTheDocument();
  });

  it('does not show disconnect button when not authenticated', () => {
    render(<Header />);
    expect(screen.queryByText('DISCONNECT')).not.toBeInTheDocument();
  });
});
