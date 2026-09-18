'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Menu, X, ArrowRight, Download } from 'lucide-react';
import { cn } from '@/lib/utils';

const NAV_LINKS = [
  { href: '#features', label: 'Features' },
  { href: '#security', label: 'Security' },
  { href: '#pricing', label: 'Pricing' },
];

export function LandingNav({ authed }: { authed: boolean }) {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <header
      className={cn(
        'fixed top-0 inset-x-0 z-50 transition-all duration-300',
        scrolled
          ? 'bg-mag-bg/90 backdrop-blur-xl border-b border-mag-border shadow-sm shadow-black/20'
          : 'bg-transparent border-b border-transparent'
      )}
    >
      <nav className="max-w-7xl mx-auto px-5 sm:px-8 h-16 flex items-center justify-between gap-4">
        {/* Brand */}
        <Link href="/" className="flex items-center gap-2.5 group shrink-0">
          <img
            src="/magneetar-mhalf.svg"
            alt="Magneetar"
            className="w-9 h-9 rounded-lg transition-all duration-300 group-hover:scale-110"
          />
          <div className="leading-none">
            <div className="text-mag-text text-sm font-bold tracking-[0.25em]">MAGNEETAR</div>
            <div className="text-[11px] font-mono text-mag-text-muted tracking-[0.3em] mt-1">TRACK · PROTECT · RECOVER</div>
          </div>
        </Link>

        {/* Desktop links */}
        <div className="hidden md:flex items-center gap-1">
          {NAV_LINKS.map((link) => (              <a
              key={link.href}
              href={link.href}
              className="nav-link-hover px-4 py-2 text-[12px] font-semibold text-mag-text-muted hover:text-mag-text transition-colors"
            >
              {link.label}
            </a>
          ))}
        </div>

        {/* Desktop CTAs */}
        <div className="hidden md:flex items-center gap-3">
          <Link
            href="/download"
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-[12px] font-bold uppercase tracking-wider border-mag-border/50 text-mag-text-muted hover:bg-mag-surface hover:border-mag-border hover:text-mag-text transition-all duration-200 active:scale-[0.97]"
          >
            <Download size={13} />
            Download APK
          </Link>
          {authed ? (
            <Link
              href="/dashboard"
              className="group inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-[12px] font-bold uppercase tracking-wider bg-emerald-500 text-white shadow-lg shadow-emerald-500/20 hover:bg-emerald-400 hover:shadow-emerald-500/30 transition-all duration-200 active:scale-[0.97]"
            >
              Launch Dashboard
              <ArrowRight size={13} className="transition-transform group-hover:translate-x-0.5" />
            </Link>
          ) : (
            <>
              <Link
                href="/login"
                className="px-4 py-2.5 text-[12px] font-semibold text-mag-text-muted hover:text-mag-text transition-colors rounded-xl hover:bg-mag-surface"
              >
                Sign in
              </Link>
              <Link
                href="/signup"
                className="group inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-[12px] font-bold uppercase tracking-wider bg-emerald-500 text-white shadow-lg shadow-emerald-500/20 hover:bg-emerald-400 hover:shadow-emerald-500/30 transition-all duration-200 active:scale-[0.97]"
              >
                Get Started
                <ArrowRight size={13} className="transition-transform group-hover:translate-x-0.5" />
              </Link>
            </>
          )}
        </div>

        {/* Mobile toggle */}
        <button
          onClick={() => setOpen(!open)}
          className="md:hidden w-10 h-10 rounded-lg border-mag-border bg-mag-surface text-mag-text-muted hover:text-mag-text hover:bg-mag-surface-raised transition-colors"
          aria-label="Toggle menu"
          aria-expanded={open}
          aria-controls="mobile-menu"
        >
          {open ? <X size={18} /> : <Menu size={18} />}
        </button>
      </nav>

      {/* Mobile menu */}
      <div
        id="mobile-menu"
        className={cn(
          'md:hidden overflow-hidden transition-all duration-300 bg-mag-bg/95 backdrop-blur-xl border-b border-mag-border',
          open ? 'max-h-[520px]' : 'max-h-0 border-b-0'
        )}
      >
        <div className="px-6 py-4 space-y-1">
          {NAV_LINKS.map((link) => (              <a
              key={link.href}
              href={link.href}
              onClick={() => setOpen(false)}
              className="block px-3 py-2.5 rounded-lg text-sm font-semibold text-mag-text-muted hover:text-mag-text hover:bg-mag-surface transition-colors"
            >
              {link.label}
            </a>
          ))}
          <div className="pt-3 pb-2 flex flex-col gap-2">              <Link
              href="/download"
              onClick={() => setOpen(false)}
              className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-[12px] font-bold uppercase tracking-wider border-mag-border/50 text-mag-text-muted hover:bg-mag-surface hover:border-mag-border transition-colors"
            >
              <Download size={14} /> Download APK
            </Link>
            {authed ? (
              <Link
                href="/dashboard"
                onClick={() => setOpen(false)}
                className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-[12px] font-bold uppercase tracking-wider bg-emerald-500 text-white"
              >
                Launch Dashboard <ArrowRight size={13} />
              </Link>
            ) : (
              <>
                <Link
                  href="/login"
                  onClick={() => setOpen(false)}
                  className="inline-flex items-center justify-center px-5 py-3 rounded-xl text-[12px] font-bold uppercase tracking-wider border-mag-border/50 text-mag-text-muted hover:text-mag-text hover:bg-mag-surface transition-colors"
                >
                  Sign in
                </Link>
                <Link
                  href="/signup"
                  onClick={() => setOpen(false)}
                  className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-[12px] font-bold uppercase tracking-wider bg-emerald-500 text-white"
                >
                  Get Started <ArrowRight size={13} />
                </Link>
              </>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
