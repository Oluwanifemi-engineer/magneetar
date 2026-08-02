/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/jest-globals';

// ─── Mutable mock state ───────────────────────────────────────────────────
let mockMedia: any[] = [];
let mockSelectedDeviceId: string | null = 'device-001';
const mockSetMedia = jest.fn();
const mockGetMedia = jest.fn<(...args: any[]) => any>();
const mockGetMediaFile = jest.fn<(...args: any[]) => any>();
const mockDeleteMedia = jest.fn<(...args: any[]) => any>();

jest.mock('@/store/useStore', () => ({
  useStore: jest.fn((selector: any) => {
    const state = {
      media: mockMedia,
      selectedDeviceId: mockSelectedDeviceId,
      setMedia: mockSetMedia,
    };
    return selector ? selector(state) : state;
  }),
}));

jest.mock('@/lib/api', () => ({
  getAPI: () => ({
    getMedia: mockGetMedia,
    getMediaFile: mockGetMediaFile,
    deleteMedia: mockDeleteMedia,
  }),
}));

jest.mock('lucide-react', () => {
  const stub = (name: string) => {
    const Comp = (props: any) => <span data-testid={`icon-${name}`} {...props} />;
    Comp.displayName = name;
    return Comp;
  };
  return {
    Camera: stub('Camera'),
    Music: stub('Music'),
    Play: stub('Play'),
    Pause: stub('Pause'),
    X: stub('X'),
    ChevronLeft: stub('ChevronLeft'),
    Trash2: stub('Trash2'),
    ShieldCheck: stub('ShieldCheck'),
    Lock: stub('Lock'),
  };
});

jest.mock('@/lib/utils', () => ({
  cn: (...args: any[]) => args.filter(Boolean).join(' '),
  formatTimestamp: (v: any) => v || '—',
  locationTimestamp: (loc: any) => loc?.server_timestamp || loc?.timestamp || null,
}));

import { MediaGallery } from '@/components/media/MediaGallery';

const baseItem = (overrides: any = {}) => ({
  id: 1,
  device_id: 'device-001',
  type: 'photo',
  timestamp: '2026-08-02T10:00:00Z',
  lat: null,
  lng: null,
  ...overrides,
});

describe('MediaGallery — password-gated deletion', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockMedia = [baseItem()];
    mockSelectedDeviceId = 'device-001';
    mockGetMedia.mockResolvedValue({ media: mockMedia });
    mockGetMediaFile.mockResolvedValue({ type: 'photo', data_b64: 'QUJD' });
    mockDeleteMedia.mockResolvedValue({ status: 'ok', deleted_id: 1 });
  });

  it('renders the captured media grid', async () => {
    render(<MediaGallery />);
    await waitFor(() => {
      expect(screen.getByText('PHOTO')).toBeInTheDocument();
    });
  });

  // Helper: enter manage mode and select every grid item so Delete (n) is enabled.
  const enterManageAndSelectAll = () => {
    fireEvent.click(screen.getByText('MANAGE'));
    fireEvent.click(screen.getByText('Select all'));
  };

  it('requires entering manage mode to delete, then asks for the password', async () => {
    render(<MediaGallery />);
    await waitFor(() => expect(mockGetMedia).toHaveBeenCalled());

    enterManageAndSelectAll();
    fireEvent.click(screen.getByText(/Delete \(1\)/));

    // Password prompt is portaled into document.body
    expect(screen.getByText('DELETE MEDIA')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
  });

  it('sends the entered password to the delete API', async () => {
    render(<MediaGallery />);
    await waitFor(() => expect(mockGetMedia).toHaveBeenCalled());

    enterManageAndSelectAll();
    fireEvent.click(screen.getByText(/Delete \(1\)/));

    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'S3cretPass' } });
    fireEvent.click(screen.getByRole('button', { name: /confirm delete/i }));

    await waitFor(() => {
      expect(mockDeleteMedia).toHaveBeenCalledWith(1, 'S3cretPass');
    });
  });

  it('reports a failed delete in the summary without aborting the batch', async () => {
    // Sequential delete: a rejected item is reported per-item (rate-limited /
    // bad password), never presented as a total failure via Promise.all.
    mockDeleteMedia.mockRejectedValueOnce(new Error('Invalid password'));
    render(<MediaGallery />);
    await waitFor(() => expect(mockGetMedia).toHaveBeenCalled());

    enterManageAndSelectAll();
    fireEvent.click(screen.getByText(/Delete \(1\)/));
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong' } });
    fireEvent.click(screen.getByRole('button', { name: /confirm delete/i }));

    await waitFor(() => {
      expect(mockDeleteMedia).toHaveBeenCalledWith(1, 'wrong');
    });
    await waitFor(() => {
      expect(screen.getByText(/0\/1 deleted/)).toBeInTheDocument();
    });
  });

  it('disables confirm until a password is entered', async () => {
    render(<MediaGallery />);
    await waitFor(() => expect(mockGetMedia).toHaveBeenCalled());

    enterManageAndSelectAll();
    fireEvent.click(screen.getByText(/Delete \(1\)/));

    expect(screen.getByRole('button', { name: /confirm delete/i })).toBeDisabled();
  });
});
