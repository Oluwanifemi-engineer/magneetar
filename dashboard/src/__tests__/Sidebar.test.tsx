/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import { render, screen, act, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/jest-globals';

// Mock the store
const mockSelectDevice = jest.fn();
const mockSetSidebarOpen = jest.fn();
const mockSetDevices = jest.fn();
let mockDevices: any[] = [];
let mockSidebarOpen = true;
let mockSelectedDeviceId: string | null = null;
let mockIsConnected = true;

jest.mock('@/store/useStore', () => ({    useStore: jest.fn((selector: any) => {
    const state = {
      devices: mockDevices,
      selectedDeviceId: mockSelectedDeviceId,
      sidebarOpen: mockSidebarOpen,
      isConnected: mockIsConnected,
      selectDevice: mockSelectDevice,
      setSidebarOpen: mockSetSidebarOpen,
      setDevices: mockSetDevices,
    };
    return selector ? selector(state) : state;
  }),
}));

// Mock lucide-react icons as proper React components
jest.mock('lucide-react', () => ({
  ChevronLeft: () => null,
  ChevronRight: () => null,
  Smartphone: () => null,
  BarChart3: () => null,
  FileText: () => null,
  BookOpen: () => null,
  Copy: () => null,
  Battery: () => null,
  MapPin: () => null,
  Link2: () => null,
  Trash2: () => null,
  X: () => null,
  AlertTriangle: () => null,
}));

// Mutable mock for the archived purge flow
const mockDeleteArchivedDevices = jest.fn<(...args: any[]) => any>();
const mockGetDevices = jest.fn<(...args: any[]) => any>();

jest.mock('@/lib/api', () => ({
  getAPI: () => ({
    getStats: jest.fn<(...args: any[]) => any>().mockResolvedValue({
      total_devices: 3,
      active_devices: 1,
      stolen_devices: 0,
      total_locations: 150,
      total_media: 12,
      alerts_today: 2,
    }),
    deleteArchivedDevices: mockDeleteArchivedDevices,
    getDevices: mockGetDevices,
  }),
}));

jest.mock('@/components/ui/StatusIndicator', () => ({
  StatusIndicator: ({ isOnline }: { isOnline: boolean }) => null,
}));

jest.mock('@/lib/utils', () => ({
  cn: (...args: any[]) => args.filter(Boolean).join(' '),
  relativeTime: (ts: string) => ts ? '2 min ago' : 'never',
  isOnline: (ts: string) => ts === 'recent',
  getSignalLevel: () => 'strong',
  deviceDisplayName: (device: any) => device?.alias || device?.model || 'Device',
  stepUpPasswordHint: () => 'the master API key (API-key mode)',
}));

import { Sidebar } from '@/components/layout/Sidebar';

// Sidebar fetches stats in a useEffect — wrap render in act() so the async
// getStats → setStats update is flushed inside act (no React warnings).
async function renderSidebar() {
  await act(async () => {
    render(<Sidebar />);
  });
}

describe('Sidebar Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockDevices = [];
    mockSidebarOpen = true;
    mockSelectedDeviceId = null;
    mockIsConnected = true;
    mockDeleteArchivedDevices.mockResolvedValue({ status: 'ok', deleted: [], count: 0 });
    mockGetDevices.mockResolvedValue({ devices: mockDevices });
  });

  it('renders the brand name when open', async () => {
    await renderSidebar();
    expect(screen.getByText('MAGNEETAR')).toBeInTheDocument();
    expect(screen.getByText('COMMAND CENTER')).toBeInTheDocument();
  });

  it('shows devices section header when open', async () => {
    await renderSidebar();
    expect(screen.getByText('Devices')).toBeInTheDocument();
  });

  it('shows empty state when no devices', async () => {
    await renderSidebar();
    expect(screen.getByText('No devices registered.')).toBeInTheDocument();
    expect(screen.getByText('Connect to server first.')).toBeInTheDocument();
  });

  it('shows device list when devices exist', async () => {
    mockDevices = [
      {
        id: 'device-001',
        alias: 'My Phone',
        last_seen: 'recent',
        model: 'Pixel 8',
      },
    ];
    mockSelectedDeviceId = 'device-001';

    await renderSidebar();
    expect(screen.getByText('My Phone')).toBeInTheDocument();
    expect(screen.getByText('device-001')).toBeInTheDocument();
  });

  it('shows a Delete archived button when archived devices exist', async () => {
    mockDevices = [
      { id: 'stale-1', model: 'Old Phone', last_seen: 'long-ago', archived_at: '2026-07-01T00:00:00Z' },
      { id: 'stale-2', model: 'Older Phone', last_seen: 'longer-ago', archived_at: '2026-06-01T00:00:00Z' },
      { id: 'live-1', model: 'Pixel 8', last_seen: 'recent', archived_at: null },
    ];
    await renderSidebar();
    expect(screen.getByRole('button', { name: /delete all archived/i })).toBeInTheDocument();
    // The devices header chip and the purge button both mention the count;
    // assert at least one "2 archived" label is visible.
    expect(screen.getAllByText(/2 archived/).length).toBeGreaterThan(0);
  });

  it('hides the Delete archived button when no devices are archived', async () => {
    mockDevices = [{ id: 'live-1', model: 'Pixel 8', last_seen: 'recent', archived_at: null }];
    await renderSidebar();
    expect(screen.queryByRole('button', { name: /delete all archived/i })).not.toBeInTheDocument();
  });

  it('bulk purge requires the step-up password — empty input never calls the API', async () => {
    mockDevices = [
      { id: 'stale-1', model: 'Old Phone', last_seen: 'long-ago', archived_at: '2026-07-01T00:00:00Z' },
    ];
    await renderSidebar();
    fireEvent.click(screen.getByRole('button', { name: /delete all archived/i }));
    fireEvent.click(screen.getByText('Yes, Delete'));
    await waitFor(() => {
      expect(screen.getByText('Enter your password to confirm.')).toBeInTheDocument();
    });
    expect(mockDeleteArchivedDevices).not.toHaveBeenCalled();
  });

  it('bulk purge calls the API with the password and refreshes the device list', async () => {
    mockDevices = [
      { id: 'stale-1', model: 'Old Phone', last_seen: 'long-ago', archived_at: '2026-07-01T00:00:00Z' },
    ];
    mockDeleteArchivedDevices.mockResolvedValue({ status: 'ok', deleted: ['stale-1'], count: 1 });
    mockGetDevices.mockResolvedValue({ devices: [] });
    await renderSidebar();
    fireEvent.click(screen.getByRole('button', { name: /delete all archived/i }));
    fireEvent.change(screen.getByLabelText('Confirm deletion password'), { target: { value: 'master-key' } });
    fireEvent.click(screen.getByText('Yes, Delete'));
    await waitFor(() => {
      expect(mockDeleteArchivedDevices).toHaveBeenCalledWith('master-key');
      expect(mockGetDevices).toHaveBeenCalled();
      expect(mockSetDevices).toHaveBeenCalled();
    });
  });

  it('shows the API error and keeps the modal open on wrong password', async () => {
    mockDevices = [
      { id: 'stale-1', model: 'Old Phone', last_seen: 'long-ago', archived_at: '2026-07-01T00:00:00Z' },
    ];
    mockDeleteArchivedDevices.mockRejectedValueOnce(new Error('Invalid password'));
    await renderSidebar();
    fireEvent.click(screen.getByRole('button', { name: /delete all archived/i }));
    fireEvent.change(screen.getByLabelText('Confirm deletion password'), { target: { value: 'wrong' } });
    fireEvent.click(screen.getByText('Yes, Delete'));
    await waitFor(() => {
      expect(screen.getByText('Invalid password')).toBeInTheDocument();
    });
    expect(screen.getByLabelText('Confirm deletion password')).toBeInTheDocument();
  });
});

describe('Sidebar Collapsed State', () => {
  beforeEach(() => {
    mockSidebarOpen = false;
  });

  it('does not show brand when collapsed', async () => {
    await renderSidebar();
    expect(screen.queryByText('MAGNEETAR')).not.toBeInTheDocument();
  });
});
