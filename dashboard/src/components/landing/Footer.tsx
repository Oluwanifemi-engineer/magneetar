'use client';

import Link from 'next/link';
import { Github } from 'lucide-react';
import { useLiveServerInfo, statusDotClass, type ServerStatus } from './VersionBadge';

const FOOTER_LINKS = [
  {
    title: 'Product',
    links: [
      { label: 'Features', href: '#features' },
      { label: 'How it works', href: '#how-it-works' },
      { label: 'Why Africa', href: '#africa' },
      { label: 'Our story', href: '#our-story' },
      { label: 'Security', href: '#security' },
      { label: 'Pricing', href: '#pricing' },
    ],
  },
  {
    title: 'Resources',
    links: [
      { label: 'Download APK', href: '/download' },
      { label: 'API Docs (Swagger)', href: 'https://api.magneetar.me/docs' },
      { label: 'API Docs (ReDoc)', href: 'https://api.magneetar.me/redoc' },
      { label: 'System Status', href: 'https://api.magneetar.me/health' },
      { label: 'Responsible Disclosure', href: '/.well-known/security.txt' },
    ],
  },
  {
    title: 'Legal',
    links: [
      { label: 'Privacy Policy', href: '/privacy' },
      { label: 'Terms of Service', href: '/terms' },
    ],
  },
];

export function Footer() {
  // Live version + system status from the server /health endpoint.
  const { version, status } = useLiveServerInfo();
  return (
    <footer className="relative border-t border-white/[0.06] bg-mag-panel/40">
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#E91E8C]/30 to-transparent" />
      <div className="max-w-7xl mx-auto px-5 sm:px-8 py-14">
        <div className="grid gap-10 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
          {/* Brand — magenta M tile (same mark as dashboard/login + launcher icon) */}
          <div>
            <div className="flex items-center gap-2.5">
              <img
                src="/m-logo.svg"
                alt="Magneetar"
                className="w-8 h-8 rounded-lg drop-shadow-[0_0_12px_rgba(233,30,140,0.3)]"
              />
              <div className="leading-none">
                <div className="text-white text-sm font-bold tracking-[0.25em]">MAGNEETAR</div>
                <div className="text-[8px] font-mono text-white/30 tracking-[0.3em] mt-1">TRACK · PROTECT · RECOVER</div>
              </div>
            </div>
            <p className="mt-5 text-[13px] leading-relaxed text-white/35 max-w-sm">
              Military-grade anti-theft tracking and live location circles for Android. Stealth
              monitoring, intelligent detection, and forensic-grade evidence — protecting what matters
              most, and keeping who matters close.
            </p>
            <div className="mt-6 flex items-center gap-3">
              <a
                href="https://github.com/Oluwanifemi-engineer/magneetar"
                target="_blank"
                rel="noopener noreferrer"
                className="w-9 h-9 rounded-lg border border-white/[0.08] bg-white/[0.03] flex items-center justify-center text-white/50 hover:text-white hover:border-white/20 hover:bg-white/[0.06] transition-all"
                aria-label="GitHub"
              >
                <Github size={15} />
              </a>
              <a
                href="https://api.magneetar.me/health"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-3.5 h-9 rounded-lg border border-white/[0.08] bg-white/[0.03] text-[10px] font-mono font-bold tracking-wider text-white/50 hover:text-white hover:border-white/20 hover:bg-white/[0.06] transition-all"
                title={
                  status === 'online'
                    ? `Live: api.magneetar.me reports online (v${version})`
                    : status === 'offline'
                      ? 'Live health check unreachable — see /health'
                      : 'Checking live server status…'
                }
              >
                <span className="relative flex w-1.5 h-1.5">
                  <span
                    className={`absolute inline-flex h-full w-full rounded-full opacity-60 animate-ping ${statusDotClass(status)}`}
                  />
                  <span className={`relative inline-flex rounded-full w-1.5 h-1.5 ${statusDotClass(status)}`} />
                </span>
                ALL SYSTEMS OPERATIONAL
              </a>
            </div>
          </div>

          {/* Link columns */}
          {FOOTER_LINKS.map((col) => (
            <div key={col.title}>
              <div className="text-[10px] font-mono font-bold tracking-[0.25em] text-white/40 uppercase mb-4">
                {col.title}
              </div>
              <ul className="space-y-2.5">
                {col.links.map((link) => (
                  <li key={link.label}>
                    <a
                      href={link.href}
                      target={link.href.startsWith('http') ? '_blank' : undefined}
                      rel={link.href.startsWith('http') ? 'noopener noreferrer' : undefined}
                      className="text-[13px] text-white/40 hover:text-white transition-colors"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 pt-6 border-t border-white/[0.06] flex flex-col sm:flex-row items-center justify-between gap-3">
          <span className="text-[11px] font-mono text-white/25">
            © {new Date().getFullYear()} Magneetar · BSL 1.1 (source-available)
          </span>
          <span className="text-[11px] font-mono text-white/25 tracking-wider">
            v{version} · BUILT FOR RECOVERY &amp; CONNECTION
          </span>
        </div>
      </div>
    </footer>
  );
}
