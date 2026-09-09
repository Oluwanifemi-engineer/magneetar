'use client';

import Link from 'next/link';
import { ArrowRight, ShieldCheck, Download, Check } from 'lucide-react';
import { MagneticButton } from '@/components/ui/MagneticButton';
import { AuroraBackground } from '@/components/ui/AuroraBackground';

export function CTA({ authed }: { authed: boolean }) {
  return (
    <AuroraBackground className="relative py-28 sm:py-36 bg-gray-950 overflow-hidden">
      {/* Multiple glow layers */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[400px] bg-emerald-500/[0.04] rounded-full blur-[140px]" />
        <div className="absolute bottom-0 left-1/4 w-[400px] h-[200px] bg-emerald-500/[0.02] rounded-full blur-[80px]" />
      </div>

      <div className="relative max-w-5xl mx-auto px-5 sm:px-8 text-center">
        <h2 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-white leading-[1.05]">
          Never lose track of
          <br />
          <span className="bg-gradient-to-r from-gray-400 via-gray-500 to-gray-400 bg-clip-text text-transparent">
            what — or who — matters.
          </span>
        </h2>
        <p className="mt-6 text-lg text-mag-text-muted leading-relaxed max-w-xl mx-auto">
          Create your account, install the app, protect every device you own, and keep your people
          close — all within minutes.
        </p>

        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          {authed ? (
            <MagneticButton as="a" href="/dashboard" className="btn-emerald !px-8 !py-4">
              <ShieldCheck size={16} />
              Open Command Center
              <ArrowRight size={15} />
            </MagneticButton>
          ) : (
            <MagneticButton as="a" href="/signup" className="btn-emerald !px-8 !py-4">
              Get Started Free
              <ArrowRight size={15} />
            </MagneticButton>
          )}
          <MagneticButton as="a" href="/login" className="btn-ghost !px-6 !py-4">
            I have an account
          </MagneticButton>
          <MagneticButton as="a" href="/download" className="btn-ghost !px-6 !py-4">
            <Download size={15} />
            Download APK
          </MagneticButton>
        </div>

        <div className="mt-6 flex items-center justify-center gap-2">
          <Check size={14} className="text-emerald-400" />
          <span className="text-[12px] font-mono text-mag-text-muted">
            Free for 1 device · No credit card required
          </span>
        </div>
      </div>
    </AuroraBackground>
  );
}
