'use client';

import { Compass, Users, Rocket } from 'lucide-react';

const ORIGIN_POINTS = [
  {
    icon: Compass,
    title: 'Started with real problems',
    description:
      'Built by students who had lived them firsthand — phone theft and staying in touch with the people who matter are everyday realities no boardroom brief can capture.',
  },
  {
    icon: Users,
    title: 'Protection + connection',
    description:
      'Two equal promises from day one: keep what you own safe, and keep the people you love within reach — for families, coworkers, and teams alike.',
  },
  {
    icon: Rocket,
    title: 'Built to grow beyond any campus',
    description:
      'Magneetar is designed to scale past its first campus and its first country — the platform, not the place, is the story.',
  },
];

export function Provenance() {
  return (
    <section id="our-story" className="relative py-28 sm:py-36 scroll-mt-20 overflow-hidden bg-gray-950">
      <div className="relative max-w-7xl mx-auto px-5 sm:px-8">
        <div className="max-w-3xl mx-auto text-center mb-14">
          <div className="badge-dark mb-5 mx-auto w-fit">
            <span>OUR STORY</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-white leading-tight">
            Built by students who
            <br />
            <span className="bg-gradient-to-r from-gray-400 to-gray-500 bg-clip-text text-transparent">lived these problems.</span>
          </h2>
          <p className="mt-5 text-mag-text-muted leading-relaxed">
            Magneetar began with students who knew both problems firsthand. Phone theft is a reality
            on university campuses across Nigeria, and staying in touch with family back home is how
            students everywhere hold their lives together.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-5 max-w-5xl mx-auto">
          {ORIGIN_POINTS.map((point) => (              <div key={point.title} className="relative group rounded-2xl border-mag-border bg-gradient-to-b from-mag-surface to-mag-bg p-7 overflow-hidden hover:border-emerald-500/15 transition-all duration-400">
              {/* Top accent on hover */}
              <div className="absolute top-0 left-10 right-10 h-px bg-gradient-to-r from-transparent via-emerald-500/0 to-transparent group-hover:via-emerald-500/30 transition-all duration-500" />

              <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mb-5 group-hover:bg-emerald-500/15 transition-all">
                <point.icon size={17} className="text-emerald-400/70 group-hover:text-emerald-400 transition-colors" />
              </div>
              <div className="text-mag-text font-semibold text-sm">{point.title}</div>
              <div className="text-[12.5px] text-mag-text-muted leading-relaxed mt-2">{point.description}</div>
            </div>
          ))}
        </div>

        <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-3 text-[11px] font-mono text-mag-text-muted">
          <span>STARTED BY STUDENTS</span>
          <span className="w-1 h-1 rounded-full bg-emerald-500/30" />
          <span>EVERY CLAIM ON THIS PAGE IS VERIFIABLE</span>
        </div>
      </div>
    </section>
  );
}
