'use client';

import Link from 'next/link';
import { FileArchive } from 'lucide-react';
import { useLiveServerInfo, statusDotClass } from './VersionBadge';
import { SOURCE_TARBALL_URL } from '@/lib/utils';

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
  const { version, status } = useLiveServerInfo();
  return (
    <footer className="relative border-t border-gray-200 bg-gray-50">
      <div className="max-w-7xl mx-auto px-5 sm:px-8 py-14">
        <div className="grid gap-10 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div>
            <div className="flex items-center gap-2.5">
              <img
                src="/magneetar-mhalf.svg"
                alt="Magneetar"
                className="w-9 h-9 rounded-lg"
              />
              <div className="leading-none">
                <div className="text-gray-900 text-sm font-bold tracking-[0.25em]">MAGNEETAR</div>
                <div className="text-[8px] font-mono text-gray-400 tracking-[0.3em] mt-1">TRACK · PROTECT · RECOVER</div>
              </div>
            </div>
            <p className="mt-5 text-[13px] leading-relaxed text-gray-500 max-w-sm">
              Military-grade anti-theft tracking and live location circles for Android. Stealth
              monitoring, intelligent detection, and forensic-grade evidence — protecting what matters
              most, and keeping who matters close.
            </p>
            <div className="mt-6 flex items-center gap-3">
              <a
                href={SOURCE_TARBALL_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="w-9 h-9 rounded-lg border border-gray-200 bg-white flex items-center justify-center text-gray-500 hover:text-gray-900 hover:border-gray-300 transition-all"
                aria-label="Source code"
              >
                <FileArchive size={15} />
              </a>
              <a
                href="https://api.magneetar.me/health"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-3.5 h-9 rounded-lg border border-gray-200 bg-white text-[10px] font-mono font-bold tracking-wider text-gray-500 hover:text-gray-900 hover:border-gray-300 transition-all"
                title={`Live: api.magneetar.me reports ${status}`}
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

          {FOOTER_LINKS.map((col) => (
            <div key={col.title}>
              <div className="text-[10px] font-mono font-bold tracking-[0.25em] text-gray-400 uppercase mb-4">
                {col.title}
              </div>
              <ul className="space-y-2.5">
                {col.links.map((link) => (
                  <li key={link.label}>
                    <a
                      href={link.href}
                      target={link.href.startsWith('http') ? '_blank' : undefined}
                      rel={link.href.startsWith('http') ? 'noopener noreferrer' : undefined}
                      className="text-[13px] text-gray-500 hover:text-gray-900 transition-colors"
                    >
                      {link.label}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-12 pt-6 border-t border-gray-200 flex flex-col sm:flex-row items-center justify-between gap-3">
          <span className="text-[11px] font-mono text-gray-400">
            © {new Date().getFullYear()} Magneetar · BSL 1.1 (source-available)
          </span>
          <span className="text-[11px] font-mono text-gray-400 tracking-wider">
            v{version} · BUILT FOR RECOVERY &amp; CONNECTION
          </span>
        </div>
      </div>
    </footer>
  );
}
