'use client';

import {
  Brain,
  MapPin,
  Camera,
  Radar,
  Zap,
  ShieldCheck,
  Smartphone,
  Lock,
  Eye,
  FileText,
  Users,
  BellRing,
} from 'lucide-react';

const FEATURES = [
  {
    icon: Brain,
    title: 'Sentinel AI',
    description:
      'Intelligent theft detection with false-positive prevention — scores movement, battery drops, and SIM changes in real time.',
    accent: '#E91E8C',
  },
  {
    icon: MapPin,
    title: 'Real-time Tracking',
    description:
      'GPS + network location streamed live to your command center over WebSocket with 3-second telemetry intervals.',
    accent: '#06B6D4',
  },
  {
    icon: Users,
    title: 'Family & Team Circles',
    description:
      'Keep in touch with the people who matter — share live locations with family, coworkers, and trusted circles, all under one account.',
    accent: '#22C55E',
  },
  {
    icon: Camera,
    title: 'Remote Evidence Capture',
    description:
      'Trigger front/rear camera photos and 20-second audio captures remotely, sealed with a SHA-256 chain of custody.',
    accent: '#E91E8C',
  },
  {
    icon: Radar,
    title: 'Geofencing',
    description:
      'Define safe zones and receive instant exit alerts. Perfect for campuses, homes, and vehicle perimeters.',
    accent: '#22C55E',
  },
  {
    icon: Zap,
    title: 'Remote Commands',
    description:
      'Lock the device, trigger a max-volume siren, wipe data, or enter Phantom Mode — all with one click.',
    accent: '#06B6D4',
  },
  {
    icon: ShieldCheck,
    title: 'Phantom Mode',
    description:
      'Hidden operation for stealth tracking. The app runs invisibly with 3-layer background persistence.',
    accent: '#E91E8C',
  },
  {
    icon: Smartphone,
    title: 'Multi-Device Fleet',
    description:
      'One account, many devices. Register every phone, tablet, or vehicle tracker under a single email.',
    accent: '#06B6D4',
  },
  {
    icon: BellRing,
    title: 'Guardian Network',
    description:
      'Community-powered recovery — trusted guardians opt in, get blurred nearby scans, and report sightings to help you find what’s lost.',
    accent: '#22C55E',
  },
  {
    icon: Lock,
    title: 'Device Admin',
    description:
      'Remote lock and wipe via Android Device Policy Manager, plus SIM-change detection that arms theft mode.',
    accent: '#22C55E',
  },
  {
    icon: Eye,
    title: 'Stealth Persistence',
    description:
      'OEM-aware survival layers for Huawei, Xiaomi, Oppo, and Vivo — watchdog alarms, health checks, and wakelock management.',
    accent: '#E91E8C',
  },
  {
    icon: FileText,
    title: 'Forensic Reports',
    description:
      'Generate PDF evidence packages with cryptographic chain of custody, ready for law enforcement.',
    accent: '#06B6D4',
  },
];

export function Features() {
  return (
    <section id="features" className="relative py-24 sm:py-32 scroll-mt-20">
      <div className="max-w-7xl mx-auto px-5 sm:px-8">
        {/* Section header */}
        <div className="max-w-2xl mx-auto text-center mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-white/10 bg-white/[0.03] mb-5">
            <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-white/50">CAPABILITIES</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight text-white">
            One command center for <span className="text-gradient-cyan">what matters</span>
          </h2>
          <p className="mt-4 text-white/45 leading-relaxed">
            Protect the devices you own and stay close to the people you love — from silent background
            tracking and forensic-grade evidence to live circles that keep everyone in sync.
          </p>
        </div>

        {/* Feature grid */}
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map((feature) => (
            <div
              key={feature.title}
              className="group card-glow relative rounded-2xl border border-white/[0.07] bg-white/[0.02] backdrop-blur-xl p-6 overflow-hidden"
            >
              {/* Hover tint */}
              <div
                className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
                style={{ background: `radial-gradient(ellipse at top, ${feature.accent}10 0%, transparent 60%)` }}
              />
              <div
                className="relative w-11 h-11 rounded-xl border border-white/[0.08] bg-white/[0.03] flex items-center justify-center mb-5 group-hover:scale-110 transition-transform duration-300"
              >
                <feature.icon size={20} style={{ color: feature.accent }} />
              </div>
              <h3 className="relative text-white font-bold text-[15px] tracking-tight">{feature.title}</h3>
              <p className="relative mt-2 text-[13px] leading-relaxed text-white/40">{feature.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
