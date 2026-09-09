'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { ArrowRight, ShieldCheck, Download, Check, Smartphone, Battery, MapPin, Camera, Lock, Zap } from 'lucide-react';
import { VersionBadge } from './VersionBadge';
import { AuroraBackground } from '@/components/ui/AuroraBackground';
import { MagneticButton } from '@/components/ui/MagneticButton';
import { AnimatedCounter } from '@/components/ui/AnimatedCounter';

const HERO_STATS: { value: number; label: string; prefix?: string; suffix?: string }[] = [
  { value: 3, label: 'second GPS updates', suffix: 's' },
  { value: 25, label: 'M+ phones stolen yearly in Nigeria', prefix: '', suffix: '' },
  { value: 11, label: '% recovery rate without Magneetar', prefix: '', suffix: '%' },
  { value: 0, label: 'naira to start protecting your phone', prefix: '₦', suffix: '' },
];

/* ── Battery Arc SVG ──────────────────────────────────────────────────── */
function BatteryArc() {
  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  const sweepAngle = 270;
  const chargePercent = 87;
  const fillLength = (circumference * sweepAngle * chargePercent) / 360;
  const emptyLength = circumference - fillLength;

  return (
    <svg viewBox="0 0 100 100" className="w-full h-full">
      <circle cx="50" cy="50" r={radius} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="5" strokeLinecap="round"
        strokeDasharray={`${(circumference * sweepAngle) / 360} ${circumference}`}
        transform="rotate(135 50 50)" />
      <circle cx="50" cy="50" r={radius} fill="none" stroke="rgba(16,185,129,0.7)" strokeWidth="5" strokeLinecap="round"
        strokeDasharray={`${fillLength} ${emptyLength}`}
        transform="rotate(135 50 50)"
        className="hero-arc-draw"
        style={{ filter: 'drop-shadow(0 0 8px rgba(16,185,129,0.3))' }} />
      <text x="50" y="46" textAnchor="middle" className="fill-white text-[18px] font-bold font-mono">87</text>
      <text x="50" y="60" textAnchor="middle" className="fill-white/30 text-[7px] font-mono tracking-wider">PERCENT</text>
    </svg>
  );
}

/* ── Signal Wave SVG ──────────────────────────────────────────────────── */
function SignalWave() {
  const bars = [0.3, 0.5, 0.7, 0.85, 1.0, 0.9, 0.75, 0.55, 0.4, 0.6, 0.8, 0.95, 0.7, 0.5, 0.35, 0.55, 0.75, 0.9, 0.65, 0.45];
  const barWidth = 4;
  const gap = 2;
  const height = 32;

  return (
    <svg viewBox={`0 0 ${bars.length * (barWidth + gap)} ${height}`} className="w-full h-full" preserveAspectRatio="none">
      {bars.map((h, i) => (
        <rect key={i} x={i * (barWidth + gap)} y={height - h * height} width={barWidth} height={h * height} rx="1.5"
          fill="rgba(16,185,129,0.4)" className="hero-bar-grow" style={{ animationDelay: `${0.8 + i * 0.06}s` }} />
      ))}
    </svg>
  );
}

/* ── Activity Timeline ────────────────────────────────────────────────── */
const EVENTS = [
  { time: '10:02', icon: MapPin, text: 'Location updated', accent: true },
  { time: '09:58', icon: Camera, text: 'Evidence captured', accent: false },
  { time: '09:55', icon: Lock, text: 'Device armed', accent: false },
];

function ActivityTimeline() {
  return (
    <div className="relative pl-4">
      <div className="absolute left-[5px] top-1 bottom-1 w-px bg-emerald-500/20" />
      <div className="space-y-3">
        {EVENTS.map((event, i) => (
          <div key={i} className="relative flex items-start gap-3">
            <div className={`absolute left-[-11px] top-1 w-[7px] h-[7px] rounded-full ${event.accent ? 'bg-emerald-400' : 'bg-mag-border/50'} ring-2 ring-[#0f172a]`} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <event.icon size={10} className={`${event.accent ? 'text-emerald-400/60' : 'text-mag-text-muted'} shrink-0`} />
                <span className="text-[10px] font-mono text-mag-text-muted truncate">{event.text}</span>
              </div>
              <span className="text-[8px] font-mono text-mag-text-muted">{event.time}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Hero({ authed }: { authed: boolean }) {
  return (
    <AuroraBackground className="relative pt-28 pb-20 sm:pt-36 sm:pb-28 overflow-hidden bg-gray-950">
      <div className="relative max-w-7xl mx-auto px-5 sm:px-8">
        {/* Top glow accent */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-emerald-500/[0.03] rounded-full blur-[120px] pointer-events-none" />

        <div className="grid lg:grid-cols-2 gap-12 lg:gap-20 items-center">
          {/* ─── Left: Copy ─────────────────────────────────────────────── */}
          <div className="relative z-10">
            <VersionBadge />

            {/* Main headline — large, bold, clean */}
            <h1 className="mt-8 text-4xl sm:text-5xl lg:text-[3.5rem] font-extrabold tracking-[-0.03em] text-white leading-[1.08]">
              Protect what you own.
              <br />
              <span className="text-mag-text-muted">Stay close to who you love.</span>
            </h1>

            <p className="mt-6 text-lg text-mag-text-muted leading-relaxed max-w-xl">
              Anti-theft tracking for Android — when your phone is stolen, it keeps reporting its
              location, captures evidence, and lets you lock it remotely. Built for Africa.
            </p>

            {/* CTAs */}
            <div className="mt-9 flex flex-wrap items-center gap-3" style={{ animation: 'heroFadeIn 0.7s cubic-bezier(0.16, 1, 0.3, 1) 0.3s both' }}>
              {authed ? (
                <MagneticButton as="a" href="/dashboard" className="btn-mag-primary !px-7 !py-3.5">
                  <ShieldCheck size={16} />
                  Open Command Center
                  <ArrowRight size={15} />
                </MagneticButton>
              ) : (
                <>
                  <MagneticButton as="a" href="/signup" className="btn-mag-primary !px-7 !py-3.5">
                    Get Started Free
                    <ArrowRight size={15} />
                  </MagneticButton>
                  <MagneticButton as="a" href="/login" className="btn-mag-ghost !px-6 !py-3.5">
                    Sign In
                  </MagneticButton>
                </>
              )}
            </div>

            <div className="mt-4 flex items-center gap-2" style={{ animation: 'heroFadeIn 0.7s cubic-bezier(0.16, 1, 0.3, 1) 0.4s both' }}>
              <Check size={13} className="text-emerald-400" />
              <span className="text-[12px] font-mono text-mag-text-muted">Free for 1 device · No credit card required</span>
            </div>

            {/* Stats */}
            <div className="mt-12 grid grid-cols-2 sm:grid-cols-4 gap-6 max-w-xl" style={{ animation: 'heroFadeIn 0.7s cubic-bezier(0.16, 1, 0.3, 1) 0.6s both' }}>
              {HERO_STATS.map((stat) => (
                <div key={stat.label}>
                  <div className="text-white text-lg font-bold font-mono tabular-nums">
                    <AnimatedCounter value={stat.value} prefix={stat.prefix} suffix={stat.suffix} className="text-lg" />
                  </div>
                  <div className="text-[10px] font-mono text-mag-text-muted uppercase tracking-wider mt-1 font-semibold">{stat.label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* ─── Right: Device Status Card ──────────────────────────────── */}
          <div className="relative z-10" style={{ animation: 'heroFadeIn 0.8s cubic-bezier(0.16, 1, 0.3, 1) 0.3s both' }}>
            {/* Card glow */}
            <div className="absolute -inset-8 bg-emerald-500/[0.04] rounded-[32px] blur-[60px] pointer-events-none" />

            <div className="relative">
              {/* Floating device label */}
              <div className="absolute -top-3 right-4 sm:right-8 px-3 py-1.5 rounded-lg border-mag-border/50 bg-[#0f172a]/90 backdrop-blur-sm shadow-elevation-2 flex items-center gap-2 z-10">
                <span className="relative flex w-2 h-2">
                  <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
                  <span className="relative inline-flex rounded-full w-2 h-2 bg-emerald-400" />
                </span>
                <Smartphone size={10} className="text-mag-text-muted" />
                <span className="text-[10px] font-mono font-bold text-mag-text">Galaxy S24 · Active</span>
              </div>

              {/* Main Card */}
              <div className="relative rounded-2xl bg-mag-landing shadow-elevation-4 overflow-hidden border-mag-border/50">
                {/* Subtle top glow */}
                <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-emerald-500/30 to-transparent" />

                {/* Card header */}
                <div className="flex items-center justify-between px-5 py-3.5 border-b border-mag-border/50">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                      <Smartphone size={14} className="text-emerald-400/70" />
                    </div>
                    <div>
                      <div className="text-[11px] font-bold text-mag-text tracking-wide">Galaxy S24</div>
                      <div className="text-[8px] font-mono text-mag-text-muted tracking-wider">SM-S921B · ANDROID 14</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/20">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                    <span className="text-[8px] font-mono font-bold text-emerald-400 tracking-wider">ONLINE</span>
                  </div>
                </div>

                {/* Telemetry Grid */}
                <div className="grid grid-cols-3 gap-px bg-mag-surface">
                  <div className="bg-mag-landing px-4 py-5 flex flex-col items-center">
                    <div className="w-20 h-20 relative"><BatteryArc /></div>
                    <div className="text-[8px] font-mono text-mag-text-muted tracking-widest mt-1">BATTERY</div>
                  </div>
                  <div className="bg-mag-landing px-4 py-5 flex flex-col">
                    <div className="text-[8px] font-mono text-mag-text-muted tracking-widest mb-2">SIGNAL</div>
                    <div className="flex-1 flex items-end">
                      <div className="w-full h-8"><SignalWave /></div>
                    </div>
                    <div className="flex items-center justify-between mt-1.5">
                      <span className="text-[9px] font-mono text-mag-text-muted">-78 dBm</span>
                      <span className="text-[9px] font-mono text-mag-text-muted">4G LTE</span>
                    </div>
                  </div>
                  <div className="bg-mag-landing px-4 py-5 flex flex-col">
                    <div className="text-[8px] font-mono text-mag-text-muted tracking-widest mb-2">THREAT</div>
                    <div className="flex-1 flex items-center justify-center">
                      <div>
                        <div className="text-2xl font-display font-extrabold text-white hero-num-tick">12</div>
                        <div className="text-[7px] font-mono text-mag-text-muted text-center mt-0.5">/ 100</div>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 mt-1">
                      <div className="flex-1 h-1 rounded-full border-mag-border/50 overflow-hidden">
                        <div className="h-full rounded-full bg-emerald-400/60" style={{ width: '12%' }} />
                      </div>
                      <span className="text-[8px] font-mono text-emerald-400/70">SAFE</span>
                    </div>
                  </div>
                </div>

                {/* Live Telemetry Bar */}
                <div className="flex items-center gap-4 px-5 py-3 border-t border-mag-border/25 bg-mag-surface">
                  <div className="flex items-center gap-1.5">
                    <MapPin size={10} className="text-emerald-400/40" />
                    <span className="text-[9px] font-mono text-mag-text-dim hero-num-tick">6.5244°N 3.3792°E</span>
                  </div>
                  <div className="w-px h-3 border-mag-border/50" />
                  <span className="text-[9px] font-mono text-mag-text-dim">38 km/h</span>
                  <div className="w-px h-3 border-mag-border/50" />
                  <span className="text-[9px] font-mono text-emerald-400/50 hero-live-blink">● LIVE</span>
                  <div className="ml-auto flex items-center gap-1">
                    <Battery size={10} className="text-mag-text-muted" />
                    <span className="text-[9px] font-mono text-mag-text-muted">87%</span>
                  </div>
                </div>

                {/* Activity */}
                <div className="px-5 py-4 border-t border-mag-border/25">
                  <div className="text-[8px] font-mono text-mag-text-muted tracking-widest mb-3">RECENT ACTIVITY</div>
                  <ActivityTimeline />
                </div>
              </div>

              {/* Floating chips */}
              <div className="absolute -bottom-3 left-4 sm:left-8 px-3 py-1.5 rounded-lg border-mag-border/50 bg-mag-landing/90 backdrop-blur-sm shadow-elevation-2 flex items-center gap-2 hero-chip-float" style={{ animationDelay: '0.8s' }}>
                <ShieldCheck size={11} className="text-emerald-400/60" />
                <span className="text-[9px] font-mono font-bold text-mag-text-dim">Recovery armed · 3 layers</span>
              </div>

              <div className="absolute -bottom-3 right-4 sm:right-8 px-3 py-1.5 rounded-lg border-mag-border/50 bg-mag-landing/90 backdrop-blur-sm shadow-elevation-2 flex items-center gap-2 hero-chip-float" style={{ animationDelay: '1s' }}>
                <Zap size={11} className="text-emerald-400/60" />
                <span className="text-[9px] font-mono font-bold text-mag-text-dim">3s GPS updates</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </AuroraBackground>
  );
}
