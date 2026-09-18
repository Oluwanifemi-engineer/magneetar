'use client';

import { Heart, MapPin, Shield, GraduationCap } from 'lucide-react';

export function OurStory() {
  return (
    <section className="relative py-28 sm:py-36 overflow-hidden bg-gray-950">
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[400px] bg-emerald-500/[0.02] rounded-full blur-[120px] pointer-events-none" />

      <div className="relative max-w-4xl mx-auto px-5 sm:px-8 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-emerald-500/20 bg-emerald-500/5 mb-8">
          <Heart size={10} className="text-emerald-400" />
          <span className="text-[11px] font-mono font-bold tracking-[0.2em] text-emerald-400/80">OUR STORY</span>
        </div>

        <h2 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold tracking-tight text-white leading-tight">
          We built this because
          <br />
          <span className="text-mag-text-muted">existing solutions failed us.</span>
        </h2>

        <div className="mt-10 max-w-2xl mx-auto space-y-5 text-left">
          <p className="text-[15px] leading-relaxed text-mag-text-muted">
            At universities across Nigeria and Africa, your phone is how you stay connected to
            family. When it gets stolen, you learn fast that Google Find My Device does not work
            reliably on most Android phones. Recovery agents charge tens of thousands of naira
            with no guarantee.
          </p>

          <p className="text-[15px] leading-relaxed text-mag-text-muted">
            We built Magneetar to fix that. A phone tracker that works on the phones students
            actually use, on the networks we actually have, and survives the real-world conditions
            where other trackers fail.
          </p>

          <p className="text-[15px] leading-relaxed text-mag-text font-medium">
            Free for your first device. Because everyone deserves to stay connected.
          </p>
        </div>

        <div className="mt-14 grid sm:grid-cols-3 gap-6 max-w-3xl mx-auto">
          <div className="flex flex-col items-center text-center">
            <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mb-4">
              <GraduationCap size={20} className="text-emerald-400/70" />
            </div>
            <div className="text-white font-semibold text-sm">Built by students</div>
            <div className="text-[12px] text-mag-text-muted mt-1 leading-relaxed">
              We live the problem. We built the solution.
            </div>
          </div>

          <div className="flex flex-col items-center text-center">
            <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mb-4">
              <Shield size={20} className="text-emerald-400/70" />
            </div>
            <div className="text-white font-semibold text-sm">Built for real failure</div>
            <div className="text-[12px] text-mag-text-muted mt-1 leading-relaxed">
              Offline, battery saving, SIM change — designed to keep working where others do not.
            </div>
          </div>

          <div className="flex flex-col items-center text-center">
            <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mb-4">
              <Heart size={20} className="text-emerald-400/70" />
            </div>
            <div className="text-white font-semibold text-sm">Free to start</div>
            <div className="text-[12px] text-mag-text-muted mt-1 leading-relaxed">
              Protect your phone at no cost. Upgrade when you are ready.
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
