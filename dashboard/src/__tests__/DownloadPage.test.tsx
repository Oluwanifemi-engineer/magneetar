/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/jest-globals';

// next/link requires a router context in tests — render a plain anchor instead.
jest.mock('next/link', () => {
  const Link = ({ href, children, ...props }: any) => (
    <a href={href} {...props}>{children}</a>
  );
  return Link;
});

import DownloadPage from '@/app/download/page';
import { pickDownloadUrl } from '@/lib/downloadTicket';

const CHECKSUM = {
  filename: 'Magneetar-v1.4.0-release.apk',
  version: '1.4.0',
  sha256: 'a'.repeat(64),
  size_bytes: 7493780,
};

// Source tarball gets a DISTINCT hash so the two checksum blocks render
// different values (the page shows APK + source checksums side by side).
const SOURCE_CHECKSUM = {
  ...CHECKSUM,
  filename: 'magneetar-v1.4.0-source.tar.gz',
  sha256: 'b'.repeat(64),
};

const TICKET = {
  url: '/apk/download?expires=9999999999&sig=test-sig',
  expires_at: '2026-08-03T20:00:00Z',
};

function fetchMock() {
  return jest.fn((input: any) => {
    const url = typeof input === 'string' ? input : String(input);
    if (url.includes('/apk/ticket')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(TICKET) });
    }
    if (url.includes('/apk/download')) {
      // The APK bytes — the click path fetches the file and downloads it as
      // a blob (no navigation), so the mock must support blob()/ok like a
      // real FileResponse.
      return Promise.resolve({ ok: true, blob: () => Promise.resolve(new Blob(['APK-BYTES'])) });
    }
    if (url.includes('/apk/source')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(SOURCE_CHECKSUM) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve(CHECKSUM) });
  }) as unknown as typeof fetch;
}

describe('Download Page', () => {
  beforeEach(() => {
    sessionStorage.clear();
    global.fetch = fetchMock();
  });

  it('renders the download page with header and features', async () => {
    render(<DownloadPage />);

    // Check for key features (using getAllByText for features that appear multiple times)
    expect(screen.getAllByText(/Real-time GPS tracking/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Remote lock/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Theft detection/i).length).toBeGreaterThan(0);
    expect(screen.getByText('Xiaomi / Redmi / POCO')).toBeInTheDocument();
    expect(screen.getByText('Huawei / Honor')).toBeInTheDocument();
    expect(screen.getByText('OPPO / Realme')).toBeInTheDocument();
    expect(screen.getByText('Vivo / iQOO')).toBeInTheDocument();

    // Download link should resolve to ticket-signed URL
    const downloadLink = screen.getByRole('link', { name: /download magneetar/i });
    await waitFor(() => {
      expect(downloadLink).toHaveAttribute('href', expect.stringContaining('api.magneetar.me/apk/download?expires='));
    });
  });

  it('shows version info and checksum', async () => {
    render(<DownloadPage />);

    await waitFor(() => {
      expect(screen.getByText(CHECKSUM.sha256)).toBeInTheDocument();
    });

    // Should have 4 fetch calls: ticket, apk checksum, source checksum, health
    expect(global.fetch).toHaveBeenCalledTimes(4);
    // Both checksum blocks render (APK + per-release source tarball).
    expect(screen.getByText(SOURCE_CHECKSUM.sha256)).toBeInTheDocument();
  });

  it('shows error state when APIs are unreachable', async () => {
    global.fetch = jest.fn(() => Promise.reject(new Error('offline'))) as unknown as typeof fetch;

    render(<DownloadPage />);

    // Download link should stay at '#' when no ticket
    const link = screen.getByRole('link', { name: /download magneetar/i });
    expect(link).toHaveAttribute('href', '#');

    // Clicking should show error
    link.click();
    await waitFor(() => {
      expect(screen.getByText(/unavailable/i)).toBeInTheDocument();
    });
  });

  it('downloads the APK as a blob without navigating (regression: old flow used window.location.href, which some browsers treated as a page refresh)', async () => {
    // jsdom has no URL.createObjectURL — the blob path needs it to download.
    const createObjectURL = jest.fn(() => 'blob:mock-apk');
    const revokeObjectURL = jest.fn();
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, writable: true });
    Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, writable: true });

    render(<DownloadPage />);
    // Wait for the pre-minted ticket so the click has a valid fallback URL.
    const link = screen.getByRole('link', { name: /download magneetar/i });
    await waitFor(() => {
      expect(link).toHaveAttribute('href', expect.stringContaining('api.magneetar.me/apk/download?expires='));
    });

    // Spy on anchor clicks so the jsdom navigation doesn't actually run.
    // NOTE: use fireEvent (not link.click()) — spying on prototype.click
    // swallows the native dispatch, which would keep React's onClick from
    // ever firing.
    const clickSpy = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    fireEvent.click(link);

    await waitFor(() => {
      // The blob download path created an <a download="…apk"> and clicked it
      // (the old flow navigated via window.location.href instead, which some
      // browsers treated as a page refresh — no download). The mint + fetch +
      // blob chain is async, so wait for the download anchor specifically.
      const apkDownloadClicked = clickSpy.mock.instances.some(
        (inst) => (inst as unknown as HTMLAnchorElement)?.download?.includes('.apk')
      );
      expect(apkDownloadClicked).toBe(true);
    });
    expect(createObjectURL).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalled();

    clickSpy.mockRestore();
  });

});

describe('pickDownloadUrl (download ticket selection)', () => {
  const FRESH = 'https://api.magneetar.me/apk/download?expires=9999999999&sig=fresh';
  const OLD_VALID = 'https://api.magneetar.me/apk/download?expires=9999999999&sig=old';
  const EXPIRED = 'https://api.magneetar.me/apk/download?expires=1&sig=old';

  it('prefers a freshly minted URL over the pre-minted href', () => {
    expect(pickDownloadUrl(FRESH, EXPIRED)).toBe(FRESH);
  });

  it('falls back to a still-valid pre-minted href when the re-mint fails', () => {
    expect(pickDownloadUrl(null, OLD_VALID)).toContain('apk/download?expires=9999999999');
  });

  it('rejects an expired pre-minted href (regression: server 403 expired-ticket)', () => {
    expect(pickDownloadUrl(null, EXPIRED)).toBeNull();
  });

  it('returns null when no ticket is available', () => {
    expect(pickDownloadUrl(null, null)).toBeNull();
  });
});
