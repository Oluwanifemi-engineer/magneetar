'use client';

import { useState, useEffect, useCallback } from 'react';
import { Play, Pause, Volume2, VolumeX, Maximize, MapPin, Shield, Camera, Lock, Zap, ChevronRight } from 'lucide-react';

/**
 * VideoDemo — embeds a product demo video with a cinematic overlay.
 *
 * When no video URL is configured, renders an animated step-through of the
 * 5 core features with a simulated dashboard mockup that updates in real time.
 * Set DEMO_VIDEO_URL to switch to a real embed (YouTube / Loom / MP4).
 */

const DEMO_VIDEO_URL = ''; // Set to YouTube/Loom URL when available
const DEMO_THUMBNAIL = '/magneetar-mhalf.svg';

const DEMO_STEPS = [
  {
    icon: MapPin,
    title: 'Real-time Tracking',
    detail: '3-second GPS updates with accurate coordinates',
    marker: 'tracking',
    color: 'from-emerald-500 to-teal-600',
  },
  {
    icon: Shield,
    title: 'Theft Detection',
    detail: '8-signal weighted theft scoring',
    marker: 'sentinel',
    color: 'from-amber-500 to-orange-600',
  },
  {
    icon: Camera,
    title: 'Evidence Capture',
    detail: 'Tamper-evident photo + audio captures',
    marker: 'evidence',
    color: 'from-blue-500 to-indigo-600',
  },
  {
    icon: Lock,
    title: 'Remote Commands',
    detail: 'Lock, siren, wipe — one click',
    marker: 'commands',
    color: 'from-red-500 to-rose-600',
  },
  {
    icon: Zap,
    title: 'Offline Resilience',
    detail: 'Queues pings, syncs on reconnect',
    marker: 'offline',
    color: 'from-violet-500 to-purple-600',
  },
];

/* ── Animated Dashboard Mockup for video placeholder ────────────────────── */
function DemoMockup({ activeStep }: { activeStep: number }) {
  const step = DEMO_STEPS[activeStep];
  const sentinelScore = activeStep === 1 ? 72 : activeStep === 2 ? 85 : 0;
  const isLocked = activeStep === 3;
  const battery = 84;

  return (
    <div className="relative bg-mag-surface rounded-2xl overflow-hidden shadow-2xl border border-mag-border">
      {/* Title bar */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-mag-surface-raised/80 border-b border-mag-border/50">
        <div className="flex gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500/80" />
          <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/80" />
          <div className="w-2.5 h-2.5 rounded-full bg-green-500/80" />
        </div>            <span className="text-[10px] font-mono text-mag-text-muted ml-2">MAGNEETAR COMMAND CENTER</span>
        <div className="ml-auto flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-[9px] font-mono text-emerald-400">LIVE</span>
        </div>
      </div>

      {/* Map area */}
      <div className="relative h-48 overflow-hidden">
        {/* Grid */}
        <div
          className="absolute inset-0 opacity-10"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.05) 1px, transparent 1px)',
            backgroundSize: '20px 20px',
          }}
        />

        {/* Animated marker */}
        <div className="absolute top-1/2 left-1/3 -translate-x-1/2 -translate-y-1/2 transition-all duration-700">
          <div className="relative">
            <div className={`absolute -inset-8 rounded-full bg-gradient-to-br ${step.color} opacity-10 animate-pulse`} />
            <div className={`w-10 h-10 rounded-full bg-gradient-to-br ${step.color} flex items-center justify-center shadow-lg transition-all duration-500`}>
              <step.icon size={18} className="text-white" />
            </div>
            <div className="absolute -inset-3 rounded-full border-2 border-mag-border/50 animate-ping" />
          </div>
        </div>

        {/* Trail dots */}
        {activeStep === 0 && (
          <div className="absolute top-1/2 left-[15%] flex gap-2 -translate-y-1/2">
            {[...Array(5)].map((_, i) => (
              <div
                key={i}
                className="w-1.5 h-1.5 rounded-full bg-emerald-400/40"
                style={{ animationDelay: `${i * 200}ms`, opacity: 1 - i * 0.15 }}
              />
            ))}
          </div>
        )}

        {/* Evidence overlay */}
        {activeStep === 2 && (
          <div className="absolute inset-0 bg-blue-500/5 flex items-center justify-center">
            <div className="bg-mag-bg/90 border border-blue-500/30 rounded-lg p-3 flex items-center gap-2">
              <Camera size={14} className="text-blue-400" />
              <span className="text-[10px] font-mono text-blue-300">Evidence capture in progress...</span>
              <div className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
            </div>
          </div>
        )}

        {/* Lock overlay */}
        {isLocked && (
          <div className="absolute inset-0 bg-red-500/5 flex items-center justify-center">
            <div className="bg-mag-bg/90 border border-red-500/30 rounded-lg p-3 flex items-center gap-2">
              <Lock size={14} className="text-red-400" />
              <span className="text-[10px] font-mono text-red-300">Screen locked remotely</span>
            </div>
          </div>
        )}

        {/* Sidebar */}
        <div className="absolute right-0 top-0 bottom-0 w-48 bg-mag-bg/90 border-l border-mag-border/50 p-3">
          <div className="text-[9px] font-mono text-mag-text-muted mb-2">DEVICES</div>
          {['Galaxy A03s', 'Pixel 8', 'Redmi Note 12'].map((name, i) => (
            <div
              key={name}
              className={`flex items-center gap-2 p-2 rounded-lg mb-1.5 transition-all duration-300 ${
                i === 0 ? 'bg-mag-surface-raised border-mag-border/50' : 'opacity-40'
              }`}
            >
              <div className={`w-2 h-2 rounded-full ${i === 0 ? 'bg-emerald-500' : 'bg-mag-text-muted/50'}`} />
              <span className="text-[10px] font-mono text-mag-text-muted">{name}</span>
            </div>
          ))}

          <div className="mt-4 text-[9px] font-mono text-mag-text-muted mb-2">DETECTION</div>
          <div className="p-2 rounded-lg bg-mag-surface border-mag-border">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-mono text-mag-text-dim">Score</span>
              <span className={`text-[10px] font-mono font-bold ${
                sentinelScore >= 70 ? 'text-red-400' : sentinelScore >= 40 ? 'text-amber-400' : 'text-emerald-400'
              }`}>
                {sentinelScore}
              </span>
            </div>              <div className="h-1 border-mag-border rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-1000 ${
                  sentinelScore >= 70 ? 'bg-red-500' : sentinelScore >= 40 ? 'bg-amber-500' : 'bg-emerald-500'
                }`}
                style={{ width: `${sentinelScore}%` }}
              />
            </div>
          </div>

          {/* Command queue indicator */}
          {activeStep >= 3 && (
            <div className="mt-3">
              <div className="text-[9px] font-mono text-mag-text-muted mb-1">COMMANDS</div>
              <div className="p-2 rounded-lg bg-mag-surface border-mag-border">
                <div className="flex items-center gap-1.5">
                  <div className={`w-1.5 h-1.5 rounded-full ${isLocked ? 'bg-red-500 animate-pulse' : 'bg-emerald-500'}`} />

                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Status bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-mag-surface-raised/60 border-t border-mag-border/50">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5">
            <div className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            <span className="text-[9px] font-mono text-mag-text-muted">Samsung A03s</span>
          </div>
          <span className="text-[9px] font-mono text-mag-text-muted">•</span>
          <span className="text-[9px] font-mono text-mag-text-muted">Battery {battery}%</span>
          <span className="text-[9px] font-mono text-mag-text-muted">•</span>
          <span className="text-[9px] font-mono text-mag-text-muted">Wifi</span>
        </div>
        <span className="text-[9px] font-mono text-mag-text-muted">2s ago</span>
      </div>
    </div>
  );
}

export function VideoDemo() {
  const [isPlaying, setIsPlaying] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  const [isMuted, setIsMuted] = useState(true);

  const nextStep = useCallback(() => {
    setActiveStep((prev) => (prev + 1) % DEMO_STEPS.length);
  }, []);

  // Auto-advance when playing
  useEffect(() => {
    if (!isPlaying) return;
    const interval = setInterval(nextStep, 3000);
    return () => clearInterval(interval);
  }, [isPlaying, nextStep]);

  // If a real video URL is configured, render the embed
  if (DEMO_VIDEO_URL) {
    const getEmbedUrl = (url: string) => {
      if (url.includes('youtube.com') || url.includes('youtu.be')) {
        const videoId = url.includes('youtu.be')
          ? url.split('/').pop()?.split('?')[0]
          : new URL(url).searchParams.get('v');
        return `https://www.youtube.com/embed/${videoId}?autoplay=0&mute=1`;
      }
      if (url.includes('loom.com')) {
        return `${url}/embed`;
      }
      return url;
    };

    return (
      <section className="py-20 sm:py-28 bg-black relative overflow-hidden">
        <div className="max-w-5xl mx-auto px-5 sm:px-8">
          <div className="text-center mb-12">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border-mag-border/50 bg-mag-surface mb-5">
              <Play size={10} className="text-emerald-400" />
              <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-mag-text-muted">WATCH THE DEMO</span>
            </div>
            <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight text-white mb-4">
              See Magneetar in 30 seconds.
            </h2>
          </div>
          <div className="relative rounded-2xl overflow-hidden shadow-2xl border border-mag-border">
            <div className="aspect-video">
              <iframe
                src={getEmbedUrl(DEMO_VIDEO_URL)}
                className="w-full h-full"
                allow="autoplay; encrypted-media"
                allowFullScreen
                title="Magneetar Product Demo"
              />
            </div>
          </div>
        </div>
      </section>
    );
  }

  // Interactive demo placeholder
  return (
    <section className="py-20 sm:py-28 bg-black relative overflow-hidden">
      <div className="max-w-6xl mx-auto px-5 sm:px-8">
        {/* Section header */}
        <div className="text-center mb-12">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border-mag-border/50 bg-mag-surface mb-5">
            <Play size={10} className="text-emerald-400" />
            <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-mag-text-muted">LIVE DEMO</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight text-white mb-4">
            See Magneetar in action.
          </h2>
          <p className="text-mag-text-muted text-base max-w-lg mx-auto">
            Click a feature below to watch the command center respond in real time.
          </p>
        </div>

        <div className="grid lg:grid-cols-5 gap-8 items-start">
          {/* Mockup — takes 3 columns */}
          <div className="lg:col-span-3">
            <DemoMockup activeStep={activeStep} />
          </div>

          {/* Feature selector — takes 2 columns */}
          <div className="lg:col-span-2 space-y-2">
            {DEMO_STEPS.map((s, i) => (                <button
                key={s.title}
                onClick={() => { setActiveStep(i); setIsPlaying(false); }}
                className={`w-full text-left p-3 rounded-xl border transition-all duration-300 ${
                  i === activeStep
                    ? 'bg-mag-surface-raised border-mag-border shadow-lg'
                    : 'border-transparent hover:bg-mag-surface hover:border-mag-border/25'
                }`}
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`w-9 h-9 rounded-lg flex items-center justify-center transition-all duration-300 ${
                      i === activeStep ? `bg-gradient-to-br ${s.color}` : 'bg-mag-surface'
                    }`}
                  >
                    <s.icon size={16} className={i === activeStep ? 'text-white' : 'text-mag-text-muted'} />
                  </div>
                  <div className="flex-1 min-w-0">                      <span className={`text-sm font-bold transition-colors ${
                      i === activeStep ? 'text-mag-text' : 'text-mag-text-muted'
                    }`}>
                      {s.title}
                    </span>
                    {i === activeStep && (
                      <p className="text-xs text-mag-text-muted mt-0.5">{s.detail}</p>
                    )}
                  </div>
                  {i === activeStep && (
                    <ChevronRight size={14} className="text-mag-text-muted shrink-0" />
                  )}
                </div>
              </button>
            ))}

            {/* Playback controls */}
            <div className="flex items-center gap-3 pt-3">
              <button
                onClick={() => setIsPlaying(!isPlaying)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg border text-xs font-mono transition-all ${
                  isPlaying
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                    : 'border-mag-border text-mag-text-muted hover:bg-mag-surface'
                }`}
              >
                {isPlaying ? <Pause size={12} /> : <Play size={12} />}
                {isPlaying ? 'Pause' : 'Auto-play'}
              </button>

              <div className="flex gap-1 ml-auto">
                {DEMO_STEPS.map((_, i) => (
                  <div
                    key={i}
                    className={`w-1.5 h-1.5 rounded-full transition-all ${
                      i === activeStep ? 'bg-mag-text w-4' : 'bg-mag-text-muted/50'
                    }`}
                  />
                ))}
              </div>
            </div>

            {/* Trust badges */}
            <div className="flex items-center gap-4 pt-4 border-t border-mag-border mt-2">
              {['Uninstall-resistant', 'Encrypted', 'Source-available'].map((label) => (
                <span key={label} className="text-[9px] font-mono text-mag-text-muted">{label}</span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
