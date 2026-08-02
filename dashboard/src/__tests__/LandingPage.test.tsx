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

    // Hero
    expect(screen.getByText('Protect what you own.')).toBeInTheDocument();
    expect(screen.getByText('Stay close to who you love.')).toBeInTheDocument();
    expect(screen.getByText('24/7')).toBeInTheDocument();

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

    // Built at OAU (provenance / social proof)
    expect(screen.getByText('OUR STORY')).toBeInTheDocument();
    expect(screen.getByText('Born at Great Ife')).toBeInTheDocument();
    expect(screen.getByText('Nigeria’s first Faculty of Technology')).toBeInTheDocument();
    expect(screen.getByText('Ranked #5 in Nigeria')).toBeInTheDocument();

    // Download APK + free-plan messaging (nav, hero, CTA)
    const apkLinks = screen.getAllByRole('link', { name: /download apk/i });
    expect(apkLinks.length).toBeGreaterThan(0);
    apkLinks.forEach((link) => {
      expect(link).toHaveAttribute('href', 'https://api.magneetar.me/apk/download');
    });
    expect(screen.getAllByText('Free plan available · No credit card required').length).toBeGreaterThan(0);

    // Security
    expect(screen.getByText('Unique per-device keys')).toBeInTheDocument();
    expect(screen.getByText('Zero plaintext secrets')).toBeInTheDocument();
    expect(screen.getByText('Token revocation')).toBeInTheDocument();

    // CTA + Footer
    expect(screen.getByText('I have an account')).toBeInTheDocument();
    expect(screen.getByText('API Docs (Swagger)')).toBeInTheDocument();
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
