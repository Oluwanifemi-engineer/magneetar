/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom/jest-globals';

// ─── Mutable mock state ───────────────────────────────────────────────────
let mockSelectedDeviceId: string | null = 'device-001';
let mockCommands: any[] = [];
let mockDevices: any[] = [];
const mockSetCommands = jest.fn();
const mockIssueCommand = jest.fn<(...args: any[]) => any>();
const mockGetCommands = jest.fn<(...args: any[]) => any>();
const mockDeleteCommand = jest.fn<(...args: any[]) => any>();
const mockClearCommandHistory = jest.fn<(...args: any[]) => any>();

jest.mock('@/store/useStore', () => ({    useStore: jest.fn((selector: any) => {
    const state = {
      selectedDeviceId: mockSelectedDeviceId,
      commands: mockCommands,
      setCommands: mockSetCommands,
      devices: mockDevices,
    };
    return selector ? selector(state) : state;
  }),
}));

jest.mock('@/lib/api', () => ({
  getAPI: () => ({
    issueCommand: mockIssueCommand,
    getCommands: mockGetCommands,
    deleteCommand: mockDeleteCommand,
    clearCommandHistory: mockClearCommandHistory,
  }),
}));

jest.mock('lucide-react', () => {
  const noop = () => null;
  return {
    Radio: noop,
    Camera: noop,
    Webcam: noop,
    Mic: noop,
    LocateFixed: noop,
    Lock: noop,
    Siren: noop,
    AlertTriangle: noop,
    CheckCircle2: noop,
    Trash2: noop,
    X: noop,
    MessageSquareText: noop,
  };
});

jest.mock('@/lib/utils', () => ({
  cn: (...args: any[]) => args.filter(Boolean).join(' '),
  isDestructiveCommand: (cmd: string) => ['wipe', 'reboot'].includes(cmd),
  getCommandLabel: (cmd: string) => cmd.toUpperCase(),
  formatTimestamp: () => '2024-01-01 12:00:00',
  stepUpPasswordHint: () => 'the master API key (API-key mode)',
}));

jest.mock('@/components/ui/CommandButton', () => ({
  CommandButton: ({ command, label, icon, loading, onSend }: any) => (
    <button
      data-testid={`cmd-btn-${command}`}
      data-loading={loading ? 'true' : 'false'}
      onClick={onSend}
    >
      {loading ? '...' : icon} {label}
    </button>
  ),
}));

import { CommandPanel } from '@/components/commands/CommandPanel';

describe('CommandPanel Component', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSelectedDeviceId = 'device-001';
    mockCommands = [];
    mockDevices = [];
    mockIssueCommand.mockResolvedValue({ status: 'queued', command_id: 1 });
    mockGetCommands.mockResolvedValue({ commands: [] });
    mockDeleteCommand.mockResolvedValue({ status: 'ok', deleted_id: 1 });
    mockClearCommandHistory.mockResolvedValue({ status: 'ok', deleted: 1 });
  });

  it('shows an offline-SMS notice when the device is offline with SMS enabled', () => {
    mockDevices = [{
      id: 'device-001',
      is_online: false,
      sms_commands_enabled: true,
      sms_phone: '+2348012345678',
    }];
    render(<CommandPanel />);
    expect(screen.getByText(/delivered via SMS/i)).toBeInTheDocument();
    expect(screen.getByText(/\+2348012345678/)).toBeInTheDocument();
  });

  it('hides the offline-SMS notice when the device is online', () => {
    mockDevices = [{
      id: 'device-001',
      is_online: true,
      sms_commands_enabled: true,
      sms_phone: '+2348012345678',
    }];
    render(<CommandPanel />);
    expect(screen.queryByText(/delivered via SMS/i)).not.toBeInTheDocument();
  });

  it('hides the offline-SMS notice when SMS commands are not enabled', () => {
    mockDevices = [{
      id: 'device-001',
      is_online: false,
      sms_commands_enabled: false,
      sms_phone: null,
    }];
    render(<CommandPanel />);
    expect(screen.queryByText(/delivered via SMS/i)).not.toBeInTheDocument();
  });

  it('renders all quick action command buttons', () => {
    render(<CommandPanel />);
    // The siren button sends wire command 'alarm' (server/device contract).
    expect(screen.getByTestId('cmd-btn-ping')).toBeInTheDocument();
    expect(screen.getByTestId('cmd-btn-capture_photo')).toBeInTheDocument();
    expect(screen.getByTestId('cmd-btn-capture_photo_front')).toBeInTheDocument();
    expect(screen.getByTestId('cmd-btn-capture_audio')).toBeInTheDocument();
    expect(screen.getByTestId('cmd-btn-location_burst')).toBeInTheDocument();
    expect(screen.getByTestId('cmd-btn-lock')).toBeInTheDocument();
    expect(screen.getByTestId('cmd-btn-alarm')).toBeInTheDocument();
    expect(screen.getByTestId('cmd-btn-wipe')).toBeInTheDocument();
  });

  it('shows empty state when no commands in history', () => {
    render(<CommandPanel />);
    expect(screen.getByText('No commands sent yet.')).toBeInTheDocument();
  });

  it('renders command history when commands exist', () => {
    mockCommands = [
      {
        id: 1,
        device_id: 'device-001',
        command: 'ping',
        params: '',
        status: 'executed',
        issued_at: '2024-01-01T12:00:00Z',
        executed_at: '2024-01-01T12:00:05Z',
      },
    ];
    mockGetCommands.mockResolvedValue({ commands: mockCommands });
    render(<CommandPanel />);
    expect(screen.getByText('executed')).toBeInTheDocument();
  });

  it('issues a ping command when Ping button is clicked', async () => {
    render(<CommandPanel />);
    const pingBtn = screen.getByTestId('cmd-btn-ping');
    fireEvent.click(pingBtn);

    await waitFor(() => {
      expect(mockIssueCommand).toHaveBeenCalledWith('device-001', 'ping', '', undefined);
    });
  });

  it('issues the siren via wire command "alarm" when SIREN button is clicked', async () => {
    render(<CommandPanel />);
    const sirenBtn = screen.getByTestId('cmd-btn-alarm');
    fireEvent.click(sirenBtn);

    await waitFor(() => {
      expect(mockIssueCommand).toHaveBeenCalledWith('device-001', 'alarm', '', undefined);
    });
  });

  it('does not issue commands when no device is selected', () => {
    mockSelectedDeviceId = null;
    render(<CommandPanel />);
    // Buttons still render; clicking should be a no-op since handleSend early-returns
    const pingBtn = screen.getByTestId('cmd-btn-ping');
    fireEvent.click(pingBtn);
    expect(mockIssueCommand).not.toHaveBeenCalled();
  });

  it('sends CONFIRMED_WIPE only after an explicit confirmation + step-up password', async () => {
    render(<CommandPanel />);
    // First click arms the confirmation — no command issued yet.
    fireEvent.click(screen.getByTestId('cmd-btn-wipe'));
    expect(mockIssueCommand).not.toHaveBeenCalled();

    // Confirmation dialog appears; a wipe needs the step-up password (the
    // server re-verifies it before queueing a factory reset).
    const confirmBtn = screen.getByRole('button', { name: /confirm wipe/i });
    fireEvent.click(confirmBtn);
    // Empty password → local validation, no API call.
    expect(mockIssueCommand).not.toHaveBeenCalled();
    expect(screen.getByText('Enter your password to confirm the wipe.')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Confirm wipe password'), { target: { value: 'master-key' } });
    fireEvent.click(confirmBtn);
    await waitFor(() => {
      expect(mockIssueCommand).toHaveBeenCalledWith('device-001', 'wipe', 'CONFIRMED_WIPE', 'master-key');
    });
  });

  it('wipe password is required — Enter with empty password does not fire', async () => {
    render(<CommandPanel />);
    fireEvent.click(screen.getByTestId('cmd-btn-wipe'));
    fireEvent.keyDown(screen.getByLabelText('Confirm wipe password'), { key: 'Enter' });
    expect(mockIssueCommand).not.toHaveBeenCalled();
    expect(screen.getByText('Enter your password to confirm the wipe.')).toBeInTheDocument();
  });

  it('wipe sends the password on Enter', async () => {
    render(<CommandPanel />);
    fireEvent.click(screen.getByTestId('cmd-btn-wipe'));
    fireEvent.change(screen.getByLabelText('Confirm wipe password'), { target: { value: 's3cret' } });
    fireEvent.keyDown(screen.getByLabelText('Confirm wipe password'), { key: 'Enter' });
    await waitFor(() => {
      expect(mockIssueCommand).toHaveBeenCalledWith('device-001', 'wipe', 'CONFIRMED_WIPE', 's3cret');
    });
  });

  it('shows an error strip when a command is rejected', async () => {
    mockIssueCommand.mockRejectedValueOnce(new Error('Wipe requires params'));
    render(<CommandPanel />);
    fireEvent.click(screen.getByTestId('cmd-btn-ping'));

    await waitFor(() => {
      expect(screen.getByText(/Wipe requires params/)).toBeInTheDocument();
    });
  });

  it('front camera button sends capture_photo_front', async () => {
    render(<CommandPanel />);
    fireEvent.click(screen.getByTestId('cmd-btn-capture_photo_front'));
    await waitFor(() => {
      expect(mockIssueCommand).toHaveBeenCalledWith('device-001', 'capture_photo_front', '', undefined);
    });
  });

  it('location burst button sends location_burst', async () => {
    render(<CommandPanel />);
    fireEvent.click(screen.getByTestId('cmd-btn-location_burst'));
    await waitFor(() => {
      expect(mockIssueCommand).toHaveBeenCalledWith('device-001', 'location_burst', '', undefined);
    });
  });
});

describe('CommandPanel — password-gated history deletion (step-up)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockSelectedDeviceId = 'device-001';
    mockCommands = [
      { id: 1, command: 'ping', status: 'executed', issued_at: '2024-01-01' },
      { id: 2, command: 'lock', status: 'pending', issued_at: '2024-01-02' },
    ];
    mockGetCommands.mockResolvedValue({ commands: mockCommands });
    mockDeleteCommand.mockResolvedValue({ status: 'ok', deleted_id: 1 });
    mockClearCommandHistory.mockResolvedValue({ status: 'ok', deleted: 1 });
  });

  it('shows a per-row trash button and opens the password card', () => {
    render(<CommandPanel />);
    const trash = screen.getAllByLabelText(/Delete .* command/);
    expect(trash).toHaveLength(2);
    fireEvent.click(trash[0]);
    expect(screen.getByLabelText('Confirm deletion password')).toBeInTheDocument();
  });

  it('requires a password — empty input never calls the API', async () => {
    render(<CommandPanel />);
    fireEvent.click(screen.getAllByLabelText(/Delete .* command/)[0]);
    fireEvent.click(screen.getByText('Yes, Delete'));
    await waitFor(() => {
      expect(screen.getByText('Enter your password to confirm.')).toBeInTheDocument();
    });
    expect(mockDeleteCommand).not.toHaveBeenCalled();
  });

  it('deletes a single command with the step-up password', async () => {
    render(<CommandPanel />);
    fireEvent.click(screen.getAllByLabelText(/Delete .* command/)[0]);
    fireEvent.change(screen.getByLabelText('Confirm deletion password'), { target: { value: 's3cret' } });
    fireEvent.click(screen.getByText('Yes, Delete'));
    await waitFor(() => {
      expect(mockDeleteCommand).toHaveBeenCalledWith(1, 's3cret');
    });
  });

  it('keeps the card open and shows the error when the password is wrong', async () => {
    mockDeleteCommand.mockRejectedValueOnce(new Error('Invalid password'));
    render(<CommandPanel />);
    fireEvent.click(screen.getAllByLabelText(/Delete .* command/)[0]);
    fireEvent.change(screen.getByLabelText('Confirm deletion password'), { target: { value: 'wrong' } });
    fireEvent.click(screen.getByText('Yes, Delete'));
    await waitFor(() => {
      expect(screen.getByText('Invalid password')).toBeInTheDocument();
    });
    expect(screen.getByLabelText('Confirm deletion password')).toBeInTheDocument();
  });

  it('shows Clear all finished only when finished commands exist and clears them with the password', async () => {
    render(<CommandPanel />);
    fireEvent.click(screen.getByText('Clear all finished'));
    expect(screen.getByLabelText('Confirm deletion password')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Confirm deletion password'), { target: { value: 's3cret' } });
    fireEvent.click(screen.getByText('Yes, Delete'));
    await waitFor(() => {
      expect(mockClearCommandHistory).toHaveBeenCalledWith('device-001', 's3cret');
    });
  });

  it('hides Clear all finished when every command is pending', () => {
    mockCommands = [{ id: 2, command: 'lock', status: 'pending', issued_at: '2024-01-02' }];
    render(<CommandPanel />);
    expect(screen.queryByText('Clear all finished')).not.toBeInTheDocument();
  });

  it('resets the pending delete confirm when the selected device changes', () => {
    const { rerender } = render(<CommandPanel />);
    fireEvent.click(screen.getAllByLabelText(/Delete .* command/)[0]);
    expect(screen.getByLabelText('Confirm deletion password')).toBeInTheDocument();

    mockSelectedDeviceId = 'device-002';
    rerender(<CommandPanel />);
    expect(screen.queryByLabelText('Confirm deletion password')).not.toBeInTheDocument();
  });
});
