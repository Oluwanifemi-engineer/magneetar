/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom/jest-globals';

// ─── Mutable mock state ───────────────────────────────────────────────────
let mockSelectedDeviceId: string | null = 'device-001';
let mockCommands: any[] = [];
const mockSetCommands = jest.fn();
const mockIssueCommand = jest.fn<(...args: any[]) => any>();
const mockGetCommands = jest.fn<(...args: any[]) => any>();

jest.mock('@/store/useStore', () => ({    useStore: jest.fn((selector: any) => {
    const state = {
      selectedDeviceId: mockSelectedDeviceId,
      commands: mockCommands,
      setCommands: mockSetCommands,
    };
    return selector ? selector(state) : state;
  }),
}));

jest.mock('@/lib/api', () => ({
  getAPI: () => ({
    issueCommand: mockIssueCommand,
    getCommands: mockGetCommands,
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
  };
});

jest.mock('@/lib/utils', () => ({
  cn: (...args: any[]) => args.filter(Boolean).join(' '),
  isDestructiveCommand: (cmd: string) => ['wipe', 'reboot'].includes(cmd),
  getCommandLabel: (cmd: string) => cmd.toUpperCase(),
  formatTimestamp: () => '2024-01-01 12:00:00',
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
    mockIssueCommand.mockResolvedValue({ status: 'queued', command_id: 1 });
    mockGetCommands.mockResolvedValue({ commands: [] });
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
      expect(mockIssueCommand).toHaveBeenCalledWith('device-001', 'ping', '');
    });
  });

  it('issues the siren via wire command "alarm" when SIREN button is clicked', async () => {
    render(<CommandPanel />);
    const sirenBtn = screen.getByTestId('cmd-btn-alarm');
    fireEvent.click(sirenBtn);

    await waitFor(() => {
      expect(mockIssueCommand).toHaveBeenCalledWith('device-001', 'alarm', '');
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

  it('sends CONFIRMED_WIPE only after an explicit confirmation', async () => {
    render(<CommandPanel />);
    // First click arms the confirmation — no command issued yet.
    fireEvent.click(screen.getByTestId('cmd-btn-wipe'));
    expect(mockIssueCommand).not.toHaveBeenCalled();

    // Confirmation dialog appears; confirm issues the wipe with the wire param.
    const confirmBtn = screen.getByRole('button', { name: /confirm wipe/i });
    fireEvent.click(confirmBtn);
    await waitFor(() => {
      expect(mockIssueCommand).toHaveBeenCalledWith('device-001', 'wipe', 'CONFIRMED_WIPE');
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
      expect(mockIssueCommand).toHaveBeenCalledWith('device-001', 'capture_photo_front', '');
    });
  });

  it('location burst button sends location_burst', async () => {
    render(<CommandPanel />);
    fireEvent.click(screen.getByTestId('cmd-btn-location_burst'));
    await waitFor(() => {
      expect(mockIssueCommand).toHaveBeenCalledWith('device-001', 'location_burst', '');
    });
  });
});
