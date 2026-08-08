'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { LandingNav } from '@/components/landing/LandingNav';
import { Footer } from '@/components/landing/Footer';
import {
  Download,
  ShieldCheck,
  Smartphone,
  Copy,
  Check,
  BatteryCharging,
  ExternalLink,
  ArrowLeft,
  MapPin,
  Camera,
  ChevronRight,
  Navigation,
  Lock,
  Trash2,
  Shield,
  Users,
  Zap,
  ArrowRight,
} from 'lucide-react';
import { APK_DOWNLOAD_URL, APK_CHECKSUM_URL } from '@/lib/utils';

type ChecksumInfo = {
  filename: string;
  version: string;
  sha256: string;
  size_bytes: number;
};

type TicketInfo = {
  url: string;
  expires_at: string;
};

const APK_TICKET_URL = `${APK_DOWNLOAD_URL.replace('/apk/download', '/apk/ticket')}`;

const INSTALL_STEPS = [
  {
    icon: Download,
    title: 'Download the APK',
    body: 'Tap the button below to download Magneetar. The file is served securely from our official servers.',
  },
  {
    icon: Smartphone,
    title: 'Allow installation',
    body: 'When Android asks, tap "Settings" and allow "Install unknown apps" for your browser. This is a standard one-time permission.',
  },
  {
    icon: Check,
    title: 'Open & sign in',
    body: 'Open Magneetar, sign in (or create an account in 30 seconds), and your device is protected.',
  },
  {
    icon: ShieldCheck,
    title: 'Grant permissions',
    body: 'Allow Location (for tracking) and Notifications (for alerts). Both are revocable anytime.',
  },
];

const OEM_NOTES = [
  {
    brand: 'Xiaomi / Redmi / POCO',
    steps: [
      'Settings → Apps → Magneetar → Battery saver → No restrictions',
      'Settings → Apps → Magneetar → Other permissions → allow Autostart',
      'Recent apps → long-press Magneetar → lock (padlock icon)',
    ],
  },
  {
    brand: 'Huawei / Honor',
    steps: [
      'Phone Manager → App launch → Magneetar → Manage manually → allow all three',
      'Settings → Battery → App launch → disable "Close after screen locked"',
    ],
  },
  {
    brand: 'OPPO / Realme',
    steps: [
      'Settings → Battery → App battery management → Magneetar → Allow background activity',
      'Settings → Apps → Magneetar → Allow auto-launch',
      'Recent apps → swipe down on Magneetar to lock it',
    ],
  },
  {
    brand: 'Vivo / iQOO',
    steps: [
      'Settings → Battery → Background app management → Magneetar → Allow background running',
      'Settings → Apps → Autostart → enable Magneetar',
      'Recent apps → long-press Magneetar → lock',
    ],
  },
];

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DownloadPage() {
  const [authed, setAuthed] = useState(false);
  const [checksum, setChecksum] = useState<ChecksumInfo | null>(null);
  const [checksumError, setChecksumError] = useState(false);
  const [copied, setCopied] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [ticketError, setTicketError] = useState(false);
  const [minting, setMinting] = useState(false);

  useEffect(() => {
    const serverUrl = sessionStorage.getItem('mt_server_url');
    const apiKey = sessionStorage.getItem('mt_api_key');
    setAuthed(Boolean(serverUrl && apiKey));
  }, []);

  const mintTicket = useCallback(async (): Promise<string | null> => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    try {
      const res = await fetch(APK_TICKET_URL, { signal: controller.signal });
      if (!res.ok) return null;
      const data: TicketInfo = await res.json();
      return new URL(data.url, APK_DOWNLOAD_URL).toString();
    } catch {
      return null;
    } finally {
      clearTimeout(timer);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    mintTicket().then((url) => {
      if (!cancelled && url) setDownloadUrl(url);
    });
    return () => { cancelled = true; };
  }, [mintTicket]);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    fetch(APK_CHECKSUM_URL, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((data: ChecksumInfo) => { if (!cancelled) setChecksum(data); })
      .catch(() => { if (!cancelled) setChecksumError(true); })
      .finally(() => clearTimeout(timer));
    return () => { cancelled = true; controller.abort(); };
  }, []);

  const copyChecksum = async () => {
    if (!checksum) return;
    try { await navigator.clipboard.writeText(checksum.sha256); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch {}
  };

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-white overflow-x-hidden">
      {/* Ambient background */}
      <div className="absolute inset-0 landing-vignette pointer-events-none" />
      <div className="absolute inset-0 landing-grid opacity-30 pointer-events-none" />

      {/* Premium ambient orbs */}
      <div className="absolute -top-40 left-1/4 w-[500px] h-[500px] rounded-full bg-[#E91E8C]/[0.07] blur-[150px] animate-aurora pointer-events-none" />
      <div className="absolute top-1/3 -right-40 w-[600px] h-[600px] rounded-full bg-[#06B6D4]/[0.05] blur-[180px] animate-aurora pointer-events-none" style={{ animationDelay: '-8s' }} />
      <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] rounded-full bg-[#E91E8C]/[0.04] blur-[200px] pointer-events-none" />

      <LandingNav authed={authed} />

      <main className="relative max-w-5xl mx-auto px-6 sm:px-8 pt-20 pb-32">
        <Link href="/" className="inline-flex items-center gap-2 text-[11px] font-mono font-bold tracking-wider text-white/30 hover:text-white/60 transition-all duration-300">
          <ArrowLeft size={13} />
          BACK TO HOME
        </Link>

        {/* ═══ Hero Section ═══ */}
        <header className="mt-12 text-center">
          <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full glass-panel mb-6">
            <Smartphone size={12} className="text-[#06B6D4]" />
            <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-white/60">GET THE APP</span>
          </div>

          <h1 className="text-5xl sm:text-6xl lg:text-7xl font-display font-extrabold tracking-tight leading-[1.05]">
            Protect your phone
            <br />
            <span className="text-gradient-primary animate-gradient-x">with Magneetar.</span>
          </h1>

          <p className="mt-6 text-white/40 leading-relaxed max-w-2xl mx-auto text-[16px]">
            One download. Complete protection. Real-time tracking, remote lock, evidence capture, and theft detection — all in one app.
          </p>

          {/* Quick stats */}
          <div className="flex items-center justify-center gap-8 mt-8">
            {[
              { label: 'Active users', value: '10K+' },
              { label: 'Devices protected', value: '25K+' },
              { label: 'Recovery rate', value: '94%' },
            ].map((stat) => (
              <div key={stat.label} className="text-center">
                <div className="text-xl font-bold text-white">{stat.value}</div>
                <div className="text-[10px] font-mono text-white/30 uppercase tracking-wider">{stat.label}</div>
              </div>
            ))}
          </div>
        </header>

        {/* ═══ Download Section ═══ */}
        <section className="mt-16 premium-card p-8 sm:p-10 relative">
          {/* Decorative gradient orb */}
          <div className="absolute -top-32 -right-32 w-64 h-64 rounded-full bg-gradient-to-br from-[#E91E8C]/20 to-[#06B6D4]/20 blur-[80px] pointer-events-none" />

          <div className="relative">
            <div className="flex items-center gap-4 mb-6">
              <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-[#E91E8C]/20 to-[#06B6D4]/20 border border-white/10 flex items-center justify-center">
                <ShieldCheck size={28} className="text-[#E91E8C]" />
              </div>
              <div>
                <h2 className="text-xl sm:text-2xl font-display font-extrabold tracking-tight text-white">
                  Download Magneetar
                </h2>
                <div className="text-[11px] font-mono text-white/40 uppercase tracking-[0.15em] font-bold mt-0.5">
                  Android 8.0+ • {checksum ? formatBytes(checksum.size_bytes) : '...'} • v{checksum?.version || '...'}
                </div>
              </div>
            </div>

            {/* Feature grid */}
            <div className="grid sm:grid-cols-2 gap-4 mb-8">
              {[
                { icon: Navigation, text: 'Real-time GPS tracking', color: 'text-[#06B6D4]' },
                { icon: Lock, text: 'Remote lock & alarm', color: 'text-[#06B6D4]' },
                { icon: Trash2, text: 'Remote wipe (factory reset)', color: 'text-[#06B6D4]' },
                { icon: Camera, text: 'Photo & audio evidence capture', color: 'text-[#06B6D4]' },
                { icon: Shield, text: 'Sentinel theft detection', color: 'text-[#06B6D4]' },
                { icon: Users, text: 'Guardian Network recovery', color: 'text-[#06B6D4]' },
              ].map((f) => (
                <div key={f.text} className="flex items-center gap-3 text-[13px] text-white/60 group">
                  <div className="w-8 h-8 rounded-lg bg-white/[0.03] border border-white/[0.06] flex items-center justify-center group-hover:border-[#06B6D4]/30 group-hover:bg-[#06B6D4]/10 transition-all duration-300">
                    <f.icon size={14} className={f.color} />
                  </div>
                  <span className="group-hover:text-white/80 transition-colors">{f.text}</span>
                </div>
              ))}
            </div>

            {/* Download button */}
            <a
              href={downloadUrl ?? '#'}
              aria-disabled={minting || !downloadUrl}
              onClick={(e) => {
                e.preventDefault();
                if (minting) return;
                setMinting(true);
                setTicketError(false);
                mintTicket().then((url) => {
                  if (url) { setDownloadUrl(url); window.location.href = url; }
                  else { setTicketError(true); }
                }).finally(() => setMinting(false));
              }}
              className={`btn-premium group inline-flex items-center justify-center gap-3 w-full sm:w-auto px-10 py-5 rounded-2xl text-[14px] font-bold uppercase tracking-wider text-white ${minting ? 'opacity-70 cursor-wait' : ''}`}
            >
              <Download size={18} className={`transition-transform group-hover:translate-y-0.5 ${minting ? 'animate-bounce' : ''}`} />
              {minting ? 'Preparing download…' : 'Download Magneetar'}
              <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" />
            </a>

            {ticketError && (
              <p className="mt-4 text-[13px] text-amber-400/80">
                Download temporarily unavailable. Please try again in a moment.
              </p>
            )}

            {/* Trust signals */}
            <div className="mt-6 flex flex-wrap items-center gap-6 text-[11px] text-white/30">
              {[
                { icon: ShieldCheck, text: 'SHA-256 verified' },
                { icon: Check, text: 'No ads, no tracking' },
                { icon: Zap, text: 'Open source' },
              ].map((item) => (
                <div key={item.text} className="flex items-center gap-2">
                  <item.icon size={12} className="text-[#22C55E]/60" />
                  <span>{item.text}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ═══ Premium Divider ═══ */}
        <div className="divider-premium my-16" />

        {/* ═══ Install Steps ═══ */}
        <section>
          <div className="text-center mb-10">
            <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight">
              How to <span className="text-gradient-primary">install</span>
            </h2>
            <p className="mt-3 text-white/40 text-[15px]">Get protected in under 5 minutes</p>
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            {INSTALL_STEPS.map((step, i) => (
              <div key={step.title} className="premium-card p-6 group cursor-default">
                <div className="flex items-start gap-4">
                  <div className="w-10 h-10 shrink-0 rounded-xl bg-gradient-to-br from-[#E91E8C]/20 to-[#06B6D4]/20 border border-white/[0.08] flex items-center justify-center group-hover:border-[#E91E8C]/30 transition-all duration-300">
                    <step.icon size={18} className="text-white/60 group-hover:text-white/80 transition-colors" />
                  </div>
                  <div>
                    <h3 className="text-white font-bold text-[14px] tracking-tight">{step.title}</h3>
                    <p className="mt-1.5 text-[13px] leading-relaxed text-white/40">{step.body}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ═══ OEM Battery Notes ═══ */}
        <section className="mt-20">
          <div className="text-center mb-10">
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full glass-panel mb-4">
              <BatteryCharging size={14} className="text-[#06B6D4]" />
              <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-white/50">OPTIMIZE</span>
            </div>
            <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight">
              Keep protection <span className="text-gradient-primary">alive</span>
            </h2>
            <p className="mt-3 text-white/40 text-[15px] max-w-xl mx-auto">
              Some phone brands need extra settings to keep background apps running
            </p>
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            {OEM_NOTES.map((oem) => (
              <div key={oem.brand} className="premium-card p-6">
                <div className="text-white font-bold text-[15px] mb-3">{oem.brand}</div>
                <ul className="space-y-2.5">
                  {oem.steps.map((s) => (
                    <li key={s} className="flex gap-3 text-[13px] leading-relaxed text-white/40">
                      <ChevronRight size={14} className="text-[#06B6D4] mt-0.5 shrink-0" />
                      <span>{s}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

        {/* ═══ Features Section ═══ */}
        <section className="mt-20">
          <div className="text-center mb-10">
            <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight">
              What Magneetar <span className="text-gradient-primary">gives you</span>
            </h2>
          </div>

          <div className="grid sm:grid-cols-3 gap-4">
            {[
              { icon: MapPin, title: 'Live tracking', body: 'Real-time GPS location with turn-by-turn navigation to your device.', color: '#06B6D4' },
              { icon: Camera, title: 'Evidence capture', body: 'Remote photo and audio capture with chain of custody for law enforcement.', color: '#E91E8C' },
              { icon: ShieldCheck, title: 'Theft detection', body: 'AI-powered detection of movement, SIM swaps, and suspicious activity.', color: '#22C55E' },
            ].map((card) => (
              <div key={card.title} className="premium-card p-7 group cursor-default">
                <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-white/[0.05] to-white/[0.02] border border-white/[0.08] flex items-center justify-center mb-4 group-hover:border-white/[0.15] transition-all duration-300">
                  <card.icon size={22} style={{ color: card.color }} />
                </div>
                <div className="text-white font-bold text-[15px] mb-2">{card.title}</div>
                <div className="text-[13px] leading-relaxed text-white/40">{card.body}</div>
              </div>
            ))}
          </div>
        </section>

        {/* ═══ Verify Section ═══ */}
        <section className="mt-20 glass-panel rounded-2xl p-6">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <div className="text-[10px] font-mono text-white/30 tracking-widest font-bold mb-2">SHA-256 CHECKSUM</div>
              {checksum ? (
                <code className="text-[13px] font-mono text-[#22D3EE]/70 break-all">{checksum.sha256}</code>
              ) : (
                <span className="text-[13px] font-mono text-white/20">Loading...</span>
              )}
            </div>
            <button
              onClick={copyChecksum}
              className="flex items-center gap-2 px-4 py-2 rounded-xl glass-panel text-[12px] font-mono font-bold text-white/50 hover:text-white transition-all duration-300"
            >
              {copied ? <Check size={14} className="text-[#22C55E]" /> : <Copy size={14} />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
        </section>

        {/* ═══ CTA Section ═══ */}
        <section className="mt-20 text-center">
          <div className="premium-card p-12 relative overflow-hidden">
            {/* Decorative gradient */}
            <div className="absolute inset-0 bg-gradient-to-br from-[#E91E8C]/[0.08] via-transparent to-[#06B6D4]/[0.08] pointer-events-none" />

            <div className="relative">
              <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight">
                Ready to protect <span className="text-gradient-primary">your phone?</span>
              </h2>
              <p className="mt-4 text-white/40 text-[15px] max-w-lg mx-auto">
                Create your account in 30 seconds, then link your device during setup.
              </p>
              <Link href="/signup" className="btn-premium mt-8 inline-flex items-center gap-3 px-10 py-5 rounded-2xl text-[14px] font-bold uppercase tracking-wider text-white">
                Get started
                <ArrowRight size={16} />
              </Link>
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
}
