/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import '@testing-library/react';
import '@testing-library/jest-dom/jest-globals';

// ─── Mutable mock state ───────────────────────────────────────────────────
let mockDevices: any[] = [];
let mockSelectedDeviceId: string | null = null;
let mockLatestLocation: any = null;

jest.mock('@/store/useStore', () => ({
  useStore: jest.fn((selector: any) => {
    const state = {
      devices: mockDevices,
      selectedDeviceId: mockSelectedDeviceId,
      latestLocation: mockLatestLocation,
    };
    return selector ? selector(state) : state;
  }),
}));

jest.mock('lucide-react', () => ({
  ShieldCheck: () => null,
  Users: () => null,
  Radar: () => null,
  MapPin: () => null,
  Send: () => null,
  Bell: () => null,
  X: () => null,
  Heart: () => null,
}));

jest.mock('@/lib/utils', () => ({
  cn: (...args: any[]) => args.filter(Boolean).join(' '),
}));

jest.mock('@/components/ui/Toast', () => ({
  useToast: () => ({ toast: jest.fn() }),
  ToastProvider: ({ children }: any) => children,
}));

jest.mock('@/components/ui/Skeleton', () => ({
  GuardianSkeleton: () => null,
}));

// ─── Mock API ─────────────────────────────────────────────────────────────
let mockProfile: any = { opted_in: false, radius_km: 20, handle: null };
let mockRequests: any[] = [];
let mockNearby: any[] = [];
let mockError: string | null = null;
let launchCalls = 0;
let closeCalls = 0;
let sightingCalls = 0;

jest.mock('@/lib/api', () => ({
  getAPI: () => ({
    getGuardianProfile: jest.fn<(...args: any[]) => any>().mockResolvedValue(mockProfile),
    getRecoveryRequests: jest.fn<(...args: any[]) => any>().mockResolvedValue({ requests: mockRequests }),
    launchRecovery: jest.fn<(...args: any[]) => any>().mockImplementation(async (deviceId: string) => {
      launchCalls++;
      return {
        id: 'rec-test',
        device_id: deviceId,
        status: 'active',
        description: null,
        sighting_count: 0,
        sightings: [],
        created_at: new Date().toISOString(),
        closed_at: null,
        closed_reason: null,
      };
    }),
    closeRecovery: jest.fn<(...args: any[]) => any>().mockImplementation(async (requestId: string) => {
      closeCalls++;
      return { status: 'ok', message: 'Recovery request closed — device marked recovered', request_id: requestId };
    }),
    getNearbyRecovery: jest.fn<(...args: any[]) => any>().mockResolvedValue({ requests: mockNearby }),
    reportSighting: jest.fn<(...args: any[]) => any>().mockImplementation(async () => {
      sightingCalls++;
      return { status: 'ok', sighting_id: 1, guardian_handle: 'EagleEye' };
    }),
    setGuardianOptIn: jest.fn<(...args: any[]) => any>().mockImplementation(async (data: any) => ({
      user_id: 'usr-test',
      opted_in: data.opted_in,
      radius_km: data.radius_km,
      handle: data.handle || null,
      created_at: null,
      updated_at: null,
    })),
  }),
}));

import { GuardianPanel } from '@/components/panels/GuardianPanel';

async function renderPanel() {
  await act(async () => {
    render(<GuardianPanel />);
  });
}

describe('GuardianPanel Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    launchCalls = 0;
    closeCalls = 0;
    sightingCalls = 0;
    mockDevices = [];
    mockSelectedDeviceId = null;
    mockLatestLocation = null;
    mockProfile = { opted_in: false, radius_km: 20, handle: null };
    mockRequests = [];
    mockNearby = [];
    mockError = null;
  });

  it('renders the Guardian Network header', async () => {
    await renderPanel();
    expect(screen.getByText('Guardian Network')).toBeInTheDocument();
    expect(screen.getByText('Guardian Mode')).toBeInTheDocument();
  });

  it('shows launch button for a stolen device with no active request', async () => {
    mockDevices = [{ id: 'device-001', is_stolen: true, sentinel_score: 90 }];
    mockSelectedDeviceId = 'device-001';

    await renderPanel();
    const launchBtn = screen.getByText('Launch Community Recovery');
    expect(launchBtn).toBeInTheDocument();

    fireEvent.click(launchBtn);
    await waitFor(() => expect(launchCalls).toBe(1));
  });

  it('shows active request with sightings for the owner', async () => {
    mockDevices = [{ id: 'device-001', is_stolen: true, sentinel_score: 90 }];
    mockSelectedDeviceId = 'device-001';
    mockRequests = [
      {
        id: 'rec-1',
        device_id: 'device-001',
        status: 'active',
        description: 'Grey Pixel',
        sighting_count: 2,
        sightings: [
          { id: 1, guardian_handle: 'EagleEye', lat: 9.083, lng: 8.676, note: 'Saw it at the bus stop', created_at: '2026-08-01T10:00:00Z' },
          { id: 2, guardian_handle: 'NightWatch', lat: 9.09, lng: 8.68, note: null, created_at: '2026-08-01T11:00:00Z' },
        ],
        created_at: '2026-08-01T09:00:00Z',
        closed_at: null,
        closed_reason: null,
      },
    ];

    await renderPanel();
    expect(screen.getByText(/ACTIVE — 2 sightings/)).toBeInTheDocument();
    expect(screen.getByText('EagleEye')).toBeInTheDocument();
    expect(screen.getByText('Saw it at the bus stop')).toBeInTheDocument();
    expect(screen.getByText('Mark Recovered & Close')).toBeInTheDocument();
  });

  it('closes the active request and marks recovered', async () => {
    mockDevices = [{ id: 'device-001', is_stolen: true, sentinel_score: 90 }];
    mockSelectedDeviceId = 'device-001';
    mockRequests = [
      {
        id: 'rec-1',
        device_id: 'device-001',
        status: 'active',
        description: null,
        sighting_count: 0,
        sightings: [],
        created_at: '2026-08-01T09:00:00Z',
        closed_at: null,
        closed_reason: null,
      },
    ];

    await renderPanel();
    fireEvent.click(screen.getByText('Mark Recovered & Close'));
    await waitFor(() => expect(closeCalls).toBe(1));
    expect(screen.getByText(/device marked recovered/i)).toBeInTheDocument();
  });

  it('shows no-device state when nothing is selected', async () => {
    await renderPanel();
    expect(screen.getByText('Select a device')).toBeInTheDocument();
  });

  it('toggles guardian mode on', async () => {
    await renderPanel();
    fireEvent.click(screen.getByLabelText('Turn guardian mode on'));
    await waitFor(() => expect(screen.getByText('You are now a Guardian.')).toBeInTheDocument());
  });

  it('shows guardian options when opted in', async () => {
    mockProfile = { opted_in: true, radius_km: 30, handle: 'EagleEye' };
    await renderPanel();
    expect(screen.getByText('You are helping recover devices.')).toBeInTheDocument();
    expect(screen.getByText('Scan Nearby Requests')).toBeInTheDocument();
    // Handle prefilled from profile
    expect(screen.getByDisplayValue('EagleEye')).toBeInTheDocument();
  });

  it('scans nearby and reports a sighting', async () => {
    mockProfile = { opted_in: true, radius_km: 30, handle: 'EagleEye' };
    mockNearby = [
      {
        id: 'rec-9',
        device_model: 'Pixel 8',
        description: 'Lost near the mall',
        distance_km: 1.2,
        blurred_lat: 9.05,
        blurred_lng: 8.65,
        sighting_count: 0,
        created_at: '2026-08-01T09:00:00Z',
      },
    ];

    await renderPanel();
    fireEvent.click(screen.getByText('Scan Nearby Requests'));
    await waitFor(() => expect(screen.getByText('Pixel 8')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Report Sighting'));
    await waitFor(() => expect(screen.getByPlaceholderText('Latitude')).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText('Latitude'), { target: { value: '9.083' } });
    fireEvent.change(screen.getByPlaceholderText('Longitude'), { target: { value: '8.676' } });
    fireEvent.change(screen.getByPlaceholderText('Where did you see it? (optional)'), {
      target: { value: 'Bus stop' },
    });

    fireEvent.click(screen.getByText('Submit Sighting'));
    await waitFor(() => expect(sightingCalls).toBe(1));
    expect(screen.getByText(/Sighting reported as "EagleEye"/)).toBeInTheDocument();
  });
});
