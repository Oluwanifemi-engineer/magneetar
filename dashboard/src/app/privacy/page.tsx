'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { LandingNav } from '@/components/landing/LandingNav';
import { Footer } from '@/components/landing/Footer';
import {
  ShieldCheck,
  Radar,
  Camera,
  MapPin,
  Database,
  Lock,
  Users,
  FileText,
  ArrowLeft,
  CheckCircle2,
} from 'lucide-react';

const SECTIONS = [
  {
    icon: Database,
    title: '1. Information We Collect',
    body: [
      'Account data: email address, display name, and a securely-hashed password (bcrypt) when you create an account.',
      'Device telemetry: location coordinates, speed, battery level, network type, signal strength, and sensor-derived context from devices you register and authorize.',
      'Evidence media: photos and audio captured by your device during an active theft response, stored with a SHA-256 hash chain for tamper-evident integrity.',
      'Device identifiers: hashed device keys, SIM serial hashes, and app/OS versions used solely to bind your account to your devices and to detect SIM swaps.',
      'Guardian Network data: an optional public handle, search radius, and sighting reports you submit when you volunteer as a guardian.',
    ],
  },
  {
    icon: Radar,
    title: '2. How We Use Your Data',
    body: [
      'Delivering the anti-theft service: theft detection (Sentinel AI), real-time tracking, geofencing, remote lock/wipe commands, and evidence capture.',
      'Community recovery: when you opt in as a Guardian, active recovery requests within your radius are shown with blurred locations. Your identity is never exposed to owners — only your chosen handle.',
      'Sending alerts via the channels you configure (SMS, WhatsApp, email, or push notifications) when theft or geofence events occur.',
      'Improving reliability: anonymized operational metrics and error reports (optionally via Sentry crash reporting) to keep the service stable.',
    ],
  },
  {
    icon: MapPin,
    title: '3. Location Data & Permissions',
    body: [
      'Magneetar only tracks devices you own or have been explicitly granted access to. Tracking is off until you activate it for a registered device.',
      'Foreground location is used for live tracking while the app is open; background location is used only to maintain theft detection when the app is closed — a core capability of the service you enable explicitly.',
      'Location history is retained for a limited period (default 90 days) and automatically purged. You can delete a device and its history at any time.',
      'You can revoke location permissions at any time through your device settings; this disables tracking but also disables theft detection.',
    ],
  },
  {
    icon: Camera,
    title: '4. Evidence Capture',
    body: [
      'When theft is detected, Magneetar may capture photos and audio to build an evidence case for recovery and law enforcement.',
      'Evidence is encrypted in transit and stored with a SHA-256 chain of custody so it can be presented as forensic material.',
      'Evidence is only attached to an active evidence case for your own device and is never shared publicly — it appears only in your command center.',
      'You can purge evidence cases permanently from the dashboard.',
    ],
  },
  {
    icon: Users,
    title: '5. Guardian Network & Community Recovery',
    body: [
      'Opt-in only: you are never a Guardian unless you explicitly enable it. Likewise, launching a recovery request is always your choice.',
      'Privacy by blur: guardians see a blurred area (not the exact location) of an active recovery request, plus the device model and your chosen description.',
      'Anonymity: guardians are identified by their handle only. Owners never see guardian account details, and guardians never see owner identities.',
      'Data minimization: sighting reports contain a coordinate, a note, and your handle — nothing else. You can withdraw from the Guardian Network at any time.',
    ],
  },
  {
    icon: Lock,
    title: '6. Data Security',
    body: [
      'Transport: all traffic is TLS-encrypted in production (HTTPS). Passwords are hashed with bcrypt. Device keys are stored as SHA-256 hashes.',
      'Tokens: session and device tokens are short-lived JWTs with refresh rotation and revocation support.',
      'Access: the dashboard is protected by per-user authentication; device data is scoped to its owner.',
      'We do not sell your data. We do not share your data with third parties except as needed to operate the service (e.g., your chosen alert providers).',
    ],
  },
  {
    icon: FileText,
    title: '7. Your Rights & Controls',
    body: [
      'Export: request a copy of your account data at any time.',
      'Deletion: delete your account or any individual device and its history from the dashboard — deletion is permanent.',
      'Correction: update your display name, alert recipients, and device aliases at any time.',
      'Withdrawal: revoke Guardian Network participation, stop background tracking, or disable alerts with a single toggle.',
      'Contact: privacy@magneetar.me for any privacy request or question. We respond within 30 days.',
    ],
  },
];

export default function PrivacyPage() {
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    const serverUrl = sessionStorage.getItem('mt_server_url');
    const apiKey = sessionStorage.getItem('mt_api_key');
    setAuthed(Boolean(serverUrl && apiKey));
  }, []);

  return (
    <div className="min-h-screen bg-white text-gray-900 overflow-x-hidden">
      {/* Ambient background */}
      <div className="absolute inset-0 landing-vignette pointer-events-none" />
      <div className="absolute inset-0 landing-grid opacity-40 pointer-events-none" />
      <div className="absolute -top-40 left-1/3 w-[600px] h-[400px] rounded-full bg-[#FFFFFF]/10 blur-[130px] animate-aurora pointer-events-none" aria-hidden="true" />
      <div className="absolute top-1/3 -right-32 w-[480px] h-[480px] rounded-full bg-[#06B6D4]/8 blur-[120px] animate-aurora pointer-events-none" style={{ animationDelay: '-6s' }} aria-hidden="true" />

      <LandingNav authed={authed} />

      <main className="relative max-w-4xl mx-auto px-5 sm:px-8 pt-16 pb-24">
        {/* Back link */}
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-[11px] font-mono font-bold tracking-wider text-gray-400 hover:text-gray-900 transition-colors"
        >
          <ArrowLeft size={13} />
          BACK TO HOME
        </Link>

        {/* Header */}
        <header className="mt-10">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-gray-200 bg-gray-50 mb-5">
            <ShieldCheck size={12} className="text-gray-900" />
            <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-gray-500">PRIVACY POLICY</span>
          </div>
          <h1 className="text-4xl sm:text-5xl font-display font-extrabold tracking-tight leading-[1.1]">
            Your data.
            <br />
            <span className="text-gray-400">Under your command.</span>
          </h1>
          <p className="mt-5 text-gray-500 leading-relaxed max-w-2xl text-[15px]">
            Magneetar protects devices — and the people who own them. This policy explains what we collect,
            why we collect it, and the controls you have over your information. It applies to the Magneetar
            Android app, the web command center, and the Magneetar API.
          </p>

          <div className="mt-6 flex flex-wrap items-center gap-4">
            <span className="px-3 py-1.5 rounded-lg border border-gray-200 bg-gray-50 text-[10px] font-mono text-gray-400">
              EFFECTIVE · AUGUST 1, 2026
            </span>
            <span className="px-3 py-1.5 rounded-lg border border-gray-200 bg-gray-50 text-[10px] font-mono text-gray-400">
              VERSION 1.0
            </span>
            <span className="px-3 py-1.5 rounded-lg border border-emerald-500/20 bg-emerald-500/[0.05] text-[10px] font-mono font-bold text-emerald-300 flex items-center gap-1.5">
              <CheckCircle2 size={11} />
              GDPR-ALIGNED CONTROLS
            </span>
          </div>
        </header>

        {/* Sections */}
        <div className="mt-14 space-y-5">
          {SECTIONS.map((section, i) => (
            <section
              key={section.title}
              className="group rounded-2xl border border-gray-200 bg-white  p-7 sm:p-8 transition-all duration-300 hover:border-gray-300 hover:bg-gray-50"
              style={{ animationDelay: `${i * 0.04}s` }}
            >
              <div className="flex items-start gap-4">
                <div className="w-10 h-10 shrink-0 rounded-xl border border-gray-200 bg-gray-50 flex items-center justify-center">
                  <section.icon size={17} className="text-gray-900" />
                </div>
                <div className="flex-1">
                  <h2 className="text-lg font-display font-bold tracking-tight text-gray-900">{section.title}</h2>
                  <ul className="mt-4 space-y-3">
                    {section.body.map((point) => (
                      <li key={point} className="flex gap-3 text-[13.5px] leading-relaxed text-gray-500">
                        <span className="mt-[7px] w-1.5 h-1.5 shrink-0 rounded-full bg-gradient-to-r from-[#FFFFFF] to-[#06B6D4]" aria-hidden="true" />
                        <span>{point}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </section>
          ))}
        </div>

        {/* Contact block */}
        <div className="mt-12 rounded-2xl border border-[#FFFFFF]/20 bg-gradient-to-br from-[#FFFFFF]/[0.06] to-[#06B6D4]/[0.04] p-8 text-center">
          <Lock size={20} className="mx-auto text-[#FFFFFF]" />
          <h2 className="mt-3 text-xl font-display font-bold tracking-tight">Questions about your privacy?</h2>
          <p className="mt-2 text-[13.5px] text-gray-500 max-w-lg mx-auto">
            Email our data protection contact at{' '}
            <a href="mailto:privacy@magneetar.me" className="text-gray-900 hover:text-[#22D3EE] font-semibold transition-colors">
              privacy@magneetar.me
            </a>{' '}
            — we respond to every privacy request within 30 days.
          </p>
        </div>
      </main>

      <Footer />
    </div>
  );
}
