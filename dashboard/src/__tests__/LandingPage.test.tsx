/**
 * @jest-environment jsdom
 */
import { describe, it, expect, jest, beforeEach } from '@jest/globals';
import { render, screen, act, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom/jest-globals';

// next/link requires a router context in tests — render a plain anchor instead.
jest.mock('next/link', () => {
  const Link = ({ href, children, ...props }: any) => (
    <a href={href} {...props}>{children}</a>
  );
  return Link;
});

import HomePage from '@/app/page';

async function renderPage() {
  await act(async () => {
    render(<HomePage />);
  });
}

describe('Landing Page', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('renders every landing section', async () => {
    await renderPage();

    // Nav
    expect(screen.getAllByText('MAGNEETAR').length).toBeGreaterThan(0);
    expect(screen.getAllByText('TRACK · PROTECT · RECOVER').length).toBeGreaterThan(0);

    // Hero — headline split across lines with <br />
    expect(screen.queryByText(/Protect what/)).toBeTruthy();
    expect(screen.queryByText(/Stay close to/)).toBeTruthy();
    // Hero stats — AnimatedCounter renders the value and suffix as separate
    // text nodes (e.g. "24" + "/7"), so assert on the stable stat labels.
    expect(screen.getByText('automated tests')).toBeInTheDocument();
    expect(screen.getByText('stealth tracking')).toBeInTheDocument();
    expect(screen.getByText('chain-of-custody hashing')).toBeInTheDocument();
    expect(screen.getByText('background persistence')).toBeInTheDocument();

    // Features grid
    expect(screen.getByText('Sentinel AI')).toBeInTheDocument();
    expect(screen.getByText('Family & Team Circles')).toBeInTheDocument();
    expect(screen.getByText('Multi-Device Fleet')).toBeInTheDocument();
    expect(screen.getByText('Guardian Network')).toBeInTheDocument();
    expect(screen.getByText('Remote Evidence Capture')).toBeInTheDocument();
    expect(screen.getByText('Phantom Mode')).toBeInTheDocument();
    expect(screen.getByText('Forensic Reports')).toBeInTheDocument();

    // How it works
    expect(screen.getByText('Install & connect in minutes')).toBeInTheDocument();
    expect(screen.getByText('Stay in sync, always')).toBeInTheDocument();
    expect(screen.getByText('Theft detected — recover it')).toBeInTheDocument();

    // Built for Africa (NBS-sourced stats)
    expect(screen.getByText('WHY MAGNEETAR')).toBeInTheDocument();
    expect(screen.getByText('25M+')).toBeInTheDocument();
    expect(screen.getByText('11.7%')).toBeInTheDocument();
    expect(screen.getByText('of reported stolen phones are recovered')).toBeInTheDocument();
    expect(screen.getByText(/National Bureau of Statistics/)).toBeInTheDocument();

    // Our story (provenance / social proof)
    expect(screen.getByText('OUR STORY')).toBeInTheDocument();
    expect(screen.getByText('Started with real problems')).toBeInTheDocument();
    expect(screen.getByText('Protection + connection')).toBeInTheDocument();
    expect(screen.getByText('Built to grow beyond any campus')).toBeInTheDocument();

    // Download APK + free-plan messaging (nav, hero, CTA) — CTAs now route
    // through the /download guide page, which carries the direct APK link.
    const apkLinks = screen.getAllByRole('link', { name: /download apk/i });
    expect(apkLinks.length).toBeGreaterThan(0);
    apkLinks.forEach((link) => {
      expect(link).toHaveAttribute('href', '/download');
    });

    // Honest-signal footnote must not leak placeholder copy.
    expect(screen.queryByText(/real adoption numbers coming as users arrive/i)).not.toBeInTheDocument();

    // Hero mockup is labelled as a demo — no fabricated live-device claims.
    expect(screen.getByText('Galaxy S24 · Active')).toBeInTheDocument();
    expect(screen.getAllByText('Free for 1 device · No credit card required').length).toBeGreaterThan(0);

    // Security
    expect(screen.getByText('Unique per-device keys')).toBeInTheDocument();
    expect(screen.getByText('Zero plaintext secrets')).toBeInTheDocument();
    expect(screen.getByText('Token revocation')).toBeInTheDocument();

    // Pricing — real tiers, Naira prices, honest device allowances.
    expect(screen.getByText('PRICING')).toBeInTheDocument();
    expect(screen.getByText('₦500')).toBeInTheDocument();
    expect(screen.getByText('₦1,500')).toBeInTheDocument();
    expect(screen.getByText('Up to 3 devices')).toBeInTheDocument();
    expect(screen.getByText('Up to 10 devices')).toBeInTheDocument();
    expect(screen.getByText('BEST VALUE')).toBeInTheDocument();
    expect(screen.getByText('Custom')).toBeInTheDocument();

    // CTA + Footer
    expect(screen.getByText('I have an account')).toBeInTheDocument();
    // The docs are disabled in production (docs_url=None) — the footer must
    // not advertise dead /docs + /redoc links; System Status (/health) works.
    expect(screen.queryByText('API Docs (Swagger)')).not.toBeInTheDocument();
    expect(screen.queryByText('API Docs (ReDoc)')).not.toBeInTheDocument();
    expect(screen.getByText('System Status')).toBeInTheDocument();
    expect(screen.getAllByText('ALL SYSTEMS OPERATIONAL').length).toBeGreaterThan(0);
  });

  it('shows sign-in / signup CTAs when not authenticated', async () => {
    await renderPage();
    expect(screen.getAllByText('Sign in').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Get Started Free').length).toBeGreaterThan(0);
    expect(screen.queryByText('Launch Dashboard')).not.toBeInTheDocument();
  });

  it('shows launch-dashboard CTAs when a session exists', async () => {
    sessionStorage.setItem('mt_server_url', 'https://api.magneetar.me');
    sessionStorage.setItem('mt_api_key', 'some-key');
    await renderPage();
    // Renders in both the desktop nav and the mobile menu — findAll to avoid
    // the multiple-elements match error.
    expect((await screen.findAllByText('Launch Dashboard')).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Open Command Center').length).toBeGreaterThan(0);
    expect(screen.queryByText('Get Started Free')).not.toBeInTheDocument();
  });

  it('toggles the mobile menu', async () => {
    await renderPage();
    const toggle = screen.getByRole('button', { name: 'Toggle menu' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');

    await act(async () => {
      fireEvent.click(toggle);
    });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');

    await act(async () => {
      fireEvent.click(toggle);
    });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });
});
