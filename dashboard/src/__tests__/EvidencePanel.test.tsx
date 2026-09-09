/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/react';
import '@testing-library/jest-dom/jest-globals';

// ─── Mutable mock state ───────────────────────────────────────────────────
let mockSelectedDeviceId: string | null = null;
let mockEvidence: any = null;
let mockGenerate: jest.Mock | null = null;
let mockToast: jest.Mock | null = null;

jest.mock('@/store/useStore', () => ({
  useStore: jest.fn((selector: any) => {
    const state = {
      selectedDeviceId: mockSelectedDeviceId,
      devices: [],
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
    ClipboardList: stub('ClipboardList'),
    FileText: stub('FileText'),
    Loader: stub('Loader'),
    Loader2: stub('Loader2'),
    ShieldCheck: stub('ShieldCheck'),
  };
});

jest.mock('@/lib/utils', () => ({
  cn: (...args: any[]) => args.filter(Boolean).join(' '),
}));

jest.mock('@/components/ui/Skeleton', () => ({
  EvidenceSkeleton: () => null,
}));

jest.mock('@/components/ui/Toast', () => ({
  useToast: () => ({ toast: mockToast }),
  ToastProvider: ({ children }: any) => children,
}));

jest.mock('@/lib/api', () => ({
  getAPI: () => ({
    getEvidence: jest.fn(async () => mockEvidence),
    generateEvidencePDF: mockGenerate,
  }),
}));

import { EvidencePanel } from '@/components/panels/EvidencePanel';

const activeCase = {
  case_id: 'MGT-2026-AB12C',
  status: 'active',
  item_counts: { locations: 12, photos: 3, audio: 1 },
  sha256_chain: 'a'.repeat(64),
};

describe('EvidencePanel — recovery dossier export', () => {
  beforeEach(() => {
    mockSelectedDeviceId = 'dev-1';
    mockEvidence = activeCase;
    mockGenerate = jest.fn(async () => new Blob(['%PDF-1.4'], { type: 'application/pdf' }));
    mockToast = jest.fn();
  });

  it('renders the active case summary with counters and chain prefix', async () => {
    render(<EvidencePanel />);

    expect(await screen.findByText('#MGT-2026-AB12C')).toBeInTheDocument();
    expect(screen.getByText('ACTIVE')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(screen.getByText(/aaaa/)).toBeInTheDocument();
  });

  it('shows the empty state when the device has no evidence case', async () => {
    mockEvidence = { case_id: null, status: 'none' };
    render(<EvidencePanel />);

    expect(await screen.findByText('No active evidence case')).toBeInTheDocument();
    // The dossier button stays enabled — the server auto-creates a case and
    // the PDF is useful even before theft detection (device info + command
    // timeline + location trail).
    expect(screen.getByText('EXPORT RECOVERY DOSSIER (PDF)')).toBeEnabled();
  });

  it('exports the dossier and fires a success toast', async () => {
    render(<EvidencePanel />);

    fireEvent.click(await screen.findByText('EXPORT RECOVERY DOSSIER (PDF)'));

    await waitFor(() => {
      expect(mockGenerate).toHaveBeenCalledWith('dev-1');
    });
    expect(mockToast).toHaveBeenCalledWith(
      expect.stringContaining('Recovery dossier downloaded'),
      'success'
    );
  });

  it('surfaces generation failures as both an inline error and an error toast', async () => {
    mockGenerate = jest.fn(async () => {
      throw new Error('No evidence data found');
    });
    render(<EvidencePanel />);

    fireEvent.click(await screen.findByText('EXPORT RECOVERY DOSSIER (PDF)'));

    expect(await screen.findByText('No evidence data found')).toBeInTheDocument();
    expect(mockToast).toHaveBeenCalledWith('No evidence data found', 'error');
  });

  it('re-enables the button after a failed generation (no stuck spinner)', async () => {
    mockGenerate = jest.fn(async () => {
      throw new Error('boom');
    });
    render(<EvidencePanel />);

    const btn = await screen.findByText('EXPORT RECOVERY DOSSIER (PDF)');
    fireEvent.click(btn);

    await waitFor(() => {
      expect(screen.getByText('EXPORT RECOVERY DOSSIER (PDF)')).toBeEnabled();
    });
  });
});
