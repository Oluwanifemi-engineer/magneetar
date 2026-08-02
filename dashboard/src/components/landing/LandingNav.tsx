'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Menu, X, ArrowRight, ShieldCheck, Download } from 'lucide-react';
import { cn, APK_DOWNLOAD_URL } from '@/lib/utils';

const NAV_LINKS = [
  { href: '#features', label: 'Features' },
  { href: '#how-it-works', label: 'How it works' },
  { href: '#africa', label: 'For Africa' },
  { href: '#our-story', label: 'Our story' },
  { href: '#security', label: 'Security' },
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
          ? 'bg-mag-bg/80 backdrop-blur-xl border-b border-mag-border/40 shadow-lg shadow-black/20'
          : 'bg-transparent border-b border-transparent'
      )}
    >
      <nav className="max-w-7xl mx-auto px-5 sm:px-8 h-16 flex items-center justify-between gap-4">
        {/* Brand */}
        <Link href="/" className="flex items-center gap-2.5 group shrink-0">
          <div className="relative w-8 h-8 rounded-lg border border-white/10 bg-white/[0.03] flex items-center justify-center overflow-hidden">
            <svg viewBox="0 0 120 120" className="w-[18px] h-[18px]" fill="none" aria-label="Magneetar logo">
              <path
                d="M24 88L24 32L48 60L60 44L72 60L96 32L96 88"
                stroke="url(#nav-grad)"
                strokeWidth="6"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <defs>
                <linearGradient id="nav-grad" x1="24" y1="32" x2="96" y2="88">
                  <stop offset="0%" stopColor="#E91E8C" />
                  <stop offset="100%" stopColor="#06B6D4" />
                </linearGradient>
              </defs>
            </svg>
          </div>
          <div className="leading-none">
            <div className="text-white text-sm font-bold tracking-[0.25em]">MAGNEETAR</div>
            <div className="text-[8px] font-mono text-white/30 tracking-[0.3em] mt-1">TRACK · PROTECT · RECOVER</div>
          </div>
        </Link>

        {/* Desktop links */}
        <div className="hidden md:flex items-center gap-1">
          {NAV_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="px-4 py-2 text-[12px] font-semibold text-white/50 hover:text-white transition-colors rounded-lg hover:bg-white/[0.03]"
            >
              {link.label}
            </a>
          ))}
        </div>

        {/* Desktop CTAs */}
        <div className="hidden md:flex items-center gap-3">
          <a
            href={APK_DOWNLOAD_URL}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-[12px] font-bold uppercase tracking-wider border border-emerald-400/25 text-emerald-300 hover:bg-emerald-400/[0.06] hover:border-emerald-400/40 hover:shadow-[0_0_20px_rgba(34,197,94,0.12)] transition-all duration-200 active:scale-[0.97]"
          >
            <Download size={13} />
            Download APK
          </a>
          {authed ? (
            <Link
              href="/dashboard"
              className="group inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-[12px] font-bold uppercase tracking-wider bg-gradient-to-r from-[#E91E8C] to-[#06B6D4] text-white shadow-lg shadow-[#E91E8C]/20 hover:shadow-[#E91E8C]/40 hover:brightness-110 transition-all duration-200 active:scale-[0.97]"
            >
              <ShieldCheck size={14} />
              Launch Dashboard
            </Link>
          ) : (
            <>
              <Link
                href="/login"
                className="px-4 py-2.5 text-[12px] font-semibold text-white/60 hover:text-white transition-colors rounded-xl hover:bg-white/[0.04]"
              >
                Sign in
              </Link>
              <Link
                href="/signup"
                className="group inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-[12px] font-bold uppercase tracking-wider bg-gradient-to-r from-[#E91E8C] to-[#06B6D4] text-white shadow-lg shadow-[#E91E8C]/20 hover:shadow-[#E91E8C]/40 hover:brightness-110 transition-all duration-200 active:scale-[0.97]"
              >
                Get Started
                <ArrowRight size={14} className="transition-transform group-hover:translate-x-0.5" />
              </Link>
            </>
          )}
        </div>

        {/* Mobile toggle */}
        <button
          onClick={() => setOpen(!open)}
          className="md:hidden w-10 h-10 rounded-lg border border-white/10 bg-white/[0.03] flex items-center justify-center text-white/70 hover:text-white transition-colors"
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
          'md:hidden overflow-hidden transition-all duration-300 bg-mag-bg/95 backdrop-blur-xl border-b border-mag-border/40',
          open ? 'max-h-[520px]' : 'max-h-0 border-b-0'
        )}
      >
        <div className="px-6 py-4 space-y-1">
          {NAV_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              onClick={() => setOpen(false)}
              className="block px-3 py-2.5 rounded-lg text-sm font-semibold text-white/60 hover:text-white hover:bg-white/[0.04] transition-colors"
            >
              {link.label}
            </a>
          ))}
          <div className="pt-3 pb-2 flex flex-col gap-2">
            <a
              href={APK_DOWNLOAD_URL}
              onClick={() => setOpen(false)}
              className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-[12px] font-bold uppercase tracking-wider border border-emerald-400/25 text-emerald-300 hover:bg-emerald-400/[0.06] hover:border-emerald-400/40 transition-colors"
            >
              <Download size={14} /> Download APK
            </a>
            {authed ? (
              <Link
                href="/dashboard"
                onClick={() => setOpen(false)}
                className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-[12px] font-bold uppercase tracking-wider bg-gradient-to-r from-[#E91E8C] to-[#06B6D4] text-white"
              >
                <ShieldCheck size={14} /> Launch Dashboard
              </Link>
            ) : (
              <>
                <Link
                  href="/login"
                  onClick={() => setOpen(false)}
                  className="inline-flex items-center justify-center px-5 py-3 rounded-xl text-[12px] font-bold uppercase tracking-wider border border-white/10 text-white/70 hover:text-white hover:bg-white/[0.04] transition-colors"
                >
                  Sign in
                </Link>
                <Link
                  href="/signup"
                  onClick={() => setOpen(false)}
                  className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl text-[12px] font-bold uppercase tracking-wider bg-gradient-to-r from-[#E91E8C] to-[#06B6D4] text-white"
                >
                  Get Started <ArrowRight size={14} />
                </Link>
              </>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
