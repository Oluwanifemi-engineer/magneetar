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
  Mic,
  Shield,
  Users,
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
    title: 'Download the APK',
    body: 'Tap the button below to download Magneetar. The file is served securely from our official servers.',
  },
  {
    title: 'Allow installation',
    body: 'When Android asks, tap "Settings" and allow "Install unknown apps" for your browser. This is a standard one-time permission.',
  },
  {
    title: 'Open & sign in',
    body: 'Open Magneetar, sign in (or create an account in 30 seconds), and your device is protected.',
  },
  {
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
    <div className="min-h-screen bg-mag-bg text-white overflow-x-hidden">
      <div className="absolute inset-0 landing-vignette pointer-events-none" />
      <div className="absolute inset-0 landing-grid opacity-40 pointer-events-none" />
      <div className="absolute -top-40 left-1/3 w-[600px] h-[400px] rounded-full bg-[#E91E8C]/10 blur-[130px] animate-aurora pointer-events-none" aria-hidden="true" />
      <div className="absolute top-1/3 -right-32 w-[480px] h-[480px] rounded-full bg-[#06B6D4]/8 blur-[120px] animate-aurora pointer-events-none" style={{ animationDelay: '-6s' }} aria-hidden="true" />

      <LandingNav authed={authed} />

      <main className="relative max-w-4xl mx-auto px-5 sm:px-8 pt-16 pb-24">
        <Link href="/" className="inline-flex items-center gap-2 text-[11px] font-mono font-bold tracking-wider text-white/40 hover:text-white transition-colors">
          <ArrowLeft size={13} />
          BACK TO HOME
        </Link>

        {/* Header */}
        <header className="mt-10">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-white/10 bg-white/[0.03] mb-5">
            <Smartphone size={12} className="text-[#06B6D4]" />
            <span className="text-[10px] font-mono font-bold tracking-[0.2em] text-white/50">GET THE APP</span>
          </div>
          <h1 className="text-4xl sm:text-5xl font-display font-extrabold tracking-tight leading-[1.1]">
            Protect your phone<br />
            <span className="text-gradient-primary animate-gradient-x">with Magneetar.</span>
          </h1>
          <p className="mt-5 text-white/45 leading-relaxed max-w-2xl text-[15px]">
            One download. Complete protection. Real-time tracking, remote lock, evidence capture, and theft detection — all in one app.
          </p>
        </header>

        {/* ═══ Download Section ═══ */}
        <section className="mt-10 rounded-2xl border-2 border-[#E91E8C]/30 bg-gradient-to-br from-[#E91E8C]/[0.08] via-[#0d0d14] to-[#06B6D4]/[0.06] p-7 sm:p-9 relative overflow-hidden">
          <div className="absolute -top-20 -right-20 w-48 h-48 rounded-full bg-[#E91E8C]/10 blur-[60px] pointer-events-none" aria-hidden="true" />

          <div className="relative">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-11 h-11 rounded-xl bg-[#E91E8C]/20 border-2 border-[#E91E8C]/40 flex items-center justify-center">
                <ShieldCheck size={22} className="text-[#E91E8C]" />
              </div>
              <div>
                <h2 className="text-lg sm:text-xl font-display font-extrabold tracking-tight text-white">
                  Download Magneetar
                </h2>
                <div className="text-[10px] font-mono text-white/40 uppercase tracking-[0.2em] font-bold">
                  Android 8.0+ • {checksum ? formatBytes(checksum.size_bytes) : '...'} • v{checksum?.version || '...'}
                </div>
              </div>
            </div>

            {/* Feature checklist */}
            <div className="grid sm:grid-cols-2 gap-3 mb-6">
              {[
                { icon: Navigation, text: 'Real-time GPS tracking' },
                { icon: Lock, text: 'Remote lock & alarm' },
                { icon: Trash2, text: 'Remote wipe (factory reset)' },
                { icon: Camera, text: 'Photo & audio evidence capture' },
                { icon: Shield, text: 'Sentinel theft detection' },
                { icon: Users, text: 'Guardian Network recovery' },
              ].map((f) => (
                <div key={f.text} className="flex items-center gap-2.5 text-[12px] text-white/60">
                  <f.icon size={14} className="text-[#06B6D4]/80" />
                  <span>{f.text}</span>
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
              className={`group inline-flex items-center justify-center gap-3 w-full sm:w-auto px-8 py-4 rounded-xl text-[13px] font-bold uppercase tracking-wider bg-gradient-to-r from-[#E91E8C] to-[#06B6D4] text-white shadow-xl shadow-[#E91E8C]/25 hover:shadow-[#E91E8C]/40 hover:brightness-110 transition-all duration-200 active:scale-[0.98] ${minting ? 'opacity-70 cursor-wait' : ''}`}
            >
              <Download size={17} className={`transition-transform group-hover:translate-y-0.5 ${minting ? 'animate-bounce' : ''}`} />
              {minting ? 'Preparing download…' : 'Download Magneetar'}
              <ExternalLink size={14} className="text-white/60" />
            </a>

            {ticketError && (
              <p className="mt-4 text-[12.5px] text-amber-400/80">
                Download temporarily unavailable. Please try again in a moment.
              </p>
            )}

            {/* Trust signals */}
            <div className="mt-5 flex flex-wrap items-center gap-4 text-[11px] text-white/35">
              <div className="flex items-center gap-1.5">
                <ShieldCheck size={12} className="text-emerald-400/60" />
                <span>SHA-256 verified</span>
              </div>
              <div className="flex items-center gap-1.5">
                <Check size={12} className="text-emerald-400/60" />
                <span>No ads, no tracking</span>
              </div>
              <div className="flex items-center gap-1.5">
                <ShieldCheck size={12} className="text-emerald-400/60" />
                <span>Open source</span>
              </div>
            </div>
          </div>
        </section>

        {/* ═══ Install steps ═══ */}
        <section className="mt-10 rounded-2xl border border-white/[0.08] bg-mag-panel/30 p-7 sm:p-9">
          <h2 className="text-lg font-display font-extrabold tracking-tight text-white mb-4">How to install</h2>
          <div className="space-y-3">
            {INSTALL_STEPS.map((step, i) => (
              <div key={step.title} className="flex gap-4 rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 transition-all duration-200 hover:border-white/[0.12]">
                <div className="w-7 h-7 shrink-0 rounded-lg bg-white/[0.05] border border-white/[0.08] flex items-center justify-center font-mono text-[11px] font-bold text-white/60">{i + 1}</div>
                <div>
                  <h3 className="text-white font-bold text-[13px] tracking-tight">{step.title}</h3>
                  <p className="mt-1 text-[12px] leading-relaxed text-white/40">{step.body}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ═══ OEM battery notes ═══ */}
        <section className="mt-14">
          <div className="flex items-center gap-2 mb-2">
            <BatteryCharging size={17} className="text-[#06B6D4]" />
            <h2 className="text-2xl font-display font-extrabold tracking-tight">Keep protection alive</h2>
          </div>
          <p className="mt-2 text-white/45 leading-relaxed text-[14px]">
            Some phone brands need extra settings to keep background apps running. Find your brand below.
          </p>
          <div className="mt-6 grid sm:grid-cols-2 gap-4">
            {OEM_NOTES.map((oem) => (
              <div key={oem.brand} className="rounded-2xl border border-white/[0.07] bg-mag-panel/40 p-6">
                <div className="text-white font-bold text-sm">{oem.brand}</div>
                <ul className="mt-3 space-y-2">
                  {oem.steps.map((s) => (
                    <li key={s} className="flex gap-2.5 text-[12.5px] leading-relaxed text-white/45">
                      <ChevronRight size={13} className="text-[#06B6D4] mt-1 shrink-0" />
                      <span>{s}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

        {/* ═══ What you get ═══ */}
        <section className="mt-14">
          <h2 className="text-2xl font-display font-extrabold tracking-tight">What Magneetar gives you</h2>
          <div className="mt-6 grid sm:grid-cols-3 gap-4">
            {[
              { icon: MapPin, title: 'Live tracking', body: 'Real-time GPS location with turn-by-turn navigation to your device.' },
              { icon: Camera, title: 'Evidence capture', body: 'Remote photo and audio capture with chain of custody for law enforcement.' },
              { icon: ShieldCheck, title: 'Theft detection', body: 'AI-powered detection of movement, SIM swaps, and suspicious activity.' },
            ].map((card) => (
              <div key={card.title} className="rounded-2xl border border-white/[0.07] bg-mag-panel/40 p-6">
                <card.icon size={18} className="text-[#06B6D4]" />
                <div className="mt-4 text-white font-bold text-sm">{card.title}</div>
                <div className="mt-1.5 text-[12.5px] leading-relaxed text-white/45">{card.body}</div>
              </div>
            ))}
          </div>
        </section>

        {/* ═══ Verify ═══ */}
        <section className="mt-14 rounded-2xl border border-white/[0.08] bg-white/[0.02] p-6">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <div className="text-[9px] font-mono text-white/35 tracking-widest font-bold mb-1">SHA-256 CHECKSUM</div>
              {checksum ? (
                <code className="text-[12px] font-mono text-[#22D3EE]/80 break-all">{checksum.sha256}</code>
              ) : (
                <span className="text-[12px] font-mono text-white/30">Loading...</span>
              )}
            </div>
            <button
              onClick={copyChecksum}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] text-[11px] font-mono font-bold text-white/50 hover:text-white hover:border-white/20 transition-colors"
            >
              {copied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
        </section>

        {/* ═══ CTA ═══ */}
        <section className="mt-14 rounded-2xl border border-white/[0.08] bg-gradient-to-br from-[#E91E8C]/[0.06] to-[#06B6D4]/[0.04] p-8 text-center">
          <h2 className="text-xl font-display font-bold tracking-tight">Ready to protect your phone?</h2>
          <p className="mt-2 text-[13.5px] text-white/45 max-w-lg mx-auto">
            Create your account in 30 seconds, then link your device during setup.
          </p>
          <Link href="/signup" className="group mt-6 inline-flex items-center gap-2.5 px-8 py-4 rounded-xl text-[13px] font-bold uppercase tracking-wider bg-gradient-to-r from-[#E91E8C] to-[#06B6D4] text-white shadow-xl shadow-[#E91E8C]/25 hover:shadow-[#E91E8C]/40 hover:brightness-110 transition-all duration-200 active:scale-[0.97]">
            Get started
            <ChevronRight size={15} className="transition-transform group-hover:translate-x-0.5" />
          </Link>
        </section>
      </main>

      <Footer />
    </div>
  );
}
