/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/jest-globals';

const mockSetDevices = jest.fn();

jest.mock('@/store/useStore', () => ({
  useStore: jest.fn(() => ({
    setDevices: mockSetDevices,
  })),
}));

const mockClaimDeviceByPairing = jest.fn<(...args: any[]) => any>();
const mockGetDevices = jest.fn<(...args: any[]) => any>();

jest.mock('@/lib/api', () => ({
  getAPI: () => ({
    claimDeviceByPairing: mockClaimDeviceByPairing,
    getDevices: mockGetDevices,
  }),
}));

// Icons used by the modal — stub them out.
jest.mock('lucide-react', () => ({
  Link2: () => null,
  X: () => null,
  Loader2: () => null,
  CheckCircle2: () => null,
  Smartphone: () => null,
}));

import { ClaimDeviceModal } from '@/components/devices/ClaimDeviceModal';

describe('ClaimDeviceModal', () => {
  const onClose = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    mockClaimDeviceByPairing.mockResolvedValue({ status: 'ok', device_id: 'mt-abc123', owner_id: 'usr-x' });
    mockGetDevices.mockResolvedValue({ devices: [] });
  });

  it('renders the two required inputs', () => {
    render(<ClaimDeviceModal onClose={onClose} />);
    expect(screen.getByLabelText('Device ID')).toBeInTheDocument();
    expect(screen.getByLabelText('Pairing code')).toBeInTheDocument();
  });

  it('rejects a malformed pairing code client-side', async () => {
    render(<ClaimDeviceModal onClose={onClose} />);
    fireEvent.change(screen.getByLabelText('Device ID'), { target: { value: 'mt-abc123' } });
    fireEvent.change(screen.getByLabelText('Pairing code'), { target: { value: 'NOTHEX!' } });
    fireEvent.click(screen.getByText('Link Device'));

    expect(await screen.findByText(/8 lowercase hex/i)).toBeInTheDocument();
    expect(mockClaimDeviceByPairing).not.toHaveBeenCalled();
  });

  it('calls the API with normalized (lowercase) code and refreshes devices', async () => {
    render(<ClaimDeviceModal onClose={onClose} />);
    fireEvent.change(screen.getByLabelText('Device ID'), { target: { value: '  mt-abc123  ' } });
    fireEvent.change(screen.getByLabelText('Pairing code'), { target: { value: 'A1B2C3D4' } });
    fireEvent.click(screen.getByText('Link Device'));

    await waitFor(() => {
      expect(mockClaimDeviceByPairing).toHaveBeenCalledWith('mt-abc123', 'a1b2c3d4');
    });
    expect(mockGetDevices).toHaveBeenCalled();
    expect(mockSetDevices).toHaveBeenCalled();
  });

  it('surfaces the server error (e.g. device limit) verbatim', async () => {
    mockClaimDeviceByPairing.mockRejectedValue(
      new Error('Device limit reached (1/1) — delete a device or upgrade your plan')
    );
    render(<ClaimDeviceModal onClose={onClose} />);
    fireEvent.change(screen.getByLabelText('Device ID'), { target: { value: 'mt-abc123' } });
    fireEvent.change(screen.getByLabelText('Pairing code'), { target: { value: 'a1b2c3d4' } });
    fireEvent.click(screen.getByText('Link Device'));

    expect(await screen.findByText(/Device limit reached/i)).toBeInTheDocument();
  });

  it('closes after a successful link', async () => {
    render(<ClaimDeviceModal onClose={onClose} />);
    fireEvent.change(screen.getByLabelText('Device ID'), { target: { value: 'mt-abc123' } });
    fireEvent.change(screen.getByLabelText('Pairing code'), { target: { value: 'a1b2c3d4' } });
    fireEvent.click(screen.getByText('Link Device'));

    await waitFor(() => expect(onClose).toHaveBeenCalled(), { timeout: 3000 });
  });
});
