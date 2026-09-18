'use client';

import { useState, useEffect, useCallback } from 'react';
import { Play, Pause, MapPin, Shield, Camera, Lock, Zap } from 'lucide-react';

const TOUR_STEPS = [
  {
    id: 'tracking',
    icon: MapPin,
    title: 'Real-time Tracking',
    description: 'Watch your device move on the live map with 3-second GPS updates. Accurate street-level coordinates.',
    color: 'from-emerald-500 to-teal-600',
    stat: '3s updates',
  },
  {
    id: 'sentinel',
    icon: Shield,
    title: 'Theft Detection',
    description: 'Automatic theft scoring across 8 signals: SIM change, failed unlocks, location off, airplane mode, geofence exit, and more.',
    color: 'from-amber-500 to-orange-600',
    stat: '8 signals',
  },
  {
    id: 'evidence',
    icon: Camera,
    title: 'Evidence Capture',
    description: 'Remote photo bursts and audio recording — tamper-evident evidence you can take to the police.',
    color: 'from-blue-500 to-indigo-600',
    stat: 'Tamper-evident',
  },
  {
    id: 'commands',
    icon: Lock,
    title: 'Remote Commands',
    description: 'Lock the screen, trigger a siren, or wipe data — one click from the dashboard. At-most-once execution prevents replay.',
    color: 'from-red-500 to-rose-600',
    stat: 'One-click',
  },
  {
    id: 'offline',
    icon: Zap,
    title: 'Offline Resilience',
    description: 'Pings queue when offline and sync on reconnect — no data lost during network gaps.',
    color: 'from-violet-500 to-purple-600',
    stat: 'Zero gaps',
  },
];

/* ── Animated Dashboard Mockup ─────────────────────────────────────────── */
function DashboardMockup({ activeStep }: { activeStep: number }) {
  const step = TOUR_STEPS[activeStep];

  return (
    <div className="relative bg-mag-surface rounded-2xl overflow-hidden shadow-2xl border border-mag-border">
      {/* Title bar */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-mag-surface-raised/80 border-b border-mag-border/50">
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500/80" />
          <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/80" />
          <div className="w-2.5 h-2.5 rounded-full bg-green-500/80" />
        </div>
        <span className="text-[10px] font-mono text-mag-text-muted ml-2">MAGNEETAR COMMAND CENTER</span>
        <div className="ml-auto flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-[9px] font-mono text-emerald-400">LIVE</span>
        </div>
      </div>

      {/* Map area with animated marker */}
      <div className="relative h-48 bg-gray-850 overflow-hidden">
        {/* Grid overlay */}
        <div className="absolute inset-0 opacity-10"
          style={{
            backgroundImage: 'linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px)',
            backgroundSize: '20px 20px',
          }}
        />

        {/* Animated marker */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 transition-all duration-1000">
          <div className="relative">
            {/* Accuracy circle */}
            <div className={`absolute -inset-8 rounded-full bg-gradient-to-br ${step.color} opacity-10 animate-pulse`} />
            {/* Pin */}
            <div className={`w-10 h-10 rounded-full bg-gradient-to-br ${step.color} flex items-center justify-center shadow-lg`}>
              <step.icon size={18} className="text-mag-text" />
            </div>
            {/* Pulse ring */}
            <div className={`absolute -inset-3 rounded-full border-2 border-mag-border/50 animate-ping`} />
          </div>
        </div>

        {/* Sidebar mockup */}
        <div className="absolute right-0 top-0 bottom-0 w-48 bg-mag-bg/90 border-l border-mag-border/50 p-3">
          <div className="text-[9px] font-mono text-mag-text-muted mb-2">DEVICES</div>
          {['Galaxy A03s', 'Pixel 8', 'Redmi Note 12'].map((name, i) => (
            <div key={name} className={`flex items-center gap-2 p-2 rounded-lg mb-1.5 transition-all duration-300 ${
              i === 0 ? 'bg-mag-surface-raised border-mag-border/50' : 'opacity-40'
            }`}>
              <div className={`w-2 h-2 rounded-full ${i === 0 ? 'bg-emerald-500' : 'bg-gray-600'}`} />
              <span className="text-[10px] font-mono text-mag-text-muted">{name}</span>
            </div>
          ))}

          <div className="mt-4 text-[9px] font-mono text-mag-text-muted mb-2">DETECTION</div>
          <div className="p-2 rounded-lg bg-mag-surface border-mag-border">
            {(() => {
              const score = activeStep === 1 ? 72 : activeStep === 2 ? 85 : activeStep === 3 ? 45 : 0;
              const scoreColor = score >= 70 ? 'text-red-400' : score >= 40 ? 'text-amber-400' : 'text-emerald-400';
              const barColor = score >= 70 ? 'bg-red-500' : score >= 40 ? 'bg-amber-500' : 'bg-emerald-500';
              return (
                <>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] font-mono text-mag-text-dim">Score</span>
                    <span className={`text-[10px] font-mono ${scoreColor} font-bold transition-colors duration-500`}>{score}</span>
                  </div>
                  <div className="h-1 bg-mag-border rounded-full overflow-hidden">
                    <div className={`h-full ${barColor} rounded-full transition-all duration-1000`} style={{ width: `${score}%` }} />
                  </div>
                </>
              );
            })()}
          </div>
        </div>
      </div>

      {/* Status bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-mag-surface-raised/60 border-t border-mag-border/50">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            <span className="text-[9px] font-mono text-mag-text-dim">Samsung A03s</span>
          </div>
          <span className="text-[9px] font-mono text-mag-text-muted">•</span>
          <span className="text-[9px] font-mono text-mag-text-muted">Battery 84%</span>
          <span className="text-[9px] font-mono text-mag-text-muted">•</span>
          <span className="text-[9px] font-mono text-mag-text-muted">Wifi</span>
        </div>
        <span className="text-[9px] font-mono text-mag-text-muted">2s ago</span>
      </div>
    </div>
  );
}

export function ProductTour() {
  const [activeStep, setActiveStep] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  const nextStep = useCallback(() => setActiveStep((prev) => (prev + 1) % TOUR_STEPS.length), []);
  const prevStep = useCallback(() => setActiveStep((prev) => (prev - 1 + TOUR_STEPS.length) % TOUR_STEPS.length), []);

  // Auto-advance when playing
  useEffect(() => {
    if (!isPlaying) return;
    const interval = setInterval(nextStep, 3500);
    return () => clearInterval(interval);
  }, [isPlaying, nextStep]);

  return (
    <section className="py-20 sm:py-28 bg-gray-950 overflow-hidden">
      <div className="max-w-7xl mx-auto px-5 sm:px-8">
        {/* Section header */}
        <div className="text-center mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border-mag-border/50 bg-mag-surface mb-5">
            <Play size={10} className="text-emerald-400" />
            <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-mag-text-1">PRODUCT TOUR</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight text-white mb-4">
            See it in action.
          </h2>
          <p className="text-mag-text-muted text-base max-w-lg mx-auto">
            Five core capabilities, one command center. Every feature is built for
            the moment your phone disappears.
          </p>
        </div>

        <div className="grid lg:grid-cols-2 gap-12 items-center">
          {/* Mockup */}
          <DashboardMockup activeStep={activeStep} />

          {/* Step selector */}
          <div className="space-y-3">
            {TOUR_STEPS.map((step, i) => (
              <button
                key={step.id}
                onClick={() => setActiveStep(i)}
                className={"w-full text-left p-4 rounded-xl border transition-all duration-300 " +
                  (i === activeStep
                    ? 'bg-mag-surface-raised border-mag-border shadow-lg'
                    : 'border-mag-border/25 hover:bg-mag-surface hover:border-mag-border/25')
                }
              >
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-xl flex items-center justify-center transition-all duration-300 ${
                    i === activeStep
                      ? `bg-gradient-to-br ${step.color}`
                      : 'bg-mag-surface'
                  }`}>
                    <step.icon size={18} className={i === activeStep ? 'text-mag-text' : 'text-mag-text-muted'} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={"text-sm font-bold transition-colors " +
                        (i === activeStep ? 'text-mag-text' : 'text-mag-text-muted')}>{step.title}</span>
                      <span className={"text-[9px] font-mono px-1.5 py-0.5 rounded " +
                        (i === activeStep ? 'bg-emerald-500/10 text-emerald-400' : 'bg-mag-surface text-mag-text-muted')}>{step.stat}</span>
                    </div>
                    {i === activeStep && (
                      <p className="text-xs text-mag-text-muted mt-1 leading-relaxed">{step.description}</p>
                    )}
                  </div>
                </div>
              </button>
            ))}

            {/* Navigation */}
            <div className="flex items-center gap-3 pt-4">
              <button
                onClick={() => setIsPlaying(!isPlaying)}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg border text-xs font-mono transition-all ${
                  isPlaying
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                    : 'border-mag-border text-mag-text-muted hover:bg-mag-surface'
                }`}
              >
                {isPlaying ? <Pause size={12} /> : <Play size={12} />}
                {isPlaying ? 'Pause' : 'Auto'}
              </button>
              <button
                onClick={prevStep}
                className="px-3 py-2 rounded-lg border-mag-border/50 text-mag-text-muted text-xs font-mono hover:bg-mag-surface hover:text-mag-text transition-colors"
              >
                ←
              </button>
              <button
                onClick={nextStep}
                className="px-3 py-2 rounded-lg border-mag-border/50 text-mag-text-muted text-xs font-mono hover:bg-mag-surface hover:text-mag-text transition-colors"
              >
                →
              </button>
              <div className="flex gap-1.5 ml-auto">
                {TOUR_STEPS.map((_, i) => (
                  <div
                    key={i}
                    className={`w-1.5 h-1.5 rounded-full transition-all ${
                      i === activeStep ? 'bg-mag-text w-4' : 'bg-mag-text-muted/50'
                    }`}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
