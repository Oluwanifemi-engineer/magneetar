'use client';

import { useEffect, useState } from 'react';

/**
 * Live server info for the landing page badges.
 *
 * The Hero + Footer used to hardcode a version string (v1.3.0) that drifted
 * from the real release — every bump required a code edit. This hook fetches
 * the public /health endpoint at runtime and reports the LIVE deployed
 * version, falling back to the build-time version (NEXT_PUBLIC_APP_VERSION,
 * baked from the repo VERSION file by the Docker build) until the fetch
 * resolves or when the API is unreachable.
 */
const FALLBACK_VERSION = process.env.NEXT_PUBLIC_APP_VERSION || '1.4.0';

export type ServerStatus = 'checking' | 'online' | 'offline';

export interface LiveServerInfo {
  version: string;
  status: ServerStatus;
}

export function useLiveServerInfo(): LiveServerInfo {
  const [info, setInfo] = useState<LiveServerInfo>({
    version: FALLBACK_VERSION,
    status: 'checking',
  });

  useEffect(() => {
    // Environments without fetch (e.g. jsdom tests, very old engines) stay on
    // the build-time fallback rather than crashing the landing page.
    if (typeof fetch !== 'function') return;
    let cancelled = false;
    const base = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/+$/, '');
    fetch(`${base}/health`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((h: { status?: string; version?: string }) => {
        if (cancelled) return;
        setInfo({
          version: typeof h.version === 'string' && h.version ? h.version : FALLBACK_VERSION,
          status: h.status === 'online' ? 'online' : 'offline',
        });
      })
      .catch(() => {
        // API unreachable — keep the build-time fallback and show an honest
        // "unknown" state rather than a fabricated green.
        if (!cancelled) setInfo((prev) => ({ ...prev, status: 'offline' }));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return info;
}

/** Status dot color used by both landing badges. */
export function statusDotClass(status: ServerStatus): string {
  switch (status) {
    case 'online':
      return 'bg-emerald-400';
    case 'offline':
      return 'bg-red-400';
    default:
      return 'bg-amber-400';
  }
}

/** Hero badge: version number with a live status pulse. */
export function VersionBadge() {
  const { version, status } = useLiveServerInfo();
  const label =
    status === 'online'
      ? `v${version} · ACTIVE`
      : status === 'offline'
        ? `v${version} · STATUS UNKNOWN`
        : `v${version} · CHECKING…`;

  return (
    <div
      className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-gray-200 bg-gray-50 mb-7"
      title={
        status === 'online'
          ? `Live server version v${version} — verified against api.magneetar.me/health`
          : `Build version v${version} — live health check unreachable`
      }
    >
      <span className="relative flex w-2 h-2">
        <span
          className={`absolute inline-flex h-full w-full rounded-full opacity-60 animate-ping ${statusDotClass(status)}`}
        />
        <span className={`relative inline-flex rounded-full w-2 h-2 ${statusDotClass(status)}`} />
      </span>
      <span className="text-[11px] font-mono font-bold tracking-wider text-gray-500">{label}</span>
    </div>
  );
}
