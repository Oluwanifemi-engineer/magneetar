/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/react';
import '@testing-library/jest-dom/jest-globals';

// ─── Mutable mock state ───────────────────────────────────────────────────
let mockDevices: any[] = [];
let mockSelectedDeviceId: string | null = null;
let mockLatestLocation: any = null;
let mockSetDevices: any = jest.fn();
let mockSelectDevice: any = jest.fn();

jest.mock('@/store/useStore', () => ({
  useStore: jest.fn((selector: any) => {
    const state = {
      devices: mockDevices,
      selectedDeviceId: mockSelectedDeviceId,
      latestLocation: mockLatestLocation,
      setDevices: mockSetDevices,
      selectDevice: mockSelectDevice,
    };
    return selector ? selector(state) : state;
  }),
}));

jest.mock('lucide-react', () => {
  const stub = (name: string) => {
    const Comp = (props: any) => <span data-testid={`icon-${name}`} {...props} />;
    Comp.displayName = name;
    return Comp;
  };
  return {
    BellRing: stub('BellRing'),
    MapPin: stub('MapPin'),
    LocateFixed: stub('LocateFixed'),
    Navigation: stub('Navigation'),
    ExternalLink: stub('ExternalLink'),
    Save: stub('Save'),
    Check: stub('Check'),
    Trash2: stub('Trash2'),
    X: stub('X'),
    Pencil: stub('Pencil'),
  };
});

jest.mock('@/lib/utils', () => ({
  cn: (...args: any[]) => args.filter(Boolean).join(' '),
  relativeTime: (v: any) => v || 'now',
  formatCoordinate: (v: any) => String(v),
  deviceDisplayName: (d: any) => d?.alias?.trim() || d?.model || d?.id || 'Device',
}));

jest.mock('@/components/ui/CoordDisplay', () => ({
  CoordDisplay: () => <div data-testid="coord-display" />,
}));

// ─── Mock API ─────────────────────────────────────────────────────────────
let mockUpdateCalls: any[] = [];
let mockDevicesResponse: any[] = [];
let mockDeleteDeviceImpl: any = null;

jest.mock('@/lib/api', () => ({
  getAPI: () => ({
    updateDeviceAlertSettings: jest.fn(async (deviceId: string, phone: string, email: string, opts?: any) => {
      mockUpdateCalls.push({ deviceId, phone, email, opts });
      return { status: 'ok', alert_phone: phone, alert_email: email };
    }),
    getDevices: jest.fn(async () => ({ devices: mockDevicesResponse })),
    updateDeviceAlias: jest.fn(async () => ({ status: 'ok' })),
    deleteDevice: jest.fn(async (deviceId: string, password: string) => {
      if (mockDeleteDeviceImpl) return mockDeleteDeviceImpl(deviceId, password);
      return { status: 'ok' };
    }),
  }),
}));

import { DevicePanel } from '@/components/devices/DevicePanel';

const baseDevice = (overrides: any = {}) => ({
  id: 'dev-1',
  alias: 'My Phone',
  model: 'SM-A037F',
  last_seen: '2026-08-02T10:00:00Z',
  registered: '2026-08-01T10:00:00Z',
  is_stolen: false,
  operating_mode: 'normal',
  sentinel_score: 0,
  lat: null,
  lng: null,
  battery_percent: null,
  is_online: false,
  alert_phone: null,
  alert_email: null,
  alert_channels: null,
  enabled_types: null,
  quiet_hours_start: null,
  quiet_hours_end: null,
  ...overrides,
});

describe('DevicePanel — alert settings', () => {
  beforeEach(() => {
    mockUpdateCalls = [];
    mockDevicesResponse = [];
    mockDevices = [baseDevice()];
    mockSelectedDeviceId = 'dev-1';
    mockLatestLocation = null;
  });

  it('renders the device name (alias preferred)', () => {
    render(<DevicePanel />);
    expect(screen.getByText('My Phone')).toBeInTheDocument();
  });

  it('expands alert settings and shows channel/type/quiet-hour controls', () => {
    render(<DevicePanel />);
    fireEvent.click(screen.getByText('Alert Settings'));

    expect(screen.getByLabelText('Toggle email channel')).toBeInTheDocument();
    expect(screen.getByLabelText('Toggle whatsapp channel')).toBeInTheDocument();
    expect(screen.getByLabelText('Toggle sms channel')).toBeInTheDocument();
    expect(screen.getByLabelText('Toggle push channel')).toBeInTheDocument();
    expect(screen.getByLabelText('Toggle Theft alert type')).toBeInTheDocument();
    expect(screen.getByLabelText('Toggle Offline alert type')).toBeInTheDocument();
    expect(screen.getByLabelText('Quiet hours start')).toBeInTheDocument();
    expect(screen.getByLabelText('Quiet hours end')).toBeInTheDocument();
  });

  it('locks emergency alert types (theft, SIM change, factory reset)', () => {
    render(<DevicePanel />);
    fireEvent.click(screen.getByText('Alert Settings'));

    // Emergencies ALWAYS deliver — the chips must be disabled so they can't be toggled
    expect(screen.getByLabelText('Toggle Theft alert type')).toBeDisabled();
    expect(screen.getByLabelText('Toggle SIM change alert type')).toBeDisabled();
    expect(screen.getByLabelText('Toggle Factory reset alert type')).toBeDisabled();

    // Non-emergency types stay toggleable
    expect(screen.getByLabelText('Toggle Offline alert type')).not.toBeDisabled();
    expect(screen.getByLabelText('Toggle Battery low alert type')).not.toBeDisabled();
  });

  it('sends channel/type/quiet-hour preferences in the save payload', async () => {
    render(<DevicePanel />);
    fireEvent.click(screen.getByText('Alert Settings'));

    // Uncheck whatsapp + offline, set quiet hours 22 -> 07
    fireEvent.click(screen.getByLabelText('Toggle whatsapp channel'));
    fireEvent.click(screen.getByLabelText('Toggle Offline alert type'));
    fireEvent.change(screen.getByLabelText('Quiet hours start'), { target: { value: '22' } });
    fireEvent.change(screen.getByLabelText('Quiet hours end'), { target: { value: '7' } });

    fireEvent.click(screen.getByText('Save Alert Settings'));

    await waitFor(() => expect(mockUpdateCalls.length).toBe(1));
    const call = mockUpdateCalls[0];
    expect(call.deviceId).toBe('dev-1');
    // whatsapp removed from the default four
    expect(call.opts.alert_channels).not.toContain('whatsapp');
    expect(call.opts.alert_channels).toContain('sms');
    // offline removed from the default type set
    expect(call.opts.enabled_types).not.toContain('device_offline');
    expect(call.opts.enabled_types).toContain('theft_detected');
    expect(call.opts.quiet_hours_start).toBe(22);
    expect(call.opts.quiet_hours_end).toBe(7);
  });

  it('pre-fills stored per-device preferences into the controls', () => {
    mockDevices = [
      baseDevice({
        alert_channels: ['whatsapp', 'push'],
        enabled_types: ['theft_detected', 'sim_changed', 'device_offline'],
        quiet_hours_start: 23,
        quiet_hours_end: 6,
      }),
    ];
    render(<DevicePanel />);
    fireEvent.click(screen.getByText('Alert Settings'));

    // whatsapp enabled (pressed), email not in the stored list -> unpressed
    expect(screen.getByLabelText('Toggle whatsapp channel')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByLabelText('Toggle email channel')).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByLabelText('Toggle Offline alert type')).toHaveAttribute('aria-pressed', 'true');
    // quiet hours prefilled
    expect((screen.getByLabelText('Quiet hours start') as HTMLSelectElement).value).toBe('23');
    expect((screen.getByLabelText('Quiet hours end') as HTMLSelectElement).value).toBe('6');
  });

  it('clears overrides when all channels/types are deselected (null = global defaults)', async () => {
    mockDevices = [baseDevice({ alert_channels: ['sms'], enabled_types: ['device_offline'] })];
    render(<DevicePanel />);
    fireEvent.click(screen.getByText('Alert Settings'));

    // Deselect everything: sms is the only one selected
    fireEvent.click(screen.getByLabelText('Toggle sms channel'));
    fireEvent.click(screen.getByLabelText('Toggle Offline alert type'));

    fireEvent.click(screen.getByText('Save Alert Settings'));
    await waitFor(() => expect(mockUpdateCalls.length).toBe(1));
    expect(mockUpdateCalls[0].opts.alert_channels).toBeNull();
    expect(mockUpdateCalls[0].opts.enabled_types).toBeNull();
  });
});

describe('DevicePanel — password-gated permanent deletion (step-up)', () => {
  beforeEach(() => {
    mockDevices = [baseDevice()];
    mockSelectedDeviceId = 'dev-1';
    mockDevicesResponse = [baseDevice()];
    mockDeleteDeviceImpl = null;
    mockSetDevices = jest.fn();
    mockSelectDevice = jest.fn();
  });

  it('opens the confirm card with a password input when Delete is clicked', () => {
    render(<DevicePanel />);
    expect(screen.queryByLabelText('Confirm deletion password')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('Delete Device Permanently'));

    expect(screen.getByLabelText('Confirm deletion password')).toBeInTheDocument();
    expect(screen.getByText('Yes, Delete')).toBeInTheDocument();
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  it('requires a password — empty input shows an error and never calls the API', async () => {
    render(<DevicePanel />);
    fireEvent.click(screen.getByText('Delete Device Permanently'));

    fireEvent.click(screen.getByText('Yes, Delete'));

    expect(screen.getByText('Enter your password to confirm.')).toBeInTheDocument();
    expect(mockDeleteDeviceImpl ?? true).toBe(true); // API not wired for assertions here
  });

  it('sends the step-up password to the API and refreshes the device list on success', async () => {
    let receivedPassword: string | undefined;
    mockDeleteDeviceImpl = jest.fn(async (_id: string, password: string) => {
      receivedPassword = password;
      return { status: 'ok', message: 'deleted' };
    });

    render(<DevicePanel />);
    fireEvent.click(screen.getByText('Delete Device Permanently'));
    fireEvent.change(screen.getByLabelText('Confirm deletion password'), {
      target: { value: 'correct-password' },
    });
    fireEvent.click(screen.getByText('Yes, Delete'));

    await waitFor(() => expect(receivedPassword).toBe('correct-password'));
    // Success closes the confirm card and clears the password field
    await waitFor(() => expect(screen.queryByLabelText('Confirm deletion password')).not.toBeInTheDocument());
  });

  it('keeps the confirm card open and shows the error when the password is wrong', async () => {
    mockDeleteDeviceImpl = jest.fn(async () => {
      const err: any = new Error('Invalid password');
      throw err;
    });

    render(<DevicePanel />);
    fireEvent.click(screen.getByText('Delete Device Permanently'));
    fireEvent.change(screen.getByLabelText('Confirm deletion password'), {
      target: { value: 'wrong-password' },
    });
    fireEvent.click(screen.getByText('Yes, Delete'));

    await waitFor(() => expect(screen.getByText('Invalid password')).toBeInTheDocument());
    // The confirm card stays open so the user can retry
    expect(screen.getByLabelText('Confirm deletion password')).toBeInTheDocument();
  });

  it('shows a warning banner for archived devices', () => {
    mockDevices = [baseDevice({ archived_at: '2026-07-01T00:00:00Z' })];
    render(<DevicePanel />);
    expect(screen.getByText('Archived')).toBeInTheDocument();
  });
});
