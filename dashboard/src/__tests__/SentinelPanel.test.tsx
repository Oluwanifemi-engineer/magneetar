/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import { render, screen } from '@testing-library/react';
import '@testing-library/react';
import '@testing-library/jest-dom/jest-globals';

// ─── Mutable mock state ───────────────────────────────────────────────────
let mockDevices: any[] = [];
let mockSelectedDeviceId: string | null = null;
let mockLatestLocation: any = null;

jest.mock('@/store/useStore', () => ({    useStore: jest.fn((selector: any) => {
    const state = {
      devices: mockDevices,
      selectedDeviceId: mockSelectedDeviceId,
      latestLocation: mockLatestLocation,
    };
    return selector ? selector(state) : state;
  }),
}));

jest.mock('lucide-react', () => ({
  Shield: () => null,
  AlertTriangle: () => null,
  Battery: () => null,
  Wifi: () => null,
  MapPin: () => null,
  Clock: () => null,
  Smartphone: () => null,
}));

jest.mock('@/lib/utils', () => ({
  cn: (...args: any[]) => args.filter(Boolean).join(' '),
  relativeTime: (ts: string | null) => {
    if (!ts) return 'Never';
    return '2m ago';
  },
}));

import { SentinelPanel } from '@/components/panels/SentinelPanel';

describe('SentinelPanel Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockDevices = [];
    mockSelectedDeviceId = null;
    mockLatestLocation = null;
  });

  it('shows empty state when no device is selected', () => {
    render(<SentinelPanel />);
    expect(screen.getByText('No device selected')).toBeInTheDocument();
  });

  it('renders threat assessment section for selected device', () => {
    mockDevices = [
      {
        id: 'device-001',
        alias: 'My Phone',
        model: 'Pixel 8',
        last_seen: '2024-01-01T12:00:00Z',
        is_stolen: false,
        sentinel_score: 12,
      },
    ];
    mockSelectedDeviceId = 'device-001';
    mockLatestLocation = {
      battery_percent: 85,
      accuracy: 10,
      speed: 0,
    };

    render(<SentinelPanel />);
    expect(screen.getByText('Threat Assessment')).toBeInTheDocument();
    expect(screen.getByText('SECURE')).toBeInTheDocument();
  });

  it('displays sentinel score with correct value', () => {
    mockDevices = [
      {
        id: 'device-001',
        sentinel_score: 75,
        is_stolen: true,
        last_seen: '2024-01-01T12:00:00Z',
      },
    ];
    mockSelectedDeviceId = 'device-001';

    render(<SentinelPanel />);
    expect(screen.getByText('75')).toBeInTheDocument();
    expect(screen.getByText('STOLEN')).toBeInTheDocument();
  });

  it('shows stolen alert banner when device is stolen', () => {
    mockDevices = [
      {
        id: 'device-001',
        sentinel_score: 85,
        is_stolen: true,
        last_seen: '2024-01-01T12:00:00Z',
      },
    ];
    mockSelectedDeviceId = 'device-001';

    render(<SentinelPanel />);
    expect(screen.getByText(/DEVICE MARKED AS STOLEN/i)).toBeInTheDocument();
    expect(screen.getByText(/All tracking data is being logged for evidence\./i)).toBeInTheDocument();
  });

  it('renders battery info from latest location', () => {
    mockDevices = [
      {
        id: 'device-001',
        sentinel_score: 10,
        is_stolen: false,
        last_seen: '2024-01-01T12:00:00Z',
      },
    ];
    mockSelectedDeviceId = 'device-001';
    mockLatestLocation = {
      battery_percent: 85,
      accuracy: 10,
      speed: 5.5,  // non-zero so component renders km/h
    };

    render(<SentinelPanel />);
    // Battery "85%
    expect(screen.getByText('85%', { exact: false })).toBeInTheDocument();
    // Accuracy "±10m"
    expect(screen.getByText('±10m', { exact: false })).toBeInTheDocument();
    // 5.5 m/s * 3.6 = 19.8 km/h
    expect(screen.getByText('19.8 km/h', { exact: false })).toBeInTheDocument();
  });

  it('shows dash placeholders when location data is missing', () => {
    mockDevices = [
      {
        id: 'device-001',
        sentinel_score: 10,
        is_stolen: false,
        last_seen: null,  // null so relativeTime returns 'Never'
      },
    ];
    mockSelectedDeviceId = 'device-001';
    mockLatestLocation = null;

    render(<SentinelPanel />);
    // '—' appears for missing battery, speed, accuracy
    const dashes = screen.getAllByText('—');
    expect(dashes.length).toBeGreaterThanOrEqual(1);
    // last_seen is null so relativeTime returns 'Never'
    expect(screen.getByText('Never')).toBeInTheDocument();
  });

  it('shows SECURE status for low sentinel scores', () => {
    mockDevices = [
      {
        id: 'device-001',
        sentinel_score: 10,
        is_stolen: false,
        last_seen: '2024-01-01T12:00:00Z',
      },
    ];
    mockSelectedDeviceId = 'device-001';

    render(<SentinelPanel />);
    expect(screen.getByText('SECURE')).toBeInTheDocument();
  });

  it('shows STOLEN status for stolen devices', () => {
    mockDevices = [
      {
        id: 'device-001',
        sentinel_score: 90,
        is_stolen: true,
        last_seen: '2024-01-01T12:00:00Z',
      },
    ];
    mockSelectedDeviceId = 'device-001';

    render(<SentinelPanel />);
    expect(screen.getByText('STOLEN')).toBeInTheDocument();
  });
});
