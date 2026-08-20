'use client';

import { useState } from 'react';
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
  },
  {
    icon: MapPin,
    title: 'Real-time Tracking',
    description:
      'GPS + network location streamed live to your command center over WebSocket with 3-second telemetry intervals.',
  },
  {
    icon: Users,
    title: 'Family & Team Circles',
    description:
      'Keep in touch with the people who matter — share live locations with family, coworkers, and trusted circles, all under one account.',
  },
  {
    icon: Camera,
    title: 'Remote Evidence Capture',
    description:
      'Trigger front/rear camera photos and 20-second audio captures remotely, sealed with a SHA-256 chain of custody.',
  },
  {
    icon: Radar,
    title: 'Geofencing',
    description:
      'Define safe zones and receive instant exit alerts. Perfect for campuses, homes, and vehicle perimeters.',
  },
  {
    icon: Zap,
    title: 'Remote Commands',
    description:
      'Lock the device, trigger a max-volume siren, wipe data, or enter Phantom Mode — all with one click.',
  },
  {
    icon: ShieldCheck,
    title: 'Phantom Mode',
    description:
      'Hidden operation for stealth tracking. The app runs invisibly with 3-layer background persistence.',
  },
  {
    icon: Smartphone,
    title: 'Multi-Device Fleet',
    description:
      'One account, many devices. Register every phone, tablet, or vehicle tracker under a single email.',
  },
  {
    icon: BellRing,
    title: 'Guardian Network',
    description:
      'Community-powered recovery — trusted guardians opt in, get blurred nearby scans, and report sightings to help you find what\'s lost.',
  },
  {
    icon: Lock,
    title: 'Device Admin',
    description:
      'Remote lock and wipe via Android Device Policy Manager, plus SIM-change detection that arms theft mode.',
  },
  {
    icon: Eye,
    title: 'Stealth Persistence',
    description:
      'OEM-aware survival layers for Huawei, Xiaomi, Oppo, and Vivo — watchdog alarms, health checks, and wakelock management.',
  },
  {
    icon: FileText,
    title: 'Forensic Reports',
    description:
      'Generate PDF evidence packages with cryptographic chain of custody, ready for law enforcement.',
  },
];

function FeatureCard({ feature }: { feature: typeof FEATURES[0]; index: number }) {
  return (
    <div className="group relative p-7 rounded-2xl bg-white shadow-[0_1px_3px_rgba(0,0,0,0.04),0_4px_12px_rgba(0,0,0,0.03)] hover:shadow-[0_8px_30px_rgba(0,0,0,0.08)] hover:-translate-y-1 transition-all duration-300 cursor-default overflow-hidden">
      {/* Bottom accent line on hover */}
      <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-gray-900 scale-x-0 group-hover:scale-x-100 transition-transform duration-500 origin-left" />
      <div className="w-12 h-12 rounded-xl bg-gray-50 border border-gray-100 flex items-center justify-center mb-5 group-hover:scale-110 group-hover:bg-gray-900 group-hover:border-gray-900 transition-all duration-300">
        <feature.icon size={22} className="text-gray-700 group-hover:text-white transition-colors duration-300" />
      </div>
      <h3 className="text-gray-900 font-bold text-[15px] tracking-tight group-hover:translate-x-1 transition-transform duration-300">
        {feature.title}
      </h3>
      <p className="mt-2.5 text-[13px] leading-relaxed text-gray-500 group-hover:text-gray-600 transition-colors duration-300">
        {feature.description}
      </p>
    </div>
  );
}

export function Features() {
  return (
    <section id="features" className="relative py-32 sm:py-40 bg-white scroll-mt-20">
      <div className="max-w-7xl mx-auto px-5 sm:px-8">
        <div className="max-w-2xl mx-auto text-center mb-16">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-gray-200 bg-white mb-5">
            <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-gray-500">CAPABILITIES</span>
          </div>
          <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight text-gray-900">
            One command center for <span className="text-gray-400">what matters</span>
          </h2>
          <p className="mt-4 text-gray-500 leading-relaxed">
            Protect the devices you own and stay close to the people you love — from silent background
            tracking and forensic-grade evidence to live circles that keep everyone in sync.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map((feature, index) => (
            <FeatureCard key={feature.title} feature={feature} index={index} />
          ))}
        </div>
      </div>
    </section>
  );
}
