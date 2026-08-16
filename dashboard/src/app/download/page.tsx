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
  ChevronDown,
} from 'lucide-react';
import { APK_DOWNLOAD_URL, APK_CHECKSUM_URL, SOURCE_TARBALL_URL, SOURCE_CHECKSUM_URL } from '@/lib/utils';
import { pickDownloadUrl } from '@/lib/downloadTicket';
import { Reveal } from '@/hooks/useScrollReveal';

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

// Server tickets live 10 minutes (APK_TICKET_TTL_SECONDS). The button's href
// is pre-minted on page load, so it must be refreshed well inside the TTL —
// otherwise a long-press / open-in-new-tab / returning-to-the-tab hits an
// expired ticket and the server answers 403 "Missing or expired download
// ticket".
const TICKET_REFRESH_MS = 4 * 60 * 1000;

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

const INSTALL_FAQ = [
  {
    q: 'The download won\'t start',
    a: 'Tap Download again — the page mints a fresh secure link every time, and links expire after a few minutes by design. If the page has been open a while, refresh it first so the button gets a fresh link.',
  },
  {
    q: 'Android asks me to allow “Install unknown apps”',
    a: 'That\'s the standard one-time permission for apps outside the Play Store: tap Settings → allow installs from your browser → then Install. Google may also show a “Play Protect” check for sideloaded apps — you can temporarily pause “Scan apps with Play Protect” in Settings → Security, install, then turn it back on. Prefer the Google Play install instead — it has no such prompts (see the banner above).',
  },
  {
    q: 'The app shows OFFLINE on my dashboard',
    a: 'After setup, Magneetar minimizes itself by design (covert mode) — just open the app once more so protection starts. If it still shows offline, check the “Keep protection alive” section above for your phone brand\'s background settings; the device should appear ONLINE within a minute.',
  },
  {
    q: 'How do I know the file is genuine?',
    a: 'The SHA-256 checksum in the Verify section below is the fingerprint of the exact file served — compare it to the downloaded file, and it\'s also printed on this page.',
  },
  {
    q: 'Android says “App not installed”',
    a: 'The downloaded file is fine (it\'s checksum-verified on this page) — the phone is refusing to install over a previous Magneetar, and Magneetar protects itself from removal, so an old install can linger invisibly. Remove it properly, in order: (1) Settings → Security → Device admin apps → Magneetar → Deactivate. (2) Settings → Accessibility → turn OFF “System Update Protection”. (3) Now Settings → Apps → Magneetar → Uninstall. If the app still won\'t uninstall or you can\'t find it, use a PC with adb: adb uninstall com.magneetar.app, then adb install <downloaded.apk> — adb prints the exact reason if anything else is wrong. Also pause Play Protect (and Samsung\'s separate “App security”) during install, and make sure the file is the full 7.5 MB (compare SHA-256 below).',
  },
];

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function SkeletonBlock({ className = '' }: { className?: string }) {
  return (
    <div className={`animate-pulse bg-white/[0.04] rounded-xl ${className}`} />
  );
}

export default function DownloadPage() {
  const [authed, setAuthed] = useState(false);
  const [checksum, setChecksum] = useState<ChecksumInfo | null>(null);
  const [sourceChecksum, setSourceChecksum] = useState<ChecksumInfo | null>(null);
  const [checksumError, setChecksumError] = useState(false);
  const [copied, setCopied] = useState(false);
  const [sourceCopied, setSourceCopied] = useState(false);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [ticketError, setTicketError] = useState(false);
  const [minting, setMinting] = useState(false);
  const [loading, setLoading] = useState(true);

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
    const refresh = () => {
      mintTicket().then((url) => {
        if (!cancelled && url) setDownloadUrl(url);
      });
    };
    refresh();
    // Keep the pre-wired href fresh (see TICKET_REFRESH_MS) and re-mint
    // immediately when the tab regains focus — background tabs freeze timers,
    // so a phone locked for 15 minutes could otherwise leave a dead link.
    const timer = setInterval(refresh, TICKET_REFRESH_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') refresh();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      cancelled = true;
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [mintTicket]);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    fetch(APK_CHECKSUM_URL, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((data: ChecksumInfo) => { if (!cancelled) setChecksum(data); })
      .catch(() => { if (!cancelled) setChecksumError(true); })
      .finally(() => { clearTimeout(timer); setLoading(false); });
    // Source tarball checksum (per-release open source — repo is private).
    fetch(SOURCE_CHECKSUM_URL, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((data: ChecksumInfo) => { if (!cancelled) setSourceChecksum(data); })
      .catch(() => {});
    return () => { cancelled = true; controller.abort(); };
  }, []);

  const copyChecksum = async () => {
    if (!checksum) return;
    try { await navigator.clipboard.writeText(checksum.sha256); setCopied(true); setTimeout(() => setCopied(false), 2000); } catch {}
  };

  const copySourceChecksum = async () => {
    if (!sourceChecksum) return;
    try { await navigator.clipboard.writeText(sourceChecksum.sha256); setSourceCopied(true); setTimeout(() => setSourceCopied(false), 2000); } catch {}
  };

  const handleDownload = async (e: React.MouseEvent<HTMLAnchorElement>) => {
    // Never navigate: some browsers/webviews treat a cross-origin navigation
    // to an attachment URL as a page reload instead of a download (the old
    // `window.location.href` here made the button "act like a refresh" on
    // those devices). A blob download never navigates — same proven pattern
    // as the PDF/CSV exports (lib/api.ts). The anchor's href stays for
    // open-in-new-tab / long-press, which uses the server's native
    // Content-Disposition download.
    e.preventDefault();
    if (minting) return;
    setMinting(true);
    setTicketError(false);
    try {
      // Prefer a freshly minted ticket; fall back to the pre-minted href only
      // while it is still within its 10-minute TTL, so a transient re-mint
      // failure never dead-ends on the server's 403 "Missing or expired
      // download ticket" response.
      const fresh = await mintTicket();
      const target = pickDownloadUrl(fresh, downloadUrl);
      if (!target) { setTicketError(true); return; }
      setDownloadUrl(target);

      const res = await fetch(target);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      // Same display name /apk/download hands the browser (checksum.filename
      // comes from the live /apk/checksum endpoint).
      const filename = checksum?.filename || 'Magneetar-release.apk';
      const objectUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objectUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(objectUrl);
    } catch {
      setTicketError(true);
    } finally {
      setMinting(false);
    }
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

          {/* Quick stats — every claim here is verifiable on this page or in
              the product itself. No fabricated adoption numbers: the checksum
              below proves the APK, tracking is a feature, and the free plan is
              real. Real adoption numbers will appear here when they exist. */}
          <div className="flex items-center justify-center gap-8 mt-8">
            {[
              { label: 'Stealth tracking', value: '24/7' },
              { label: 'Checksum verified', value: 'SHA-256' },
              { label: 'Free plan', value: '1 device' },
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
          {loading && (
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <SkeletonBlock className="w-14 h-14 rounded-2xl" />
                <div className="space-y-2">
                  <SkeletonBlock className="w-48 h-5" />
                  <SkeletonBlock className="w-32 h-3" />
                </div>
              </div>
              <div className="grid sm:grid-cols-2 gap-4">
                {[...Array(6)].map((_, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <SkeletonBlock className="w-8 h-8 rounded-lg" />
                    <SkeletonBlock className="w-32 h-4" />
                  </div>
                ))}
              </div>
              <SkeletonBlock className="w-full sm:w-auto h-14 rounded-2xl" />
            </div>
          )}
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
              onClick={handleDownload}
              className={`btn-premium group inline-flex items-center justify-center gap-3 w-full sm:w-auto px-10 py-5 rounded-2xl text-[14px] font-bold uppercase tracking-wider text-white ${minting ? 'opacity-70 cursor-wait' : ''}`}
            >
              <Download size={18} className={`transition-transform group-hover:translate-y-0.5 ${minting ? 'animate-bounce' : ''}`} />
              {minting ? 'Preparing download…' : 'Download Magneetar'}
              <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" />
            </a>

            {ticketError && (
              <p className="mt-4 text-[13px] text-amber-400/80">
                Download link unavailable — tap Download again for a fresh link.
              </p>
            )}

            {/* Trust signals — every one verifiable on this page */}
            <div className="mt-6 flex flex-wrap items-center gap-6 text-[11px] text-white/30">
              {[
                { icon: ShieldCheck, text: 'SHA-256 verified' },
                { icon: Check, text: 'No ads, no tracking' },
                { icon: Zap, text: 'Source released per version' },
              ].map((item) => (
                <div key={item.text} className="flex items-center gap-2">
                  <item.icon size={12} className="text-[#22C55E]/60" />
                  <span>{item.text}</span>
                </div>
              ))}
            </div>
            <p className="mt-4 text-[11px] text-white/25">
              The source of this exact release is downloadable below —{' '}
              <a href={SOURCE_TARBALL_URL} target="_blank" rel="noopener noreferrer" className="underline hover:text-white/50">
                magneetar-v{checksum?.version || ''}-source.tar.gz
              </a>{' '}
              (SHA-256 verified in the Verify section).
            </p>

          </div>
        </section>

        {/* ═══ Premium Divider ═══ */}
        <div className="divider-premium my-16" />

        {/* ═══ Install Steps ═══ */}
        <Reveal>
          <div className="text-center mb-10">
            <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight">
              How to <span className="text-gradient-primary">install</span>
            </h2>
            <p className="mt-3 text-white/40 text-[15px]">Get protected in under 5 minutes</p>
          </div>

          <div className="mb-8 rounded-xl border border-[#06B6D4]/25 bg-[#06B6D4]/[0.06] p-5">
            <div className="flex items-start gap-3">
              <ShieldCheck size={18} className="text-[#06B6D4] shrink-0 mt-0.5" />
              <div>
                <p className="text-white font-semibold text-[14px]">
                  Google Play install (recommended)
                </p>
                <p className="mt-1 text-[13px] leading-relaxed text-white/50">
                  The Play Store version installs with no prompts — no “Install
                  unknown apps”, no Play Protect block, and automatic updates.
                  We're in private testing right now; join the waitlist and we'll
                  invite you by email. The steps below are the manual fallback
                  for devices that can't use the Play Store.
                </p>
              </div>
            </div>
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
        </Reveal>

        {/* ═══ OEM Battery Notes ═══ */}
        <Reveal delay={100} className="mt-20">
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
        </Reveal>

        {/* ═══ Install FAQ ═══ */}
        <Reveal delay={350} className="mt-20">
          <div className="text-center mb-10">
            <h2 className="text-3xl sm:text-4xl font-display font-extrabold tracking-tight">
              Having trouble <span className="text-gradient-primary">installing?</span>
            </h2>
            <p className="mt-3 text-white/40 text-[15px]">Quick answers for the common hiccups</p>
          </div>

          <div className="max-w-3xl mx-auto space-y-3">
            {INSTALL_FAQ.map((item) => (
              <details
                key={item.q}
                className="group premium-card p-5 open:border-[#06B6D4]/25 open:bg-[#06B6D4]/[0.03] transition-all duration-300"
              >
                <summary className="flex items-center justify-between gap-4 cursor-pointer select-none list-none">
                  <span className="text-[14px] font-bold text-white/80 group-hover:text-white transition-colors">
                    {item.q}
                  </span>
                  <ChevronDown
                    size={16}
                    className="text-white/30 shrink-0 transition-transform duration-300 group-open:rotate-180 group-open:text-[#06B6D4]"
                  />
                </summary>
                <p className="mt-3 text-[13px] leading-relaxed text-white/40">
                  {item.a}
                </p>
              </details>
            ))}
          </div>
        </Reveal>

        {/* ═══ Features Section ═══ */}
        <Reveal delay={200} className="mt-20">
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
        </Reveal>

        {/* ═══ Verify Section ═══ */}
        <Reveal delay={300} className="mt-20 space-y-4">
          <div className="glass-panel rounded-2xl p-6">
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div>
                <div className="text-[10px] font-mono text-white/30 tracking-widest font-bold mb-2">SHA-256 CHECKSUM — APK</div>
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
          </div>

          <div className="glass-panel rounded-2xl p-6">
            <div className="flex items-start justify-between gap-4 flex-wrap">
              <div className="min-w-0">
                <div className="text-[10px] font-mono text-white/30 tracking-widest font-bold mb-2">SOURCE TARBALL — SHA-256 (open source, per release)</div>
                {sourceChecksum ? (
                  <code className="text-[13px] font-mono text-[#22D3EE]/70 break-all">{sourceChecksum.sha256}</code>
                ) : (
                  <span className="text-[13px] font-mono text-white/20">Loading...</span>
                )}
              </div>
              <button
                onClick={copySourceChecksum}
                className="flex items-center gap-2 px-4 py-2 rounded-xl glass-panel text-[12px] font-mono font-bold text-white/50 hover:text-white transition-all duration-300 shrink-0"
              >
                {sourceCopied ? <Check size={14} className="text-[#22C55E]" /> : <Copy size={14} />}
                {sourceCopied ? 'Copied' : 'Copy'}
              </button>
              <a
                href={SOURCE_TARBALL_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 px-4 py-2 rounded-xl glass-panel text-[12px] font-mono font-bold text-white/50 hover:text-white transition-all duration-300 shrink-0"
              >
                <Download size={14} />
                Source (.tar.gz)
              </a>
            </div>
            <p className="mt-3 text-[11px] text-white/25 leading-relaxed">
              The git repository is private; the full source of this exact release ships as a
              tarball so every claim stays verifiable. Compare the hash of your downloaded
              tarball to the one above — they must match.
            </p>
          </div>
        </Reveal>

        {/* ═══ CTA Section ═══ */}
        <Reveal delay={400} className="mt-20 text-center">
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
        </Reveal>
      </main>

      <Footer />
    </div>
  );
}
