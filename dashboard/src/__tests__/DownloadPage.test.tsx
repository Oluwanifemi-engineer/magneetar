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
  filename: 'Magneetar-v1.4.0-release.apk',
  version: '1.4.0',
  sha256: 'a'.repeat(64),
  size_bytes: 7493780,
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

    // Should have 3 fetch calls: ticket, checksum, and health
    expect(global.fetch).toHaveBeenCalledTimes(3);
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
});
