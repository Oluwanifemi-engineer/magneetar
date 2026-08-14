'use client';

import Link from 'next/link';
import { ArrowRight, ShieldCheck, Radar, MapPin, Camera, ChevronRight, Download, Check } from 'lucide-react';
import { VersionBadge } from './VersionBadge';
import { AnimatedCounter } from '@/components/ui/AnimatedCounter';
import { PRODUCT_STATS } from '@/lib/productStats';

// Stats with numeric values for animation. The first three are single-sourced
// from PRODUCT_STATS (so the hero and login page can never diverge); the 4th
// (3-layer background persistence) is hero-only.
const HERO_STATS: { value: number; label: string; prefix?: string; suffix?: string }[] = [
  ...PRODUCT_STATS.map((s) => ({ value: s.value, label: s.label, prefix: s.prefix, suffix: s.suffix })),
  { value: 3, label: 'background persistence', suffix: '-layer' },
];

export function Hero({ authed }: { authed: boolean }) {
  return (
    <section className="relative pt-32 pb-20 sm:pt-40 sm:pb-28 overflow-hidden">
      {/* Ambient background */}
      <div className="absolute inset-0 landing-vignette pointer-events-none" />
      <div className="absolute inset-0 landing-grid opacity-60 pointer-events-none" />
      {/* Glow orbs — aqua/teal */}
      <div className="absolute -top-32 left-1/2 -translate-x-1/2 w-[720px] h-[420px] rounded-full bg-mag-primary/10 blur-[120px] pointer-events-none" />
      <div className="absolute top-40 right-[-120px] w-[400px] h-[400px] rounded-full bg-mag-secondary/8 blur-[100px] pointer-events-none animate-float-slow" />
      <div className="absolute top-72 left-[-140px] w-[360px] h-[360px] rounded-full bg-mag-primary/6 blur-[100px] pointer-events-none animate-float-slow" style={{ animationDelay: '-3s' }} />

      <div className="relative max-w-7xl mx-auto px-5 sm:px-8 grid lg:grid-cols-2 gap-14 lg:gap-10 items-center">
        {/* ─── Copy ─────────────────────────────────────────────────────── */}
        <div>
          {/* Status badge — version is fetched LIVE from the server /health,
              with a build-time fallback, so it can never show a stale release */}
          <VersionBadge />

          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-display font-extrabold tracking-tight text-white leading-[1.08]">
            Protect what you own.
            <br />
            <span className="text-gradient-primary animate-gradient-x">Stay close to who you love.</span>
          </h1>

          <p className="mt-6 text-base sm:text-lg text-white/70 leading-relaxed max-w-xl">
            In Nigeria, only 11.7% of stolen phones are ever recovered. Magneetar is built to change
            that number — real-time tracking, a route that walks you to your device, and forensic-grade
            evidence. While it keeps you safe, it keeps the people you love within reach.
          </p>

          {/* CTAs */}
          <div className="mt-9 flex flex-wrap items-center gap-4">
            {authed ? (
              <Link
                href="/dashboard"
                className="btn-premium group inline-flex items-center gap-2.5 px-8 py-4 rounded-2xl text-[13px] font-bold uppercase tracking-wider text-white"
              >
                <ShieldCheck size={16} />
                Open Command Center
                <ArrowRight size={15} className="transition-transform group-hover:translate-x-1" />
              </Link>
            ) : (
              <>
                <Link
                  href="/signup"
                  className="btn-premium group inline-flex items-center gap-2.5 px-8 py-4 rounded-2xl text-[13px] font-bold uppercase tracking-wider text-white"
                >
                  Get Started Free
                  <ArrowRight size={15} className="transition-transform group-hover:translate-x-1" />
                </Link>
                <Link
                  href="/login"
                  className="glass-panel inline-flex items-center gap-2 px-7 py-4 rounded-2xl text-[13px] font-bold uppercase tracking-wider text-white/80 hover:text-white transition-all duration-300"
                >
                  Sign In
                </Link>
              </>
            )}
            <Link
              href="/download"
              className="glass-panel inline-flex items-center gap-2 px-7 py-4 rounded-2xl text-[13px] font-bold uppercase tracking-wider text-emerald-400 hover:text-emerald-300 hover:border-emerald-400/30 transition-all duration-300"
            >
              <Download size={15} />
              Download APK
            </Link>
          </div>

          {/* Free plan note */}
          <div className="mt-5 flex items-center gap-2">
            <Check size={14} className="text-emerald-400" />
            <span className="text-[12px] font-mono font-semibold tracking-wide text-white/60">
              Free for 1 device · No credit card required
            </span>
          </div>

          {/* Animated Stats */}
          <div className="mt-12 grid grid-cols-2 sm:grid-cols-4 gap-6 max-w-xl">
            {HERO_STATS.map((stat) => (
              <div key={stat.label}>
                <div className="text-white text-xl font-bold font-mono">
                  <AnimatedCounter
                    value={stat.value}
                    prefix={stat.prefix}
                    suffix={stat.suffix}
                    className="text-xl"
                  />
                </div>
                <div className="text-[10px] font-mono text-white/50 uppercase tracking-wider mt-1 font-semibold">
                  {stat.label}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ─── Live Dashboard Mockup ────────────────────────────────────── */}
        <div className="relative">
          {/* Glow behind panel — aqua */}
          <div className="absolute inset-0 bg-gradient-to-tr from-mag-primary/15 via-transparent to-mag-secondary/15 rounded-3xl blur-3xl pointer-events-none" />

          <div className="relative rounded-2xl glass-panel overflow-hidden">
            {/* Window chrome */}
            <div className="flex items-center gap-2 px-4 py-3 border-b border-white/[0.06] bg-white/[0.02]">
              <span className="w-2.5 h-2.5 rounded-full bg-[#FF5F57]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#FEBC2E]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#28C840]" />
              <span className="ml-3 text-[9px] font-mono text-white/50 tracking-widest font-bold">
                MAGNEETAR — COMMAND CENTER
              </span>
            </div>

            {/* Map area */}
            <div className="relative h-56 sm:h-64 overflow-hidden">
              <div className="absolute inset-0 landing-grid opacity-80" />
              {/* Radar ping — aqua */}
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-16 h-16" aria-hidden="true">
                <span className="absolute inset-0 rounded-full border border-mag-accent/40 animate-radar-ping" />
                <span className="absolute inset-0 rounded-full border border-mag-accent/25 animate-radar-ping" style={{ animationDelay: '1.2s' }} />
                <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-3.5 h-3.5 rounded-full bg-mag-accent shadow-[0_0_16px_rgba(16,185,129,0.8)]" />
              </div>
              {/* Decorative route — aqua gradient */}
              <svg className="absolute inset-0 w-full h-full" viewBox="0 0 400 220" fill="none" preserveAspectRatio="none" aria-hidden="true">
                <path
                  d="M40 180 C 120 150, 160 90, 240 110 S 360 60, 380 50"
                  stroke="url(#route-grad)"
                  strokeWidth="1.5"
                  strokeDasharray="6 6"
                  strokeLinecap="round"
                />
                <circle cx="40" cy="180" r="3" fill="#06B6D4" />
                <circle cx="380" cy="50" r="3" fill="#14B8A6" />
                <defs>
                  <linearGradient id="route-grad" x1="40" y1="180" x2="380" y2="50">
                    <stop offset="0%" stopColor="#06B6D4" />
                    <stop offset="100%" stopColor="#14B8A6" />
                  </linearGradient>
                </defs>
              </svg>
              {/* HUD chips */}
              <div className="absolute top-3 left-3 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-black/50 border border-white/10 backdrop-blur-md">
                <Radar size={11} className="text-amber-300" />
                <span className="text-[9px] font-mono font-bold tracking-wider text-amber-200">DEMO</span>
              </div>
              <div className="absolute top-3 right-3 px-2.5 py-1.5 rounded-lg bg-black/50 border border-white/10 backdrop-blur-md">
                <span className="text-[9px] font-mono font-bold tracking-wider text-white/70">
                  6.5244° N, 3.3792° E
                </span>
              </div>
              <div className="absolute bottom-3 right-3 px-2.5 py-1.5 rounded-lg bg-black/50 border border-white/10 backdrop-blur-md flex items-center gap-1.5">
                <MapPin size={10} className="text-mag-primary" />
                <span className="text-[9px] font-mono font-bold tracking-wider text-white/80">12 m · 38 km/h</span>
              </div>
            </div>

            {/* Bottom rows — aqua accents */}
            <div className="grid grid-cols-3 gap-px bg-white/[0.05] border-t border-white/[0.06]">
              <div className="bg-mag-panel/95 px-4 py-3.5">
                <div className="text-[8px] font-mono text-white/50 tracking-widest font-bold mb-1.5">THREAT</div>
                <div className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.7)]" />
                  <span className="text-white text-sm font-bold font-mono">SAFE</span>
                </div>
              </div>
              <div className="bg-mag-panel/95 px-4 py-3.5">
                <div className="text-[8px] font-mono text-white/50 tracking-widest font-bold mb-1.5">SENTINEL</div>
                <div className="flex items-center gap-2">
                  <span className="text-white text-sm font-bold font-mono">12</span>
                  <div className="flex-1 h-1 rounded-full bg-white/10 overflow-hidden">
                    <div className="h-full w-[12%] rounded-full bg-gradient-to-r from-mag-primary to-mag-secondary" />
                  </div>
                </div>
              </div>
              <div className="bg-mag-panel/95 px-4 py-3.5 flex items-center justify-between">
                <div>
                  <div className="text-[8px] font-mono text-white/50 tracking-widest font-bold mb-1.5">EVIDENCE</div>
                  <div className="flex items-center gap-1.5">
                    <Camera size={12} className="text-mag-secondary" />
                    <span className="text-white text-sm font-bold font-mono">3 files</span>
                  </div>
                </div>
                <ChevronRight size={14} className="text-white/30" />
              </div>
            </div>
          </div>

          {/* Floating chip — device online */}
          <div className="absolute -top-4 -right-3 sm:-right-6 px-3.5 py-2 rounded-xl border border-white/10 bg-mag-panel/95 backdrop-blur-xl shadow-xl shadow-black/50 animate-float-slow flex items-center gap-2">
            <span className="relative flex w-2 h-2">
              <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
              <span className="relative inline-flex rounded-full w-2 h-2 bg-emerald-400" />
            </span>
            <span className="text-[10px] font-mono font-bold text-white/80">Pixel 8 · Demo device</span>
          </div>

          {/* Floating chip — recovery */}
          <div className="absolute -bottom-4 -left-3 sm:-left-6 px-3.5 py-2 rounded-xl border border-white/10 bg-mag-panel/95 backdrop-blur-xl shadow-xl shadow-black/50 animate-float-slow flex items-center gap-2" style={{ animationDelay: '-2.5s' }}>
            <ShieldCheck size={12} className="text-mag-primary" />
            <span className="text-[10px] font-mono font-bold text-white/80">Recovery enabled</span>
          </div>
        </div>
      </div>
    </section>
  );
}
