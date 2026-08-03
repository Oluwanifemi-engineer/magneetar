'use client';

import Link from 'next/link';
import { ArrowRight, ShieldCheck, Download, Check } from 'lucide-react';

export function CTA({ authed }: { authed: boolean }) {
  return (
    <section className="relative py-24 sm:py-32">
      <div className="max-w-5xl mx-auto px-5 sm:px-8">
        <div className="relative rounded-3xl border border-white/[0.08] bg-gradient-to-br from-[#E91E8C]/15 via-[#0d0d14] to-[#06B6D4]/10 overflow-hidden px-8 py-14 sm:px-16 sm:py-20 text-center">
          {/* Decorative grid */}
          <div className="absolute inset-0 landing-grid opacity-40 pointer-events-none" />
          <div className="absolute -top-24 left-1/2 -translate-x-1/2 w-[560px] h-[300px] rounded-full bg-[#E91E8C]/10 blur-[100px] pointer-events-none" />

          <div className="relative">
            <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-white/10 bg-white/[0.04] mb-7">
              <span className="relative flex w-2 h-2">
                <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
                <span className="relative inline-flex rounded-full w-2 h-2 bg-emerald-400" />
              </span>
              <span className="text-[11px] font-mono font-bold tracking-wider text-white/70">
                READY WHEN YOU ARE
              </span>
            </div>

            <h2 className="text-3xl sm:text-5xl font-display font-extrabold tracking-tight text-white leading-tight">
              Never lose track of
              <br />
              what — or who — matters.
            </h2>
            <p className="mt-5 text-white/45 leading-relaxed max-w-xl mx-auto">
              Create your account, install the app, protect every device you own, and keep your people
              close — all within minutes.
            </p>

            <div className="mt-9 flex flex-wrap items-center justify-center gap-4">
              {authed ? (
                <Link
                  href="/dashboard"
                  className="group inline-flex items-center gap-2.5 px-8 py-4 rounded-xl text-[13px] font-bold uppercase tracking-wider bg-gradient-to-r from-[#E91E8C] to-[#06B6D4] text-white shadow-xl shadow-[#E91E8C]/25 hover:shadow-[#E91E8C]/40 hover:brightness-110 transition-all duration-200 active:scale-[0.97]"
                >
                  <ShieldCheck size={16} />
                  Open Command Center
                  <ArrowRight size={15} className="transition-transform group-hover:translate-x-0.5" />
                </Link>
              ) : (
                <Link
                  href="/signup"
                  className="group inline-flex items-center gap-2.5 px-8 py-4 rounded-xl text-[13px] font-bold uppercase tracking-wider bg-gradient-to-r from-[#E91E8C] to-[#06B6D4] text-white shadow-xl shadow-[#E91E8C]/25 hover:shadow-[#E91E8C]/40 hover:brightness-110 transition-all duration-200 active:scale-[0.97]"
                >
                  Get Started Free
                  <ArrowRight size={15} className="transition-transform group-hover:translate-x-0.5" />
                </Link>
              )}
              <Link
                href="/login"
                className="inline-flex items-center gap-2 px-7 py-4 rounded-xl text-[13px] font-bold uppercase tracking-wider border border-white/12 text-white/70 hover:text-white hover:bg-white/[0.05] hover:border-white/25 transition-all duration-200"
              >
                I have an account
              </Link>
              <Link
                href="/download"
                className="inline-flex items-center gap-2 px-7 py-4 rounded-xl text-[13px] font-bold uppercase tracking-wider border border-emerald-400/25 text-emerald-300 hover:bg-emerald-400/[0.06] hover:border-emerald-400/40 hover:shadow-[0_0_24px_rgba(34,197,94,0.12)] transition-all duration-200 active:scale-[0.97]"
              >
                <Download size={15} />
                Download APK
              </Link>
            </div>

            <div className="mt-6 flex items-center justify-center gap-2">
              <Check size={14} className="text-emerald-400" />
              <span className="text-[12px] font-mono font-semibold tracking-wide text-white/45">
                Free for 1 device · From ₦500/mo to protect more
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
