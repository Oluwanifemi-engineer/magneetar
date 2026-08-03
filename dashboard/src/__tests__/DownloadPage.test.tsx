/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/jest-globals';

// next/link requires a router context in tests — render a plain anchor instead.
jest.mock('next/link', () => {
  const Link = ({ href, children, ...props }: any) => (
    <a href={href} {...props}>{children}</a>
  );
  return Link;
});

import DownloadPage from '@/app/download/page';
import { APK_DOWNLOAD_URL } from '@/lib/utils';

const CHECKSUM = {
  filename: 'magneetar-v1.3.0-release.apk',
  version: '1.3.0',
  sha256: 'a'.repeat(64),
  size_bytes: 20971520, // 20 MB
};

const TICKET = {
  url: '/apk/download?expires=9999999999&sig=test-sig',
  expires_at: '2026-08-03T20:00:00Z',
};

// Resolve by URL so the ticket call and the checksum call get the right body.
function fetchMock() {
  return jest.fn((input: any) => {
    const url = typeof input === 'string' ? input : String(input);
    if (url.includes('/apk/ticket')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(TICKET) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(CHECKSUM) });
  }) as unknown as typeof fetch;
}

describe('Download Page', () => {
  beforeEach(() => {
    sessionStorage.clear();
    global.fetch = fetchMock();
  });

  it('renders the install guide and the direct APK link', () => {
    render(<DownloadPage />);

    expect(screen.getByText(/Put Magneetar/i)).toBeInTheDocument();
    expect(screen.getByText('Download the APK')).toBeInTheDocument();
    expect(screen.getByText('Allow installs from this source')).toBeInTheDocument();
    expect(screen.getByText('Grant the two critical permissions')).toBeInTheDocument();
    expect(screen.getByText('Xiaomi / Redmi / POCO')).toBeInTheDocument();
    expect(screen.getByText('Huawei / Honor')).toBeInTheDocument();
    expect(screen.getByText('OPPO / Realme')).toBeInTheDocument();
    expect(screen.getByText('Vivo / iQOO')).toBeInTheDocument();

    // The primary CTA points at the hosted APK (absolute URL) — either the
    // pre-ticket fallback or the ticket-signed URL.
    const downloadLink = screen.getByRole('link', { name: /download the apk \(direct\)/i });
    expect(downloadLink).toHaveAttribute('href', expect.stringContaining('api.magneetar.me/apk'));
  });

  it('mints a download ticket and shows the live checksum', async () => {
    render(<DownloadPage />);

    expect(screen.getByText('FETCHING CHECKSUM…')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(CHECKSUM.sha256)).toBeInTheDocument();
    });
    expect(screen.getByText(`v${CHECKSUM.version}`)).toBeInTheDocument();
    expect(screen.getByText('20.0 MB')).toBeInTheDocument();

    // Two API calls: the download ticket (rate-limited) and the checksum,
    // both with an abort signal (8s timeout).
    expect(global.fetch).toHaveBeenCalledTimes(2);
    expect(global.fetch).toHaveBeenCalledWith(
      'https://api.magneetar.me/apk/ticket',
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
    expect(global.fetch).toHaveBeenCalledWith(
      'https://api.magneetar.me/apk/checksum',
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });

  it('falls back gracefully when the APIs are unreachable', async () => {
    global.fetch = jest.fn(() => Promise.reject(new Error('offline'))) as unknown as typeof fetch;

    render(<DownloadPage />);

    expect(await screen.findByText(/checksum unavailable right now/i)).toBeInTheDocument();
    expect(await screen.findByText(/couldn.t fetch a fresh download ticket/i)).toBeInTheDocument();
    // The direct download must still be offered even without ticket/checksum.
    expect(screen.getByRole('link', { name: /download the apk \(direct\)/i })).toHaveAttribute(
      'href',
      APK_DOWNLOAD_URL
    );
  });
});
