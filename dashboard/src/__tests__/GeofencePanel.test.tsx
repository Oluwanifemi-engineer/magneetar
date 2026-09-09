/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/react';
import '@testing-library/jest-dom/jest-globals';

// ─── Mutable mock state ───────────────────────────────────────────────────
let mockSelectedDeviceId: string | null = null;
let mockLatestLocation: any = null;

jest.mock('@/store/useStore', () => ({
  useStore: jest.fn((selector: any) => {
    const state = {
      selectedDeviceId: mockSelectedDeviceId,
      latestLocation: mockLatestLocation,
      // access_role defaults to owner when absent, so an empty list is safe
      devices: mockDevices,
    };
    return selector ? selector(state) : state;
  }),
}));

let mockDevices: any[] = [];

jest.mock('lucide-react', () => {
  const stub = (name: string) => {
    const Comp = (props: any) => <span data-testid={`icon-${name}`} {...props} />;
    Comp.displayName = name;
    return Comp;
  };
  return {
    Fence: stub('Fence'),
    MapPin: stub('MapPin'),
    Plus: stub('Plus'),
    Trash2: stub('Trash2'),
    ShieldAlert: stub('ShieldAlert'),
    Camera: stub('Camera'),
    Volume2: stub('Volume2'),
    Loader: stub('Loader'),
    Loader2: stub('Loader2'),
    Check: stub('Check'),
  };
});

jest.mock('@/lib/utils', () => ({
  cn: (...args: any[]) => args.filter(Boolean).join(' '),
  formatCoordinate: (v: any, type: string) => `${v}${type === 'lat' ? 'N' : 'E'}`,
}));

jest.mock('@/components/ui/Toast', () => ({
  useToast: () => ({ toast: jest.fn() }),
  ToastProvider: ({ children }: any) => children,
}));

// ─── Mock API ─────────────────────────────────────────────────────────────
let mockZones: any[] = [];
let mockCreateCalls: any[] = [];
let mockDeleteCalls: number[] = [];

jest.mock('@/lib/api', () => ({
  getAPI: () => ({
    getGeofences: jest.fn(async () => ({ geofences: mockZones })),
    createGeofence: jest.fn(async (data: any) => {
      mockCreateCalls.push(data);
      return { status: 'ok', geofence_id: 99, auto_action: data.auto_action ?? null };
    }),
    deleteGeofence: jest.fn(async (id: number) => {
      mockDeleteCalls.push(id);
      return { status: 'ok' };
    }),
  }),
}));

import { GeofencePanel } from '@/components/panels/GeofencePanel';

const baseZone = (overrides: any = {}) => ({
  id: 1,
  device_id: 'dev-1',
  name: 'Home',
  center_lat: 6.5244,
  center_lng: 3.3792,
  radius_meters: 300,
  is_safe_zone: true,
  active: 1,
  last_inside: 1,
  auto_action: 'capture',
  created_at: '2026-08-01T10:00:00+00:00',
  ...overrides,
});

describe('GeofencePanel — zone policy UI', () => {
  beforeEach(() => {
    mockSelectedDeviceId = 'dev-1';
    mockLatestLocation = { lat: 6.5244, lng: 3.3792 };
    mockZones = [];
    mockCreateCalls = [];
    mockDeleteCalls = [];
  });

  it('renders existing zones with their auto-action policy', async () => {
    mockZones = [
      baseZone(),
      baseZone({ id: 2, name: 'School', is_safe_zone: false, auto_action: 'siren', radius_meters: 500 }),
      baseZone({ id: 3, name: 'Office', auto_action: null }),
    ];
    render(<GeofencePanel />);

    expect(await screen.findByText('Home')).toBeInTheDocument();
    expect(screen.getByText('School')).toBeInTheDocument();
    // Note: badges render 'Safe'/'Restricted' (uppercase is CSS-only).
    // Two of the three fixtures are safe zones (is_safe_zone defaults true).
    expect(screen.getAllByText('Safe')).toHaveLength(2);
    expect(screen.getByText('Restricted')).toBeInTheDocument();
    expect(screen.getByText('CAPTURE')).toBeInTheDocument();
    expect(screen.getByText('SIREN')).toBeInTheDocument();
    expect(screen.getByText('ALERT')).toBeInTheDocument();
  });

  it('shows the empty state when no zones exist', async () => {
    render(<GeofencePanel />);
    expect(await screen.findByText('No zones yet')).toBeInTheDocument();
  });

  it('creates a zone with the selected auto-action policy', async () => {
    render(<GeofencePanel />);
    fireEvent.click(await screen.findByText('Add Zone'));

    fireEvent.change(screen.getByLabelText('Zone name'), { target: { value: 'Work' } });
    fireEvent.change(screen.getByLabelText('Zone radius meters'), { target: { value: '1000' } });
    fireEvent.click(screen.getByLabelText('Auto action Capture'));
    fireEvent.click(screen.getByText('Create Zone'));

    await waitFor(() => {
      expect(mockCreateCalls).toHaveLength(1);
    });
    expect(mockCreateCalls[0]).toEqual({
      device_id: 'dev-1',
      name: 'Work',
      center_lat: 6.5244,
      center_lng: 3.3792,
      radius_meters: 1000,
      is_safe_zone: true,
      auto_action: 'capture',
    });
  });

  it('sends alert-only (null auto_action) when no policy is selected', async () => {
    render(<GeofencePanel />);
    fireEvent.click(await screen.findByText('Add Zone'));
    fireEvent.click(screen.getByText('Create Zone'));

    await waitFor(() => {
      expect(mockCreateCalls).toHaveLength(1);
    });
    expect(mockCreateCalls[0].auto_action).toBeNull();
  });

  it('rejects an invalid latitude with an inline error', async () => {
    render(<GeofencePanel />);
    fireEvent.click(await screen.findByText('Add Zone'));
    fireEvent.change(screen.getByLabelText('Zone latitude'), { target: { value: '99' } });
    fireEvent.click(screen.getByText('Create Zone'));

    expect(await screen.findByText('Enter a valid latitude (-90 to 90).')).toBeInTheDocument();
    expect(mockCreateCalls).toHaveLength(0);
  });

  it('deletes a zone only after the two-click confirm', async () => {
    mockZones = [baseZone()];
    render(<GeofencePanel />);
    const btn = await screen.findByLabelText('Delete zone Home');

    // First click only arms the confirm — nothing deleted yet.
    fireEvent.click(btn);
    expect(mockDeleteCalls).toEqual([]);
    expect(screen.getByText('Confirm?')).toBeInTheDocument();

    // Second click deletes.
    fireEvent.click(btn);
    await waitFor(() => {
      expect(mockDeleteCalls).toEqual([1]);
    });
  });

  it('does not clobber an open form when a new location fix streams in', async () => {
    render(<GeofencePanel />);
    fireEvent.click(await screen.findByText('Add Zone'));
    fireEvent.change(screen.getByLabelText('Zone latitude'), { target: { value: '6.55' } });

    // A fresh fix arrives for the same device (device key unchanged) — the
    // form must stay open with the user's typed value intact.
    mockLatestLocation = { lat: 9.0579, lng: 7.4951 };
    fireEvent.click(screen.getByLabelText('Auto action Capture'));

    expect(screen.getByLabelText('Zone latitude')).toHaveValue('6.55');
    expect(screen.getByText('New Zone')).toBeInTheDocument();
  });
});
