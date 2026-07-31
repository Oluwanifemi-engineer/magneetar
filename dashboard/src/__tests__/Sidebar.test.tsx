/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom/jest-globals';

// Mock the store
const mockSelectDevice = jest.fn();
const mockSetSidebarOpen = jest.fn();
let mockDevices: any[] = [];
let mockSidebarOpen = true;
let mockSelectedDeviceId: string | null = null;
let mockStats: any = null;
let mockIsConnected = true;

jest.mock('@/store/useStore', () => ({    useStore: jest.fn((selector: any) => {
    const state = {
      devices: mockDevices,
      selectedDeviceId: mockSelectedDeviceId,
      sidebarOpen: mockSidebarOpen,
      isConnected: mockIsConnected,
      selectDevice: mockSelectDevice,
      setSidebarOpen: mockSetSidebarOpen,
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
}));

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
}));

import { Sidebar } from '@/components/layout/Sidebar';

describe('Sidebar Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockDevices = [];
    mockSidebarOpen = true;
    mockSelectedDeviceId = null;
    mockStats = null;
    mockIsConnected = true;
  });

  it('renders the brand name when open', () => {
    render(<Sidebar />);
    expect(screen.getByText('MAGNEETAR')).toBeInTheDocument();
    expect(screen.getByText('COMMAND CENTER')).toBeInTheDocument();
  });

  it('shows devices section header when open', () => {
    render(<Sidebar />);
    expect(screen.getByText('Devices')).toBeInTheDocument();
  });

  it('shows empty state when no devices', () => {
    render(<Sidebar />);
    expect(screen.getByText('No devices registered.')).toBeInTheDocument();
    expect(screen.getByText('Connect to server first.')).toBeInTheDocument();
  });

  it('shows device list when devices exist', () => {
    mockDevices = [
      {
        id: 'device-001',
        alias: 'My Phone',
        last_seen: 'recent',
        model: 'Pixel 8',
      },
    ];
    mockSelectedDeviceId = 'device-001';

    render(<Sidebar />);
    expect(screen.getByText('My Phone')).toBeInTheDocument();
    expect(screen.getByText('device-001')).toBeInTheDocument();
  });
});

describe('Sidebar Collapsed State', () => {
  beforeEach(() => {
    mockSidebarOpen = false;
  });

  it('does not show brand when collapsed', () => {
    render(<Sidebar />);
    expect(screen.queryByText('MAGNEETAR')).not.toBeInTheDocument();
  });
});
