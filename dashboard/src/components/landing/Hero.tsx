'use client';

import Link from 'next/link';
import { ArrowRight, ShieldCheck, Radar, MapPin, Camera, ChevronRight, Download, Check } from 'lucide-react';
import { APK_DOWNLOAD_URL } from '@/lib/utils';

const HERO_STATS = [
  { value: '267', label: 'automated tests' },
  { value: '24/7', label: 'stealth tracking' },
  { value: 'AES-256', label: 'encrypted' },
  { value: '3-layer', label: 'background persistence' },
];

export function Hero({ authed }: { authed: boolean }) {
  return (
    <section className="relative pt-32 pb-20 sm:pt-40 sm:pb-28 overflow-hidden">
      {/* Ambient background */}
      <div className="absolute inset-0 landing-vignette pointer-events-none" />
      <div className="absolute inset-0 landing-grid opacity-60 pointer-events-none" />
      {/* Glow orbs */}
      <div className="absolute -top-32 left-1/2 -translate-x-1/2 w-[720px] h-[420px] rounded-full bg-[#E91E8C]/10 blur-[120px] pointer-events-none" />
      <div className="absolute top-40 right-[-120px] w-[400px] h-[400px] rounded-full bg-[#06B6D4]/8 blur-[100px] pointer-events-none animate-float-slow" />
      <div className="absolute top-72 left-[-140px] w-[360px] h-[360px] rounded-full bg-[#E91E8C]/6 blur-[100px] pointer-events-none animate-float-slow" style={{ animationDelay: '-3s' }} />

      <div className="relative max-w-7xl mx-auto px-5 sm:px-8 grid lg:grid-cols-2 gap-14 lg:gap-10 items-center">
        {/* ─── Copy ─────────────────────────────────────────────────────── */}
        <div>
          {/* Status badge */}
          <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-white/10 bg-white/[0.03] mb-7">
            <span className="relative flex w-2 h-2">
              <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
              <span className="relative inline-flex rounded-full w-2 h-2 bg-emerald-400" />
            </span>
            <span className="text-[11px] font-mono font-bold tracking-wider text-white/70">
              v1.3.0 · PRODUCTION READY
            </span>
          </div>

          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-display font-extrabold tracking-tight text-white leading-[1.08]">
            Protect what you own.
            <br />
            <span className="text-gradient-primary animate-gradient-x">Stay close to who you love.</span>
          </h1>

          <p className="mt-6 text-base sm:text-lg text-white/50 leading-relaxed max-w-xl">
            Magneetar is one command center for the people and things that matter — military-grade
            anti-theft protection for your devices, plus live location sharing that keeps family,
            coworkers, and teams in sync.
          </p>

          {/* CTAs */}
          <div className="mt-9 flex flex-wrap items-center gap-4">
            {authed ? (
              <Link
                href="/dashboard"
                className="group inline-flex items-center gap-2.5 px-7 py-3.5 rounded-xl text-[13px] font-bold uppercase tracking-wider bg-gradient-to-r from-[#E91E8C] to-[#06B6D4] text-white shadow-xl shadow-[#E91E8C]/25 hover:shadow-[#E91E8C]/40 hover:brightness-110 transition-all duration-200 active:scale-[0.97]"
              >
                <ShieldCheck size={16} />
                Open Command Center
                <ArrowRight size={15} className="transition-transform group-hover:translate-x-0.5" />
              </Link>
            ) : (
              <>
                <Link
                  href="/signup"
                  className="group relative inline-flex items-center gap-2.5 px-7 py-3.5 rounded-xl text-[13px] font-bold uppercase tracking-wider bg-gradient-to-r from-[#E91E8C] to-[#06B6D4] text-white shadow-xl shadow-[#E91E8C]/25 hover:shadow-[#E91E8C]/40 hover:brightness-110 transition-all duration-200 active:scale-[0.97] overflow-hidden"
                >
                  <span className="absolute inset-y-0 -left-full w-1/2 bg-white/15 blur-md animate-shimmer" />
                  Get Started Free
                  <ArrowRight size={15} className="transition-transform group-hover:translate-x-0.5" />
                </Link>
                <Link
                  href="/login"
                  className="inline-flex items-center gap-2 px-6 py-3.5 rounded-xl text-[13px] font-bold uppercase tracking-wider border border-white/12 text-white/70 hover:text-white hover:bg-white/[0.05] hover:border-white/25 transition-all duration-200"
                >
                  Sign In
                </Link>
              </>
            )}
            <a
              href={APK_DOWNLOAD_URL}
              className="inline-flex items-center gap-2 px-6 py-3.5 rounded-xl text-[13px] font-bold uppercase tracking-wider border border-emerald-400/25 text-emerald-300 hover:bg-emerald-400/[0.06] hover:border-emerald-400/40 hover:shadow-[0_0_24px_rgba(34,197,94,0.12)] transition-all duration-200 active:scale-[0.97]"
            >
              <Download size={15} />
              Download APK
            </a>
          </div>

          {/* Free plan note */}
          <div className="mt-5 flex items-center gap-2">
            <Check size={14} className="text-emerald-400" />
            <span className="text-[12px] font-mono font-semibold tracking-wide text-white/45">
              Free plan available · No credit card required
            </span>
          </div>

          {/* Stats */}
          <div className="mt-12 grid grid-cols-2 sm:grid-cols-4 gap-6 max-w-xl">
            {HERO_STATS.map((stat) => (
              <div key={stat.label}>
                <div className="text-white text-xl font-bold font-mono tabular-nums">{stat.value}</div>
                <div className="text-[10px] font-mono text-white/35 uppercase tracking-wider mt-1 font-semibold">
                  {stat.label}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ─── Live Dashboard Mockup ────────────────────────────────────── */}
        <div className="relative">
          {/* Glow behind panel */}
          <div className="absolute inset-0 bg-gradient-to-tr from-[#E91E8C]/15 via-transparent to-[#06B6D4]/15 rounded-3xl blur-2xl pointer-events-none" />

          <div className="relative rounded-2xl border border-white/10 bg-[#0d0d14]/90 backdrop-blur-xl shadow-2xl shadow-black/60 overflow-hidden">
            {/* Window chrome */}
            <div className="flex items-center gap-2 px-4 py-3 border-b border-white/[0.06] bg-white/[0.02]">
              <span className="w-2.5 h-2.5 rounded-full bg-[#FF5F57]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#FEBC2E]" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#28C840]" />
              <span className="ml-3 text-[9px] font-mono text-white/30 tracking-widest font-bold">
                MAGNEETAR — COMMAND CENTER
              </span>
            </div>

            {/* Map area */}
            <div className="relative h-56 sm:h-64 overflow-hidden">
              <div className="absolute inset-0 landing-grid opacity-80" />
              {/* Radar ping */}
              <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-16 h-16" aria-hidden="true">
                <span className="absolute inset-0 rounded-full border border-[#22C55E]/40 animate-radar-ping" />
                <span className="absolute inset-0 rounded-full border border-[#22C55E]/25 animate-radar-ping" style={{ animationDelay: '1.2s' }} />
                <span className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-3.5 h-3.5 rounded-full bg-[#22C55E] shadow-[0_0_16px_rgba(34,197,94,0.8)]" />
              </div>
              {/* Decorative route */}
              <svg className="absolute inset-0 w-full h-full" viewBox="0 0 400 220" fill="none" preserveAspectRatio="none" aria-hidden="true">
                <path
                  d="M40 180 C 120 150, 160 90, 240 110 S 360 60, 380 50"
                  stroke="url(#route-grad)"
                  strokeWidth="1.5"
                  strokeDasharray="6 6"
                  strokeLinecap="round"
                />
                <circle cx="40" cy="180" r="3" fill="#E91E8C" />
                <circle cx="380" cy="50" r="3" fill="#06B6D4" />
                <defs>
                  <linearGradient id="route-grad" x1="40" y1="180" x2="380" y2="50">
                    <stop offset="0%" stopColor="#E91E8C" />
                    <stop offset="100%" stopColor="#06B6D4" />
                  </linearGradient>
                </defs>
              </svg>
              {/* HUD chips */}
              <div className="absolute top-3 left-3 flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-black/50 border border-white/10 backdrop-blur-md">
                <Radar size={11} className="text-emerald-400" />
                <span className="text-[9px] font-mono font-bold tracking-wider text-emerald-300">LIVE</span>
              </div>
              <div className="absolute top-3 right-3 px-2.5 py-1.5 rounded-lg bg-black/50 border border-white/10 backdrop-blur-md">
                <span className="text-[9px] font-mono font-bold tracking-wider text-white/50">
                  6.5244° N, 3.3792° E
                </span>
              </div>
              <div className="absolute bottom-3 right-3 px-2.5 py-1.5 rounded-lg bg-black/50 border border-white/10 backdrop-blur-md flex items-center gap-1.5">
                <MapPin size={10} className="text-[#06B6D4]" />
                <span className="text-[9px] font-mono font-bold tracking-wider text-white/60">12 m · 38 km/h</span>
              </div>
            </div>

            {/* Bottom rows */}
            <div className="grid grid-cols-3 gap-px bg-white/[0.05] border-t border-white/[0.06]">
              <div className="bg-[#0d0d14]/95 px-4 py-3.5">
                <div className="text-[8px] font-mono text-white/30 tracking-widest font-bold mb-1.5">THREAT</div>
                <div className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(34,197,94,0.7)]" />
                  <span className="text-white text-sm font-bold font-mono">SAFE</span>
                </div>
              </div>
              <div className="bg-[#0d0d14]/95 px-4 py-3.5">
                <div className="text-[8px] font-mono text-white/30 tracking-widest font-bold mb-1.5">SENTINEL</div>
                <div className="flex items-center gap-2">
                  <span className="text-white text-sm font-bold font-mono">12</span>
                  <div className="flex-1 h-1 rounded-full bg-white/10 overflow-hidden">
                    <div className="h-full w-[12%] rounded-full bg-gradient-to-r from-[#E91E8C] to-[#06B6D4]" />
                  </div>
                </div>
              </div>
              <div className="bg-[#0d0d14]/95 px-4 py-3.5 flex items-center justify-between">
                <div>
                  <div className="text-[8px] font-mono text-white/30 tracking-widest font-bold mb-1.5">EVIDENCE</div>
                  <div className="flex items-center gap-1.5">
                    <Camera size={12} className="text-[#06B6D4]" />
                    <span className="text-white text-sm font-bold font-mono">3 files</span>
                  </div>
                </div>
                <ChevronRight size={14} className="text-white/20" />
              </div>
            </div>
          </div>

          {/* Floating chip — device online */}
          <div className="absolute -top-4 -right-3 sm:-right-6 px-3.5 py-2 rounded-xl border border-white/10 bg-[#111118]/95 backdrop-blur-xl shadow-xl shadow-black/50 animate-float-slow flex items-center gap-2">
            <span className="relative flex w-2 h-2">
              <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
              <span className="relative inline-flex rounded-full w-2 h-2 bg-emerald-400" />
            </span>
            <span className="text-[10px] font-mono font-bold text-white/70">Pixel 8 · Online</span>
          </div>

          {/* Floating chip — recovery */}
          <div className="absolute -bottom-4 -left-3 sm:-left-6 px-3.5 py-2 rounded-xl border border-white/10 bg-[#111118]/95 backdrop-blur-xl shadow-xl shadow-black/50 animate-float-slow flex items-center gap-2" style={{ animationDelay: '-2.5s' }}>
            <ShieldCheck size={12} className="text-[#06B6D4]" />
            <span className="text-[10px] font-mono font-bold text-white/70">Recovery enabled</span>
          </div>
        </div>
      </div>
    </section>
  );
}
