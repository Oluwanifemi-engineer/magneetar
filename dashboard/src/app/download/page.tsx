'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { LandingNav } from '@/components/landing/LandingNav';
import { Footer } from '@/components/landing/Footer';
import {
  Download,
  ShieldCheck,
  ShieldAlert,
  Smartphone,
  Copy,
  Check,
  AlertTriangle,
  BatteryCharging,
  TerminalSquare,
  ExternalLink,
  ArrowLeft,
  MapPin,
  Camera,
  FileCheck,
  ChevronRight,
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
    body: 'Tap the green button above to download the official Magneetar APK. It is served over HTTPS from the same host as the API — never install Magneetar from third-party mirrors or WhatsApp forwards.',
  },
  {
    title: 'Allow installs from this source',
    body: 'When Android blocks the install, tap "Settings" on the prompt and allow "Install unknown apps" for the browser you downloaded with. On Android 13+, Android asks for this permission per-app the first time — that is expected.',
  },
  {
    title: 'Open & sign in',
    body: 'Open Magneetar, sign in with your account (or create one in 30 seconds), then link this device to your account. A notification appears confirming "Magneetar is protecting this device" — that is the honest price of background theft detection.',
  },
  {
    title: 'Grant the two critical permissions',
    body: 'Location — choose "Allow all the time" so theft detection keeps working when the app is closed. Notifications — required for theft alerts, offline detection, and command results. Both are revocable anytime.',
  },
  {
    title: 'Pause battery optimization for the app',
    body: 'Aggressive Android battery killers can stop background protection. Use the OEM guide below to keep Magneetar alive in the background on your brand of phone.',
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
      'Phone Manager (or Settings) → App launch → Magneetar → Manage manually → allow all three (Auto-launch, Secondary launch, Run in background)',
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

  // The download endpoint is gated behind a short-lived signed ticket
  // (rate-limited per IP) so the APK can't be hotlinked or scraped in bulk.
  // Mint a fresh signed ticket; used on mount (pre-warm the button) and on
  // every click (a ticket only lives 10 minutes — a user who waits on the
  // page past the TTL must get a working link, never a 403).
  //
  // The fetch aborts after 8s so a hung network can never leave the button
  // stuck on "Preparing download…" — a stalled mint fails fast and surfaces
  // the retry hint instead (regression: the old click path had no timeout).
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
    return () => {
      cancelled = true;
    };
  }, [mintTicket]);

  useEffect(() => {
    let cancelled = false;
    // Abort after 8s so a stalled API host can't leave the checksum spinner
    // spinning forever — the download itself is still offered either way.
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);

    fetch(APK_CHECKSUM_URL, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then((data: ChecksumInfo) => {
        if (!cancelled) setChecksum(data);
      })
      .catch(() => {
        if (!cancelled) setChecksumError(true);
      })
      .finally(() => clearTimeout(timer));
    return () => {
      cancelled = true;
      controller.abort();
      clearTimeout(timer);
    };
  }, []);

  const copyChecksum = async () => {
    if (!checksum) return;
    try {
      await navigator.clipboard.writeText(checksum.sha256);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard unavailable (older browsers / non-secure context) — no-op.
    }
  };

  return (
    <div className="min-h-screen bg-mag-bg text-white overflow-x-hidden">
      {/* Ambient background */}
      <div className="absolute inset-0 landing-vignette pointer-events-none" />
      <div className="absolute inset-0 landing-grid opacity-40 pointer-events-none" />
      <div className="absolute -top-40 left-1/3 w-[600px] h-[400px] rounded-full bg-[#E91E8C]/10 blur-[130px] animate-aurora pointer-events-none" aria-hidden="true" />
      <div className="absolute top-1/3 -right-32 w-[480px] h-[480px] rounded-full bg-[#06B6D4]/8 blur-[120px] animate-aurora pointer-events-none" style={{ animationDelay: '-6s' }} aria-hidden="true" />

      <LandingNav authed={authed} />

      <main className="relative max-w-4xl mx-auto px-5 sm:px-8 pt-16 pb-24">
        {/* Back link */}
        <Link
          href="/"
          className="inline-flex items-center gap-2 text-[11px] font-mono font-bold tracking-wider text-white/40 hover:text-white transition-colors"
        >
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
            Put Magneetar
            <br />
            <span className="text-gradient-primary animate-gradient-x">on your phone.</span>
          </h1>
          <p className="mt-5 text-white/45 leading-relaxed max-w-2xl text-[15px]">
            One download, five minutes of setup, and every phone you own is protected. Android 8.0+
            required. This guide covers sideloading the official APK — including how to verify the file
            you downloaded is really ours.
          </p>
        </header>

        {/* ─── Download card ─────────────────────────────────────────────── */}
        <section className="mt-12 rounded-2xl border border-white/[0.08] bg-gradient-to-br from-[#E91E8C]/[0.07] via-[#0d0d14] to-[#06B6D4]/[0.06] p-7 sm:p-9">
          <div className="flex items-start gap-2">
            <ShieldCheck size={16} className="text-emerald-400 mt-0.5 shrink-0" />
            <p className="text-[13px] text-white/55 leading-relaxed">
              The APK below is the official Magneetar release, signed with our release key and served over
              TLS from <span className="font-mono text-white/70">api.magneetar.me</span>.
            </p>
          </div>

          <a
            href={downloadUrl ?? '#'}
            aria-disabled={minting || !downloadUrl}
            onClick={(e) => {
              // NEVER fall back to the bare /apk/download URL: that endpoint
              // requires a signed ticket and returns 403 without one (the bug
              // that made this button error for users). Every click mints a
              // FRESH ticket (TTL is 10 minutes) and navigates only on
              // success; a failure shows a retry hint instead of a dead end.
              e.preventDefault();
              if (minting) return;
              setMinting(true);
              setTicketError(false);
              mintTicket().then((url) => {
                if (url) {
                  setDownloadUrl(url);
                  window.location.href = url;
                } else {
                  setTicketError(true);
                }
              }).finally(() => setMinting(false));
            }}
            className={"group mt-7 inline-flex items-center justify-center gap-3 w-full sm:w-auto px-8 py-4 rounded-xl text-[13px] font-bold uppercase tracking-wider bg-gradient-to-r from-[#E91E8C] to-[#06B6D4] text-white shadow-xl shadow-[#E91E8C]/25 hover:shadow-[#E91E8C]/40 hover:brightness-110 transition-all duration-200 active:scale-[0.98] " + (minting ? 'opacity-70 cursor-wait' : '')}
          >
            <Download size={17} className={"transition-transform group-hover:translate-y-0.5 " + (minting ? 'animate-bounce' : '')} />
            {minting ? 'Preparing download…' : 'Download the APK (direct)'}
            <ExternalLink size={14} className="text-white/60" />
          </a>

          {ticketError && (
            <div className="mt-4 flex items-start gap-2">
              <AlertTriangle size={15} className="text-amber-400 mt-0.5 shrink-0" />
              <p className="text-[12.5px] text-white/45 leading-relaxed">
                Couldn&apos;t fetch a download ticket just now — the server may be mid-deploy or rate-limiting
                this network. Tap the button again in a moment to retry.
              </p>
            </div>
          )}

          {/* Checksum / metadata */}
          <div className="mt-7 rounded-xl border border-white/[0.07] bg-black/30 p-5">
            {checksum ? (
              <div className="grid gap-4 sm:grid-cols-3">
                <div>
                  <div className="text-[9px] font-mono text-white/35 tracking-widest font-bold mb-1.5">VERSION</div>
                  <div className="text-white text-sm font-bold font-mono">v{checksum.version}</div>
                </div>
                <div>
                  <div className="text-[9px] font-mono text-white/35 tracking-widest font-bold mb-1.5">SIZE</div>
                  <div className="text-white text-sm font-bold font-mono">{formatBytes(checksum.size_bytes)}</div>
                </div>
                <div>
                  <div className="text-[9px] font-mono text-white/35 tracking-widest font-bold mb-1.5">FILE</div>
                  <div className="text-white text-sm font-bold font-mono truncate" title={checksum.filename}>
                    {checksum.filename}
                  </div>
                </div>
                <div className="sm:col-span-3">
                  <div className="flex items-center justify-between gap-3 mb-1.5">
                    <div className="text-[9px] font-mono text-white/35 tracking-widest font-bold">SHA-256 CHECKSUM</div>
                    <button
                      onClick={copyChecksum}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-white/[0.08] bg-white/[0.03] text-[10px] font-mono font-bold text-white/60 hover:text-white hover:border-white/20 transition-colors"
                      aria-label="Copy SHA-256 checksum"
                    >
                      {copied ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}
                      {copied ? 'COPIED' : 'COPY'}
                    </button>
                  </div>
                  <code className="block text-[11px] sm:text-[12px] font-mono text-[#22D3EE]/90 leading-relaxed break-all bg-white/[0.03] border border-white/[0.06] rounded-lg px-3 py-2.5">
                    {checksum.sha256}
                  </code>
                </div>
              </div>
            ) : checksumError ? (
              <div className="flex items-start gap-2">
                <AlertTriangle size={15} className="text-amber-400 mt-0.5 shrink-0" />
                <p className="text-[12.5px] text-white/45 leading-relaxed">
                  Checksum unavailable right now — the server may be mid-deploy. Download the APK, then
                  verify it later against{' '}
                  <span className="font-mono text-white/60">{APK_CHECKSUM_URL}</span>.
                </p>
              </div>
            ) : (
              <div className="flex items-center gap-3">
                <div className="w-4 h-4 rounded-full border-2 border-white/15 border-t-[#06B6D4] animate-spin" />
                <span className="text-[12px] font-mono text-white/40">FETCHING CHECKSUM…</span>
              </div>
            )}
          </div>
        </section>

        {/* ─── Play Protect warning guide ────────────────────────────────── */}
        <section className="mt-14 rounded-2xl border border-amber-500/20 bg-amber-500/[0.04] p-7 sm:p-9">
          <div className="flex items-center gap-2">
            <ShieldAlert size={17} className="text-amber-400" />
            <h2 className="text-xl font-display font-extrabold tracking-tight">
              Android says &ldquo;Play Protect blocked this app&rdquo;?
            </h2>
          </div>
          <p className="mt-3 text-[13.5px] leading-relaxed text-white/50">
            That warning is expected for Magneetar today — it is a generic caution Android shows for{' '}
            <span className="text-white font-semibold">any</span> app installed from outside the Play
            Store that requests sensitive permissions. It is not a malware detection. Here is why it
            appears and how to proceed safely.
          </p>

          <div className="mt-6 space-y-4">
            <div className="flex gap-3">
              <span className="mt-[7px] w-1.5 h-1.5 shrink-0 rounded-full bg-amber-400/80" aria-hidden="true" />
              <div className="text-[13.5px] leading-relaxed text-white/50">
                <span className="text-white font-semibold">Why the warning appears:</span> Magneetar needs
                the same permissions spyware abuses — SMS (for offline theft commands when a stolen phone
                has no data), Device Admin (so a thief can&apos;t uninstall it), and background location (theft
                detection). Because those permissions are abused by real malware, Google warns about them
                on every sideloaded install, regardless of whether the app is legitimate.
              </div>
            </div>
            <div className="flex gap-3">
              <span className="mt-[7px] w-1.5 h-1.5 shrink-0 rounded-full bg-amber-400/80" aria-hidden="true" />
              <div className="text-[13.5px] leading-relaxed text-white/50">
                <span className="text-white font-semibold">What to do:</span> tap{' '}
                <span className="font-mono text-white/80">More details</span>, review the list, then tap{' '}
                <span className="font-mono text-white/80">Install anyway</span>. On some Android versions
                the &ldquo;Install anyway&rdquo; button only appears after you open &ldquo;More details&rdquo;. The warning
                disappears entirely once the app ships on the Play Store.
              </div>
            </div>
            <div className="flex gap-3">
              <span className="mt-[7px] w-1.5 h-1.5 shrink-0 rounded-full bg-amber-400/80" aria-hidden="true" />
              <div className="text-[13.5px] leading-relaxed text-white/50">
                <span className="text-white font-semibold">Install only after verifying:</span> confirm the
                downloaded file&apos;s SHA-256 matches the value shown in the card above, and that the APK
                comes from this page (never WhatsApp forwards or mirrors). The checksum and signature
                checks below are the trust mechanism that replaces the Play Store&apos;s review until Magneetar
                is listed there.
              </div>
            </div>
          </div>
        </section>

        {/* ─── Install guide ─────────────────────────────────────────────── */}
        <section className="mt-14">
          <h2 className="text-2xl font-display font-extrabold tracking-tight">
            Install in <span className="text-gradient-primary">five steps</span>
          </h2>
          <div className="mt-7 space-y-4">
            {INSTALL_STEPS.map((step, i) => (
              <div
                key={step.title}
                className="flex gap-5 rounded-2xl border border-white/[0.07] bg-mag-panel/40 backdrop-blur-sm p-6 transition-all duration-300 hover:border-white/[0.14] hover:bg-mag-panel/60"
              >
                <div className="w-9 h-9 shrink-0 rounded-xl bg-gradient-to-br from-[#E91E8C]/20 to-[#06B6D4]/15 border border-white/[0.08] flex items-center justify-center font-mono text-[12px] font-bold text-white/80">
                  {i + 1}
                </div>
                <div>
                  <h3 className="text-white font-bold text-[15px] tracking-tight">{step.title}</h3>
                  <p className="mt-1.5 text-[13px] leading-relaxed text-white/45">{step.body}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ─── OEM battery notes ─────────────────────────────────────────── */}
        <section className="mt-14">
          <div className="flex items-center gap-2 mb-2">
            <BatteryCharging size={17} className="text-[#06B6D4]" />
            <h2 className="text-2xl font-display font-extrabold tracking-tight">
              Keep protection alive on your brand
            </h2>
          </div>
          <p className="mt-2 text-white/45 leading-relaxed text-[14px]">
            OEM battery managers aggressively kill background apps — including theft protection. These are
            the exact settings Magneetar needs on the most common brands in Nigeria.
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

        {/* ─── Verify authenticity ───────────────────────────────────────── */}
        <section className="mt-14 rounded-2xl border border-emerald-500/15 bg-emerald-500/[0.03] p-7 sm:p-9">
          <div className="flex items-center gap-2">
            <FileCheck size={17} className="text-emerald-400" />
            <h2 className="text-xl font-display font-extrabold tracking-tight">Verify the file is really ours</h2>
          </div>
          <p className="mt-3 text-[13.5px] leading-relaxed text-white/50">
            Anyone can upload a fake "Magneetar" APK to a mirror. On a security product, that matters. Two
            ways to confirm your download is genuine:
          </p>
          <ul className="mt-5 space-y-4">
            <li className="flex gap-3">
              <span className="mt-[7px] w-1.5 h-1.5 shrink-0 rounded-full bg-gradient-to-r from-[#E91E8C] to-[#06B6D4]" aria-hidden="true" />
              <div className="text-[13.5px] leading-relaxed text-white/50">
                <span className="text-white font-semibold">Checksum match (recommended):</span> compare the
                downloaded file&apos;s SHA-256 against the value shown above. On a computer:{' '}
                <code className="font-mono text-[12px] text-[#22D3EE]/90">sha256sum Magneetar.apk</code>. The
                hashes must be identical, character for character.
              </div>
            </li>
            <li className="flex gap-3">
              <span className="mt-[7px] w-1.5 h-1.5 shrink-0 rounded-full bg-gradient-to-r from-[#E91E8C] to-[#06B6D4]" aria-hidden="true" />
              <div className="text-[13.5px] leading-relaxed text-white/50">
                <span className="text-white font-semibold">Signature (advanced):</span> every release is
                signed with the Magneetar release key (certificate CN = Magneetar, SHA-256{' '}
                <code className="font-mono text-[12px] text-[#22D3EE]/90">024cbb34…b20a7f</code>). With
                Android SDK tools installed:{' '}
                <code className="font-mono text-[12px] text-[#22D3EE]/90">
                  apksigner verify --print-certs Magneetar.apk
                </code>{' '}
                — the output must show the Magneetar certificate with exactly that SHA-256 digest, not a
                random self-signed key. The full fingerprint:{' '}
                <code className="font-mono text-[11px] text-white/60 break-all">
                  024cbb34db441f37ed3de001174bb1832e3d7ce52e73b6eb35920f1dc4b20a7f
                </code>
              </div>
            </li>
          </ul>
          <div className="mt-6 flex items-start gap-2 rounded-xl border border-amber-500/15 bg-amber-500/[0.04] p-4">
            <AlertTriangle size={15} className="text-amber-400 mt-0.5 shrink-0" />
            <p className="text-[12.5px] leading-relaxed text-amber-200/70">
              Only install from this page or the Play Store listing when it ships. If an APK&apos;s checksum
              doesn&apos;t match, do not install it — report it to security@magneetar.me.
            </p>
          </div>
        </section>

        {/* ─── What you get ──────────────────────────────────────────────── */}
        <section className="mt-14">
          <h2 className="text-2xl font-display font-extrabold tracking-tight">
            What the app gives you
          </h2>
          <div className="mt-6 grid sm:grid-cols-3 gap-4">
            {[
              {
                icon: MapPin,
                title: 'Live tracking + route',
                body: 'Real-time location with a turn-by-turn navigation route straight to your device.',
              },
              {
                icon: Camera,
                title: 'Remote evidence capture',
                body: 'On-theft photo and audio capture with a SHA-256 chain of custody for law enforcement.',
              },
              {
                icon: ShieldCheck,
                title: 'Sentinel theft detection',
                body: 'Silent scoring of movement, SIM swaps, and battery drops — alarms only when it matters.',
              },
            ].map((card) => (
              <div key={card.title} className="rounded-2xl border border-white/[0.07] bg-mag-panel/40 p-6">
                <card.icon size={18} className="text-[#06B6D4]" />
                <div className="mt-4 text-white font-bold text-sm">{card.title}</div>
                <div className="mt-1.5 text-[12.5px] leading-relaxed text-white/45">{card.body}</div>
              </div>
            ))}
          </div>
        </section>

        {/* ─── Next CTA ──────────────────────────────────────────────────── */}
        <section className="mt-14 rounded-2xl border border-white/[0.08] bg-gradient-to-br from-[#E91E8C]/[0.06] to-[#06B6D4]/[0.04] p-8 text-center">
          <h2 className="text-xl font-display font-bold tracking-tight">Have an account ready before you install</h2>
          <p className="mt-2 text-[13.5px] text-white/45 max-w-lg mx-auto">
            Creating an account takes 30 seconds. Do it first, then link your device during setup — you&apos;ll
            be protected before the hour is out.
          </p>
          <Link
            href="/signup"
            className="group mt-6 inline-flex items-center gap-2.5 px-8 py-4 rounded-xl text-[13px] font-bold uppercase tracking-wider bg-gradient-to-r from-[#E91E8C] to-[#06B6D4] text-white shadow-xl shadow-[#E91E8C]/25 hover:shadow-[#E91E8C]/40 hover:brightness-110 transition-all duration-200 active:scale-[0.97]"
          >
            Create your account
            <ChevronRight size={15} className="transition-transform group-hover:translate-x-0.5" />
          </Link>
        </section>
      </main>

      <Footer />
    </div>
  );
}
