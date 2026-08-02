'use client';

import { Compass, Users, Rocket } from 'lucide-react';

/**
 * Magneetar's origin story.
 *
 * Deliberately NO university history or rankings here — the project is built
 * to grow well beyond any single campus or country, so the story stays about
 * the problems, not the place. Every claim is verifiable and nothing is
 * fabricated; real adoption numbers get added as users arrive.
 */
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
    <section
      id="our-story"
      className="relative py-24 sm:py-32 scroll-mt-20 overflow-hidden"
    >
      <div className="absolute inset-0 landing-vignette pointer-events-none" />
      <div className="absolute top-24 right-0 w-[420px] h-[420px] rounded-full bg-[#06B6D4]/6 blur-[120px] pointer-events-none" />

      <div className="relative max-w-7xl mx-auto px-5 sm:px-8">
        {/* Section header */}
        <div className="max-w-3xl mx-auto text-center mb-14">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-white/10 bg-white/[0.03] mb-5">
            <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-white/50">OUR STORY</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight text-white leading-tight">
            Built by students who
            <br />
            <span className="text-gradient-primary">lived these problems.</span>
          </h2>
          <p className="mt-5 text-white/45 leading-relaxed">
            Magneetar began with students who knew both problems firsthand. Phone theft is a reality
            on university campuses across Nigeria, and staying in touch with family back home is how
            students everywhere hold their lives together. We didn’t start from a boardroom; we
            started from problems our whole generation recognizes.
          </p>
        </div>

        {/* Story cards */}
        <div className="grid md:grid-cols-3 gap-5 max-w-5xl mx-auto">
          {ORIGIN_POINTS.map((point) => (
            <div
              key={point.title}
              className="relative group card-glow rounded-2xl border border-white/[0.07] bg-[#0d0d14]/80 backdrop-blur-xl p-7 overflow-hidden"
            >
              <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none bg-[radial-gradient(ellipse_at_top,rgba(6,182,212,0.1)_0%,transparent_60%)]" />
              <div className="w-10 h-10 rounded-lg border border-white/[0.08] bg-white/[0.03] flex items-center justify-center mb-5 group-hover:border-[#06B6D4]/30 transition-colors">
                <point.icon size={17} className="text-[#06B6D4]" />
              </div>
              <div className="text-white font-semibold text-sm">{point.title}</div>
              <div className="text-[12.5px] text-white/40 leading-relaxed mt-2">{point.description}</div>
            </div>
          ))}
        </div>

        {/* Honest-signal footnote */}
        <div className="mt-10 flex items-center justify-center gap-2 text-[11px] font-mono text-white/25">
          <span>STARTED BY STUDENTS</span>
          <span className="w-1 h-1 rounded-full bg-white/20" />
          <span>REAL ADOPTION NUMBERS COMING AS USERS ARRIVE</span>
        </div>
      </div>
    </section>
  );
}
