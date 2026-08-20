'use client';

import Link from 'next/link';
import { ArrowRight, ShieldCheck, Download, Check } from 'lucide-react';

export function CTA({ authed }: { authed: boolean }) {
  return (
    <section className="relative py-32 sm:py-40 bg-white">
      <div className="max-w-5xl mx-auto px-5 sm:px-8 text-center">
        <h2 className="text-4xl sm:text-5xl lg:text-6xl font-display font-extrabold tracking-tight text-gray-900 leading-[1.05]">
          Never lose track of
          <br />
          <span className="text-gray-400">what — or who — matters.</span>
        </h2>
        <p className="mt-6 text-lg text-gray-500 leading-relaxed max-w-xl mx-auto">
          Create your account, install the app, protect every device you own, and keep your people
          close — all within minutes.
        </p>

        <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
          {authed ? (
            <Link href="/dashboard" className="inline-flex items-center gap-2.5 px-8 py-4 rounded-2xl text-[13px] font-bold uppercase tracking-wider bg-gray-900 text-white shadow-lg shadow-gray-900/10 hover:bg-gray-800 transition-all duration-200">
              <ShieldCheck size={16} />
              Open Command Center
              <ArrowRight size={15} />
            </Link>
          ) : (
            <Link href="/signup" className="inline-flex items-center gap-2.5 px-8 py-4 rounded-2xl text-[13px] font-bold uppercase tracking-wider bg-gray-900 text-white shadow-lg shadow-gray-900/10 hover:bg-gray-800 transition-all duration-200">
              Get Started Free
              <ArrowRight size={15} />
            </Link>
          )}
          <Link href="/login" className="inline-flex items-center gap-2 px-7 py-4 rounded-2xl text-[13px] font-bold uppercase tracking-wider border border-gray-200 text-gray-600 hover:bg-gray-50 hover:border-gray-300 hover:text-gray-900 transition-all duration-200">
            I have an account
          </Link>
          <Link href="/download" className="inline-flex items-center gap-2 px-7 py-4 rounded-2xl text-[13px] font-bold uppercase tracking-wider border border-gray-200 text-gray-400 hover:bg-gray-50 hover:border-gray-300 hover:text-gray-900 transition-all duration-200">
            <Download size={15} />
            Download APK
          </Link>
        </div>

        <div className="mt-6 flex items-center justify-center gap-2">
          <Check size={14} className="text-gray-400" />
          <span className="text-[12px] font-mono font-medium tracking-wide text-gray-400">
            Free for 1 device · No credit card required
          </span>
        </div>
      </div>
    </section>
  );
}
