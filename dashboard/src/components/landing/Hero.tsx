'use client';

import Link from 'next/link';
import { ArrowRight, ShieldCheck, Download, Check, Smartphone, Battery, MapPin, Camera, Lock } from 'lucide-react';
import { VersionBadge } from './VersionBadge';
import { AnimatedCounter } from '@/components/ui/AnimatedCounter';
import { PRODUCT_STATS } from '@/lib/productStats';

const HERO_STATS: { value: number; label: string; prefix?: string; suffix?: string }[] = [
  ...PRODUCT_STATS.map((s) => ({ value: s.value, label: s.label, prefix: s.prefix, suffix: s.suffix })),
  { value: 3, label: 'background persistence', suffix: '-layer' },
];

/* ── Battery Arc SVG (dark card version — white strokes) ─────────────────── */
function BatteryArc() {
  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  const sweepAngle = 270;
  const chargePercent = 87;
  const fillLength = (circumference * sweepAngle * chargePercent) / 360;
  const emptyLength = circumference - fillLength;

  return (
    <svg viewBox="0 0 100 100" className="w-full h-full">
      <circle
        cx="50" cy="50" r={radius}
        fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="6" strokeLinecap="round"
        strokeDasharray={`${(circumference * sweepAngle) / 360} ${circumference}`}
        transform="rotate(135 50 50)"
      />
      <circle
        cx="50" cy="50" r={radius}
        fill="none" stroke="rgba(255,255,255,0.7)" strokeWidth="6" strokeLinecap="round"
        strokeDasharray={`${fillLength} ${emptyLength}`}
        transform="rotate(135 50 50)"
        className="hero-arc-draw"
        style={{ filter: 'drop-shadow(0 0 6px rgba(255,255,255,0.2))' }}
      />
      <text x="50" y="46" textAnchor="middle" className="fill-white text-[18px] font-bold font-mono">87</text>
      <text x="50" y="60" textAnchor="middle" className="fill-white/40 text-[7px] font-mono tracking-wider">PERCENT</text>
    </svg>
  );
}

/* ── Signal Wave SVG (dark card version) ─────────────────────────────────── */
function SignalWave() {
  const bars = [0.3, 0.5, 0.7, 0.85, 1.0, 0.9, 0.75, 0.55, 0.4, 0.6, 0.8, 0.95, 0.7, 0.5, 0.35, 0.55, 0.75, 0.9, 0.65, 0.45];
  const barWidth = 4;
  const gap = 2;
  const height = 32;
  const width = bars.length * (barWidth + gap);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-full" preserveAspectRatio="none">
      {bars.map((h, i) => (
        <rect
          key={i}
          x={i * (barWidth + gap)}
          y={height - h * height}
          width={barWidth}
          height={h * height}
          rx="1.5"
          fill="rgba(255,255,255,0.45)"
          className="hero-bar-grow"
          style={{ animationDelay: `${0.8 + i * 0.06}s` }}
        />
      ))}
    </svg>
  );
}

/* ── Threat Timeline (dark card version) ─────────────────────────────────── */
const EVENTS = [
  { time: '10:02', icon: MapPin, text: 'Location updated', color: 'bg-white/30' },
  { time: '09:58', icon: Camera, text: 'Evidence captured', color: 'bg-white/20' },
  { time: '09:55', icon: Lock, text: 'Device armed', color: 'bg-white/40' },
];

function ThreatTimeline() {
  return (
    <div className="relative pl-4">
      <div className="absolute left-[5px] top-1 bottom-1 w-px bg-white/10" />
      <div className="space-y-3">
        {EVENTS.map((event, i) => (
          <div key={i} className="relative flex items-start gap-3">
            <div className={`absolute left-[-11px] top-1 w-[7px] h-[7px] rounded-full ${event.color} ring-2 ring-[#0f172a]`} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <event.icon size={10} className="text-white/30 shrink-0" />
                <span className="text-[10px] font-mono text-white/60 truncate">{event.text}</span>
              </div>
              <span className="text-[8px] font-mono text-white/25">{event.time}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Hero({ authed }: { authed: boolean }) {
  return (
    <section className="relative pt-36 pb-24 sm:pt-44 sm:pb-32 overflow-hidden bg-white">
      {/* Subtle grid */}
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.02]"
        style={{
          backgroundImage: 'linear-gradient(#000 1px, transparent 1px), linear-gradient(90deg, #000 1px, transparent 1px)',
          backgroundSize: '44px 44px',
        }}
      />

      <div className="relative max-w-7xl mx-auto px-5 sm:px-8 grid lg:grid-cols-2 gap-16 lg:gap-20 items-center">
        {/* ─── Copy ─────────────────────────────────────────────────────── */}
        <div>
          <VersionBadge />

          <h1
            className="text-5xl sm:text-6xl lg:text-7xl font-display font-extrabold tracking-[-0.03em] text-gray-900 leading-[1.02] mt-8"
            style={{ animation: 'heroFadeIn 0.7s cubic-bezier(0.16, 1, 0.3, 1) 0.1s both' }}
          >
            Protect what
            <br />
            you own.
            <br />
            <span className="text-gray-400">
              Stay close to
              <br />
              who you love.
            </span>
          </h1>

          <p
            className="mt-7 text-lg sm:text-xl text-gray-500 leading-relaxed max-w-xl"
            style={{ animation: 'heroFadeIn 0.7s cubic-bezier(0.16, 1, 0.3, 1) 0.3s both' }}
          >
            In Nigeria, only 11.7% of stolen phones are ever recovered. Magneetar is built to change
            that number — real-time tracking, forensic-grade evidence, and a route that walks you
            straight to your device.
          </p>

          {/* CTAs */}
          <div
            className="mt-10 flex flex-wrap items-center gap-4"
            style={{ animation: 'heroFadeIn 0.7s cubic-bezier(0.16, 1, 0.3, 1) 0.5s both' }}
          >
            {authed ? (
              <Link href="/dashboard" className="inline-flex items-center gap-2.5 px-8 py-4 rounded-2xl text-[13px] font-bold uppercase tracking-wider bg-gray-900 text-white shadow-lg shadow-gray-900/10 hover:bg-gray-800 transition-all duration-200">
                <ShieldCheck size={16} />
                Open Command Center
                <ArrowRight size={15} />
              </Link>
            ) : (
              <>
                <Link href="/signup" className="inline-flex items-center gap-2.5 px-8 py-4 rounded-2xl text-[13px] font-bold uppercase tracking-wider bg-gray-900 text-white shadow-lg shadow-gray-900/10 hover:bg-gray-800 transition-all duration-200">
                  Get Started Free
                  <ArrowRight size={15} />
                </Link>
                <Link href="/login" className="inline-flex items-center gap-2 px-7 py-4 rounded-2xl text-[13px] font-bold uppercase tracking-wider border border-gray-200 text-gray-600 hover:bg-gray-50 hover:border-gray-300 hover:text-gray-900 transition-all duration-200">
                  Sign In
                </Link>
              </>
            )}
            <Link href="/download" className="inline-flex items-center gap-2 px-7 py-4 rounded-2xl text-[13px] font-bold uppercase tracking-wider text-gray-400 hover:text-gray-900 transition-all duration-200">
              <Download size={15} />
              Download APK
            </Link>
          </div>

          <div
            className="mt-5 flex items-center gap-2"
            style={{ animation: 'heroFadeIn 0.7s cubic-bezier(0.16, 1, 0.3, 1) 0.6s both' }}
          >
            <Check size={14} className="text-gray-400" />
            <span className="text-[12px] font-mono font-medium tracking-wide text-gray-400">
              Free for 1 device · No credit card required
            </span>
          </div>

          {/* Stats */}
          <div
            className="mt-14 grid grid-cols-2 sm:grid-cols-4 gap-6 max-w-xl"
            style={{ animation: 'heroFadeIn 0.7s cubic-bezier(0.16, 1, 0.3, 1) 0.8s both' }}
          >
            {HERO_STATS.map((stat) => (
              <div key={stat.label}>
                <div className="text-gray-900 text-xl font-bold font-mono">
                  <AnimatedCounter value={stat.value} prefix={stat.prefix} suffix={stat.suffix} className="text-xl" />
                </div>
                <div className="text-[10px] font-mono text-gray-400 uppercase tracking-wider mt-1 font-semibold">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* ─── Device Status Card — Dark centerpiece ────────────────────── */}
        <div className="relative" style={{ animation: 'heroFadeIn 0.8s cubic-bezier(0.16, 1, 0.3, 1) 0.4s both' }}>
          {/* Shadow behind card */}
          <div className="absolute -inset-6 bg-gray-900/[0.08] rounded-[32px] blur-3xl pointer-events-none" />

          <div className="relative">
            {/* Floating device label */}
            <div className="absolute -top-4 right-4 sm:right-8 px-3.5 py-2 rounded-xl border border-white/10 bg-[#0f172a] shadow-xl shadow-black/20 flex items-center gap-2.5 z-10">
              <span className="relative flex w-2 h-2">
                <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" />
                <span className="relative inline-flex rounded-full w-2 h-2 bg-emerald-400" />
              </span>
              <Smartphone size={11} className="text-white/40" />
              <span className="text-[10px] font-mono font-bold text-white/80">Galaxy S24 · Active</span>
            </div>

            {/* Main Card — DARK */}
            <div className="relative rounded-2xl bg-[#0f172a] shadow-2xl shadow-gray-900/20 overflow-hidden border border-white/[0.06]">
              {/* Card header */}
              <div className="flex items-center justify-between px-5 py-3.5 border-b border-white/[0.06]">
                <div className="flex items-center gap-2.5">
                  <div className="w-7 h-7 rounded-lg bg-white/[0.05] border border-white/[0.08] flex items-center justify-center">
                    <Smartphone size={13} className="text-white/50" />
                  </div>
                  <div>
                    <div className="text-[11px] font-bold text-white tracking-wide">Galaxy S24</div>
                    <div className="text-[8px] font-mono text-white/35 tracking-wider">SM-S921B · ANDROID 14</div>
                  </div>
                </div>
                <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-emerald-500/10 border border-emerald-500/20">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                  <span className="text-[8px] font-mono font-bold text-emerald-400 tracking-wider">ONLINE</span>
                </div>
              </div>

              {/* Telemetry Grid */}
              <div className="grid grid-cols-3 gap-px bg-white/[0.03]">
                <div className="bg-[#0f172a] px-4 py-5 flex flex-col items-center">
                  <div className="w-20 h-20 relative"><BatteryArc /></div>
                  <div className="text-[8px] font-mono text-white/35 tracking-widest mt-1">BATTERY</div>
                </div>
                <div className="bg-[#0f172a] px-4 py-5 flex flex-col">
                  <div className="text-[8px] font-mono text-white/35 tracking-widest mb-2">SIGNAL</div>
                  <div className="flex-1 flex items-end">
                    <div className="w-full h-8"><SignalWave /></div>
                  </div>
                  <div className="flex items-center justify-between mt-1.5">
                    <span className="text-[9px] font-mono text-white/50">-78 dBm</span>
                    <span className="text-[9px] font-mono text-white/30">4G LTE</span>
                  </div>
                </div>
                <div className="bg-[#0f172a] px-4 py-5 flex flex-col">
                  <div className="text-[8px] font-mono text-white/35 tracking-widest mb-2">THREAT</div>
                  <div className="flex-1 flex items-center justify-center">
                    <div className="relative">
                      <div className="text-2xl font-display font-extrabold text-white hero-num-tick">12</div>
                      <div className="text-[7px] font-mono text-white/30 text-center mt-0.5">/ 100</div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5 mt-1">
                    <div className="flex-1 h-1 rounded-full bg-white/[0.06] overflow-hidden">
                      <div className="h-full rounded-full bg-white/40" style={{ width: '12%' }} />
                    </div>
                    <span className="text-[8px] font-mono text-emerald-400/70">SAFE</span>
                  </div>
                </div>
              </div>

              {/* Live Telemetry Bar */}
              <div className="flex items-center gap-4 px-5 py-3 border-t border-white/[0.04] bg-white/[0.01]">
                <div className="flex items-center gap-1.5">
                  <MapPin size={10} className="text-white/30" />
                  <span className="text-[9px] font-mono text-white/50 hero-num-tick">6.5244°N 3.3792°E</span>
                </div>
                <div className="w-px h-3 bg-white/[0.08]" />
                <span className="text-[9px] font-mono text-white/50">38 km/h</span>
                <div className="w-px h-3 bg-white/[0.08]" />
                <span className="text-[9px] font-mono text-white/30 hero-live-blink">● LIVE</span>
                <div className="ml-auto flex items-center gap-1">
                  <Battery size={10} className="text-white/30" />
                  <span className="text-[9px] font-mono text-white/40">87%</span>
                </div>
              </div>

              {/* Event Timeline */}
              <div className="px-5 py-4 border-t border-white/[0.04]">
                <div className="text-[8px] font-mono text-white/35 tracking-widest mb-3">RECENT ACTIVITY</div>
                <ThreatTimeline />
              </div>
            </div>

            {/* Floating recovery chip */}
            <div className="absolute -bottom-3 left-4 sm:left-8 px-3 py-2 rounded-xl border border-white/10 bg-[#0f172a] shadow-xl shadow-black/20 flex items-center gap-2">
              <ShieldCheck size={11} className="text-white/50" />
              <span className="text-[9px] font-mono font-bold text-white/70">Recovery armed · 3 layers</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
