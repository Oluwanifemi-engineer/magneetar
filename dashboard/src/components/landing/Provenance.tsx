'use client';

import { GraduationCap, Cpu, Award } from 'lucide-react';

/**
 * Built at OAU — Magneetar's origin story as social proof.
 *
 * Every claim here is verifiable:
 *  - OAU (est. 1962 as University of Ife, renamed 1987) is one of Nigeria's
 *    premier federal universities, widely known as "Great Ife".
 *  - Its Faculty of Technology (est. 1970) was the FIRST engineering faculty
 *    in Nigeria, and pioneered the SIWES scheme now adopted nationwide.
 *  - It hosts Africa's first MIT-collaboration iLab south of the Sahara.
 *  - CWUR 2026 ranks OAU #5 nationally in Nigeria / #58 in Africa.
 *
 * The origin story frames OAU as the birthplace of the IDEA — not as a
 * uniquely theft-prone place: phone theft is a common campus crime across
 * Nigeria, and staying in touch with family is universal among students.
 *
 * Deliberately NO fabricated user counts — real adoption numbers get added
 * when the campus launch has actual data behind them.
 */
const OAU_POINTS = [
  {
    icon: GraduationCap,
    title: 'Born at Great Ife',
    description:
      'Obafemi Awolowo University, Ile-Ife — founded 1962, one of Nigeria’s premier federal universities, and home to generations of the engineers building Africa’s digital future.',
  },
  {
    icon: Cpu,
    title: 'Nigeria’s first Faculty of Technology',
    description:
      'OAU opened the country’s first engineering faculty in 1970 and pioneered the SIWES work-experience scheme that every Nigerian university now uses.',
  },
  {
    icon: Award,
    title: 'Ranked #5 in Nigeria',
    description:
      'CWUR 2026 places OAU 5th nationally and 58th in Africa — and it runs Africa’s first MIT-collaboration iLab south of the Sahara.',
  },
];

export function Provenance() {
  return (
    <section
      id="built-at-oau"
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
            Magneetar began at Obafemi Awolowo University — but the problems it solves aren’t
            unique to any one campus. Phone theft is a reality on university campuses across
            Nigeria, and staying in touch with family back home is how students everywhere hold
            their lives together. We didn’t start from a boardroom; we started from problems our
            whole generation recognizes.
          </p>
        </div>

        {/* Credibility cards */}
        <div className="grid md:grid-cols-3 gap-5 max-w-5xl mx-auto">
          {OAU_POINTS.map((point) => (
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
          <span>OAU · ILE-IFE · EST. 1962</span>
          <span className="w-1 h-1 rounded-full bg-white/20" />
          <span>REAL ADOPTION NUMBERS COMING AT CAMPUS LAUNCH</span>
        </div>
      </div>
    </section>
  );
}
