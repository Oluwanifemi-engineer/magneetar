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
      // access_role defaults to owner when absent, so an empty list is safe
      devices: mockDevices,
    };
    return selector ? selector(state) : state;
  }),
}));

let mockDevices: any[] = [];

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

jest.mock('@/components/ui/Toast', () => ({
  useToast: () => ({ toast: jest.fn() }),
  ToastProvider: ({ children }: any) => children,
}));

jest.mock('@/components/ui/Skeleton', () => ({
  MediaSkeleton: () => null,
}));

jest.mock('@/lib/utils', () => ({
  cn: (...args: any[]) => args.filter(Boolean).join(' '),
  formatTimestamp: (v: any) => v || '—',
  locationTimestamp: (loc: any) => loc?.server_timestamp || loc?.timestamp || null,
  stepUpPasswordHint: () => 'the master API key (API-key mode)',
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

describe('MediaGallery — audio playback', () => {
  const audioItem = (overrides: any = {}) => ({
    id: 7,
    device_id: 'device-001',
    type: 'audio',
    timestamp: '2026-08-15T10:00:00Z',
    lat: null,
    lng: null,
    ...overrides,
  });

  beforeEach(() => {
    jest.clearAllMocks();
    mockMedia = [audioItem()];
    mockSelectedDeviceId = 'device-001';
    mockGetMedia.mockResolvedValue({ media: mockMedia });
    mockGetMediaFile.mockResolvedValue({ type: 'audio', data_b64: 'QUJD' });
  });

  it('opens the audio viewer with a PLAY button and an audio element', async () => {
    render(<MediaGallery />);
    await waitFor(() => expect(mockGetMedia).toHaveBeenCalled());

    fireEvent.click(screen.getByText('AUDIO'));
    await waitFor(() => expect(mockGetMediaFile).toHaveBeenCalledWith(7));

    expect(screen.getByRole('button', { name: /play/i })).toBeInTheDocument();
    const audio = document.querySelector('audio');
    expect(audio).not.toBeNull();
    expect(audio!.getAttribute('src')).toContain('data:audio/mp4;base64');
    // Playback is gesture-driven: autoPlay must NOT be set (the pre-fix
    // behavior toggled autoPlay after mount, which autoplay policies block).
    expect(audio!.autoplay).toBe(false);
  });

  it('calls play() explicitly from the PLAY button (user-gesture playback)', async () => {
    const playMock = jest
      .spyOn(window.HTMLMediaElement.prototype, 'play')
      .mockResolvedValue();
    render(<MediaGallery />);
    await waitFor(() => expect(mockGetMedia).toHaveBeenCalled());

    fireEvent.click(screen.getByText('AUDIO'));
    await waitFor(() => expect(mockGetMediaFile).toHaveBeenCalledWith(7));

    fireEvent.click(screen.getByRole('button', { name: /play/i }));
    expect(playMock).toHaveBeenCalledTimes(1);
    playMock.mockRestore();
  });

  it('pauses when PLAY is pressed again while playing', async () => {
    const playMock = jest
      .spyOn(window.HTMLMediaElement.prototype, 'play')
      .mockResolvedValue();
    const pauseMock = jest
      .spyOn(window.HTMLMediaElement.prototype, 'pause')
      .mockImplementation(() => {});
    render(<MediaGallery />);
    await waitFor(() => expect(mockGetMedia).toHaveBeenCalled());

    fireEvent.click(screen.getByText('AUDIO'));
    await waitFor(() => expect(mockGetMediaFile).toHaveBeenCalledWith(7));

    fireEvent.click(screen.getByRole('button', { name: /play/i }));
    expect(playMock).toHaveBeenCalledTimes(1);

    // Button now reads PAUSE — clicking it pauses.
    await waitFor(() => expect(screen.getByRole('button', { name: /pause/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /pause/i }));
    expect(pauseMock).toHaveBeenCalledTimes(1);
    playMock.mockRestore();
    pauseMock.mockRestore();
  });

  it('shows a clear error when the browser blocks/rejects playback', async () => {
    const playMock = jest
      .spyOn(window.HTMLMediaElement.prototype, 'play')
      .mockRejectedValue(new Error('NotAllowedError: play() failed'));
    render(<MediaGallery />);
    await waitFor(() => expect(mockGetMedia).toHaveBeenCalled());

    fireEvent.click(screen.getByText('AUDIO'));
    await waitFor(() => expect(mockGetMediaFile).toHaveBeenCalledWith(7));

    fireEvent.click(screen.getByRole('button', { name: /play/i }));
    await waitFor(() => {
      expect(screen.getByText(/Playback failed/)).toBeInTheDocument();
    });
    playMock.mockRestore();
  });
});
