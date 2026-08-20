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
    <section
      id="our-story"
      className="relative py-24 sm:py-32 bg-white scroll-mt-20 overflow-hidden"
    >
      <div className="relative max-w-7xl mx-auto px-5 sm:px-8">
        <div className="max-w-3xl mx-auto text-center mb-14">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-gray-200 bg-gray-50 mb-5">
            <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-gray-500">OUR STORY</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight text-gray-900 leading-tight">
            Built by students who
            <br />
            <span className="text-gray-400">lived these problems.</span>
          </h2>
          <p className="mt-5 text-gray-500 leading-relaxed">
            Magneetar began with students who knew both problems firsthand. Phone theft is a reality
            on university campuses across Nigeria, and staying in touch with family back home is how
            students everywhere hold their lives together. We didn&apos;t start from a boardroom; we
            started from problems our whole generation recognizes.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-5 max-w-5xl mx-auto">
          {ORIGIN_POINTS.map((point) => (
            <div
              key={point.title}
              className="relative group rounded-2xl border border-gray-200 bg-white p-7 overflow-hidden hover:border-gray-300 hover:shadow-lg hover:shadow-gray-900/[0.04] transition-all duration-300"
            >
              <div className="w-10 h-10 rounded-lg bg-gray-50 border border-gray-200 flex items-center justify-center mb-5 group-hover:bg-gray-100 transition-colors">
                <point.icon size={17} className="text-gray-600" />
              </div>
              <div className="text-gray-900 font-semibold text-sm">{point.title}</div>
              <div className="text-[12.5px] text-gray-500 leading-relaxed mt-2">{point.description}</div>
            </div>
          ))}
        </div>

        <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-2 text-[11px] font-mono text-gray-400">
          <span>STARTED BY STUDENTS</span>
          <span className="w-1 h-1 rounded-full bg-gray-300" />
          <span>EVERY CLAIM ON THIS PAGE IS VERIFIABLE</span>
        </div>
      </div>
    </section>
  );
}
