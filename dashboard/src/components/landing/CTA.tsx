'use client';

import Link from 'next/link';
import { ArrowRight, ShieldCheck, Download, Check } from 'lucide-react';

export function CTA({ authed }: { authed: boolean }) {
  return (
    <section className="relative py-24 sm:py-32">
      <div className="max-w-5xl mx-auto px-5 sm:px-8">
        <div className="relative premium-card overflow-hidden px-8 py-14 sm:px-16 sm:py-20 text-center">
          {/* Decorative gradient overlay */}
          <div className="absolute inset-0 bg-gradient-to-br from-[#E91E8C]/[0.08] via-transparent to-[#06B6D4]/[0.08] pointer-events-none" />
          <div className="absolute inset-0 landing-grid opacity-30 pointer-events-none" />
          <div className="absolute -top-32 left-1/2 -translate-x-1/2 w-[600px] h-[400px] rounded-full bg-[#E91E8C]/10 blur-[120px] pointer-events-none" />

          <div className="relative">
            <div className="badge-premium mb-7">
              <span className="relative flex w-2 h-2">
                <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
                <span className="relative inline-flex rounded-full w-2 h-2 bg-emerald-400" />
              </span>
              READY WHEN YOU ARE
            </div>

            <h2 className="text-3xl sm:text-5xl font-display font-extrabold tracking-tight text-white leading-tight">
              Never lose track of
              <br />
              <span className="text-gradient-primary">what — or who — matters.</span>
            </h2>
            <p className="mt-5 text-white/40 leading-relaxed max-w-xl mx-auto text-[16px]">
              Create your account, install the app, protect every device you own, and keep your people
              close — all within minutes.
            </p>

            <div className="mt-9 flex flex-wrap items-center justify-center gap-4">
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
                <Link
                  href="/signup"
                  className="btn-premium group inline-flex items-center gap-2.5 px-8 py-4 rounded-2xl text-[13px] font-bold uppercase tracking-wider text-white"
                >
                  Get Started Free
                  <ArrowRight size={15} className="transition-transform group-hover:translate-x-1" />
                </Link>
              )}
              <Link
                href="/login"
                className="glass-panel inline-flex items-center gap-2 px-7 py-4 rounded-2xl text-[13px] font-bold uppercase tracking-wider text-white/70 hover:text-white transition-all duration-300"
              >
                I have an account
              </Link>
              <Link
                href="/download"
                className="glass-panel inline-flex items-center gap-2 px-7 py-4 rounded-2xl text-[13px] font-bold uppercase tracking-wider text-[#22C55E]/80 hover:text-[#22C55E] transition-all duration-300"
              >
                <Download size={15} />
                Download APK
              </Link>
            </div>

            <div className="mt-6 flex items-center justify-center gap-2">
              <Check size={14} className="text-[#22C55E]" />
              <span className="text-[12px] font-mono font-semibold tracking-wide text-white/40">
                Free for 1 device · No credit card required
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
