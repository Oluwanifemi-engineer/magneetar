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

const CHECKSUM = {
  // Mirrors the live /apk/checksum response for the v1.4.0 sideload build.
  filename: 'Magneetar-v1.4.0-release.apk',
  version: '1.4.0',
  sha256: 'a'.repeat(64),
  size_bytes: 7493780, // 7.1 MB (sideload flavor)
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

  it('renders the install guide and the direct APK link', async () => {
    render(<DownloadPage />);

    expect(screen.getByText(/Put Magneetar/i)).toBeInTheDocument();
    expect(screen.getByText('Download the APK')).toBeInTheDocument();
    expect(screen.getByText('Allow installs from this source')).toBeInTheDocument();
    expect(screen.getByText('Grant the two critical permissions')).toBeInTheDocument();
    expect(screen.getByText('Xiaomi / Redmi / POCO')).toBeInTheDocument();
    expect(screen.getByText('Huawei / Honor')).toBeInTheDocument();
    expect(screen.getByText('OPPO / Realme')).toBeInTheDocument();
    expect(screen.getByText('Vivo / iQOO')).toBeInTheDocument();

    // The primary CTA must never be the bare /apk/download URL (it 403s
    // without a signed ticket — the bug this page used to ship). It resolves
    // to the ticket-signed URL once minted, or stays '#' while pending.
    const downloadLink = screen.getByRole('link', { name: /download the apk \(direct\)/i });
    await waitFor(() => {
      expect(downloadLink).toHaveAttribute('href', expect.stringContaining('api.magneetar.me/apk/download?expires='));
    });
  });

  it('mints a download ticket and shows the live checksum', async () => {
    render(<DownloadPage />);

    expect(screen.getByText('FETCHING CHECKSUM…')).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(CHECKSUM.sha256)).toBeInTheDocument();
    });
    expect(screen.getByText(`v${CHECKSUM.version}`)).toBeInTheDocument();
    expect(screen.getByText('7.1 MB')).toBeInTheDocument();

    // API calls: the download ticket (pre-warm), the checksum — both carry an
    // 8s abort signal so a hung network can't freeze the button — plus the
    // Footer's live /health version badge (rendered on this page).
    expect(global.fetch).toHaveBeenCalledTimes(3);
    expect(global.fetch).toHaveBeenCalledWith(
      'https://api.magneetar.me/apk/ticket',
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
    expect(global.fetch).toHaveBeenCalledWith(
      'https://api.magneetar.me/apk/checksum',
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    );
  });

  it('shows a retry hint instead of a dead 403 link when the APIs are unreachable', async () => {
    global.fetch = jest.fn(() => Promise.reject(new Error('offline'))) as unknown as typeof fetch;

    render(<DownloadPage />);

    // Checksum error surfaces on mount (its own fetch failed).
    expect(await screen.findByText(/checksum unavailable right now/i)).toBeInTheDocument();
    // Regression (the download-button bug): with no ticket, the button must
    // NOT point at the bare /apk/download URL (403) — it stays inert at '#'.
    const link = screen.getByRole('link', { name: /download the apk \(direct\)/i });
    expect(link).toHaveAttribute('href', '#');

    // Clicking it attempts a fresh ticket, fails, and shows the retry hint
    // (never a dead navigation).
    link.click();
    expect(await screen.findByText(/couldn.t fetch a download ticket just now/i)).toBeInTheDocument();
    expect(link).toHaveAttribute('href', '#');
  });
});
