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
import { TiltCard } from '@/components/ui/TiltCard';

const FEATURES = [
  {
    icon: Brain,
    title: 'Theft Detection',
    description:
      'Knows the difference between you and a thief. Spots SIM changes, failed unlocks, and suspicious movement — and alerts you instantly.',
    accent: true,
  },
  {
    icon: MapPin,
    title: 'Live Tracking',
    description:
      'Watch your phone move on the map in real time. Updates every 3 seconds with accurate, street-level coordinates.',
    accent: false,
  },
  {
    icon: Camera,
    title: 'Photo & Audio Evidence',
    description:
      'Remotely trigger the camera and microphone to capture who has your phone — photos and recordings that cannot be altered.',
    accent: false,
  },
  {
    icon: Radar,
    title: 'Safe Zone Alerts',
    description:
      'Set a safe zone around your home or office. Get alerted the moment your phone leaves — and set auto-actions like triggering the siren.',
    accent: false,
  },
  {
    icon: Zap,
    title: 'One-Tap Remote Control',
    description:
      'Lock the screen, blast the siren, capture evidence, or wipe your data — all from the dashboard with one tap.',
    accent: true,
  },
  {
    icon: BellRing,
    title: 'Alerts on Every Channel',
    description:
      'Push, email, and SMS alerts — so you know the moment something happens, even on slow networks. WhatsApp alerting is in development.',
    accent: false,
  },
  {
    icon: Lock,
    title: 'Remote Lock & Wipe',
    description:
      'Lock your phone remotely with a custom message. If it is gone for good, wipe your data to protect your privacy.',
    accent: false,
  },
  {
    icon: Smartphone,
    title: 'Works Offline',
    description:
      'When your phone has no internet, it saves location data and uploads it the moment it reconnects — nothing is lost.',
    accent: false,
  },
  {
    icon: Eye,
    title: 'Works on Any Android',
    description:
      'Huawei, Xiaomi, Oppo, Vivo, Realme — phones that kill most tracking apps. Magneetar was built to survive them.',
    accent: false,
  },
  {
    icon: FileText,
    title: 'Police-Ready Reports',
    description:
      'Generate a PDF with location history, photos, and timeline — evidence you can hand to the police.',
    accent: false,
  },
];

function FeatureCard({ feature }: { feature: typeof FEATURES[0]; index: number }) {
  return (
    <TiltCard className="group rounded-2xl bg-gradient-to-b from-mag-surface to-mag-bg border-mag-border hover:border-emerald-500/20 transition-all duration-400">
      <div className="relative p-6 overflow-hidden">
        {/* Top accent line on hover */}
        <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-emerald-500/0 to-transparent group-hover:via-emerald-500/40 transition-all duration-500" />

        <div className={`w-11 h-11 rounded-xl flex items-center justify-center mb-4 transition-all duration-300 ${
          feature.accent
            ? 'bg-emerald-500/10 border border-emerald-500/20'
            : 'bg-mag-surface border-mag-border group-hover:bg-emerald-500/8 group-hover:border-emerald-500/15'
        }`}>
          <feature.icon size={20} className={`${feature.accent ? 'text-emerald-400' : 'text-mag-text-muted group-hover:text-emerald-400'} transition-colors duration-300`} />
        </div>

        <h3 className="text-mag-text font-bold text-[14px] tracking-tight group-hover:text-emerald-50 transition-colors duration-300">
          {feature.title}
        </h3>
        <p className="mt-2 text-[13px] leading-relaxed text-mag-text-muted group-hover:text-mag-text-dim transition-colors duration-300">
          {feature.description}
        </p>
      </div>
    </TiltCard>
  );
}

export function Features() {
  return (
    <section id="features" className="relative py-28 sm:py-36 bg-gradient-to-b from-gray-950 via-[#060a10] to-gray-950 scroll-mt-20">
      {/* Subtle grid dots */}
      <div className="absolute inset-0 bg-grid-dark bg-[size:24px_24px] opacity-40 pointer-events-none" />

      <div className="relative max-w-7xl mx-auto px-5 sm:px-8">
        <div className="max-w-2xl mx-auto text-center mb-14">
          <div className="badge-dark mb-5 mx-auto w-fit">
            <span>CAPABILITIES</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-mag-text">
            Everything you need to{' '}
            <span className="bg-gradient-to-r from-emerald-400 to-teal-400 bg-clip-text text-transparent">protect your phone</span>
          </h2>
          <p className="mt-4 text-mag-text-muted leading-relaxed max-w-lg mx-auto">
            From the moment it's stolen to the moment you recover it — Magneetar has your back.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map((feature, index) => (
            <FeatureCard key={feature.title} feature={feature} index={index} />
          ))}
        </div>
      </div>
    </section>
  );
}
