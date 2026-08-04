'use client';

import { useState, useEffect, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { cn, relativeTime, isOnline, getSignalLevel, deviceDisplayName } from '@/lib/utils';
import { StatusIndicator } from '@/components/ui/StatusIndicator';
import { ClaimDeviceModal } from '@/components/devices/ClaimDeviceModal';
import { stepUpPasswordHint } from '@/lib/utils';
import { ChevronLeft, ChevronRight, Smartphone, BarChart3, FileText, BookOpen, Copy, Battery, MapPin, Link2, Trash2, X, AlertTriangle } from 'lucide-react';

function sentinelLevel(score: number): string {
  if (score >= 70) return 'HIGH';
  if (score >= 40) return 'ELEVATED';
  return 'SAFE';
}

interface DashboardStats {
  total_devices: number;
  active_devices: number;
  stolen_devices: number;
  total_locations: number;
  total_media: number;
  alerts_today: number;
}

export function Sidebar() {
  const { devices, selectedDeviceId, selectDevice, sidebarOpen, setSidebarOpen, isConnected, setDevices } = useStore();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [showClaimModal, setShowClaimModal] = useState(false);
  // Bulk purge of stale/archived devices — step-up password gated like
  // single-device deletion, so a stolen session can't wipe the account's
  // device history in one click.
  const [confirmPurge, setConfirmPurge] = useState(false);
  const [purgePassword, setPurgePassword] = useState('');
  const [purgeError, setPurgeError] = useState('');
  const [purging, setPurging] = useState(false);

  const onlineCount = devices.filter(d => isOnline(d.last_seen)).length;
  const offlineCount = devices.filter(d => !isOnline(d.last_seen)).length;
  // Archived = soft-flagged by the server after ~30 days of silence. Kept at
  // the bottom of the list and dimmed so long-dead rows stop dominating the
  // sidebar, while remaining visible for review & purge (password-gated).
  const archivedDevices = devices.filter(d => !!d.archived_at);
  const activeDevices = devices.filter(d => !d.archived_at);

  const fetchStats = useCallback(async () => {
    if (!isConnected) return;
    try {
      const api = getAPI();
      const data = await api.getStats();
      setStats(data);
    } catch (e) {
      // Stats endpoint may not exist yet
    }
  }, [isConnected]);

  // Bulk-delete all archived (stale) devices after verifying the step-up
  // password. The server re-checks it (account password for users, master API
  // key for admins), so this UI prompt is the confirmation layer, not the
  // security boundary.
  const confirmPurgeArchived = async () => {
    if (purging || archivedDevices.length === 0) return;
    if (!purgePassword.trim()) {
      setPurgeError('Enter your password to confirm.');
      return;
    }
    setPurging(true);
    setPurgeError('');
    try {
      const res = await getAPI().deleteArchivedDevices(purgePassword);
      // Refresh the device list so the sidebar drops the removed rows.
      const { devices: freshDevices } = await getAPI().getDevices();
      setDevices(freshDevices);
      if (res.count === 0) {
        setPurgeError('No archived devices remain to delete.');
      }
      setConfirmPurge(false);
      setPurgePassword('');
    } catch (e: any) {
      setPurgeError(e?.message || 'Failed to delete archived devices');
    } finally {
      setPurging(false);
    }
  };

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 15000);
    return () => clearInterval(interval);
  }, [fetchStats]);

  return (
    <aside className={cn(
      'bg-mag-panel/90 backdrop-blur-xl border-r border-mag-border/60 flex flex-col transition-all duration-300 ease-out relative overflow-hidden',
      sidebarOpen ? 'w-72' : 'w-12'
    )}>
      {/* Left gradient accent rail */}
      <div className="absolute left-0 top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-mag-primary/25 to-transparent pointer-events-none" />
      {/* ─── Toggle ──────────────────────────────────────────────────────── */}
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        className="h-10 flex items-center justify-center border-b border-mag-border/30 hover:bg-mag-surface/20 transition-colors group shrink-0"
        aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
      >
        {sidebarOpen ? (
          <ChevronLeft size={13} className="text-mag-text-dim/40 group-hover:text-mag-text-dim transition-colors" />
        ) : (
          <ChevronRight size={13} className="text-mag-text-dim/40 group-hover:text-mag-text-dim transition-colors" />
        )}
      </button>

      {sidebarOpen && (
        <>
          {/* ─── M Brand Bar ──────────────────────────────────────────────── */}
          <div className="px-4 py-3 border-b border-mag-border/30 flex items-center gap-3 shrink-0 relative">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-mag-primary/15 via-transparent to-cyan-500/10 border border-white/[0.08] flex items-center justify-center shrink-0 overflow-hidden shadow-[0_0_14px_rgba(233,30,140,0.12)]">
              <img src="/m-logo.svg" alt="M" className="w-4 h-4 drop-shadow-[0_0_5px_rgba(233,30,140,0.45)]" />
            </div>
            <div>
              <div className="text-[11px] font-bold tracking-[0.2em] text-gradient-primary">MAGNEETAR</div>
              <div className="text-[8px] font-mono text-mag-text-dim/30 tracking-[0.2em] font-bold">COMMAND CENTER</div>
            </div>
            <div className="ml-auto w-1 h-1 rounded-full bg-mag-accent shadow-[0_0_6px_rgba(34,197,94,0.5)]" />
          </div>

          {/* ─── Stats Overview ────────────────────────────────────────────── */}
          {stats && (
            <div className="px-4 py-3 border-b border-mag-border/30 shrink-0">
              <div className="flex items-center gap-1.5 mb-2.5">
                <BarChart3 size={11} className="text-mag-primary/60" />
                <span className="text-[9px] font-mono text-mag-text-dim/50 uppercase tracking-[0.15em] font-bold">
                  Overview
                </span>
              </div>
              <div className="grid grid-cols-3 gap-1.5">
                <div className="bg-mag-surface/20 border border-mag-border/25 rounded-lg p-2 text-center transition-all duration-200 hover:border-mag-primary/25 hover:shadow-[0_0_12px_rgba(233,30,140,0.06)]">
                  <div className="font-mono text-sm font-bold text-gradient-primary tabular-nums">{stats.total_devices}</div>
                  <div className="text-[7px] font-mono text-mag-text-dim/40 font-bold uppercase tracking-wider">Total</div>
                </div>
                <div className="bg-mag-accent/[0.04] border border-mag-accent/15 rounded-lg p-2 text-center transition-all duration-200 hover:border-mag-accent/35 hover:shadow-[0_0_12px_rgba(34,197,94,0.08)]">
                  <div className="font-mono text-sm font-bold text-mag-accent tabular-nums">{stats.active_devices}</div>
                  <div className="text-[7px] font-mono text-mag-text-dim/40 font-bold uppercase tracking-wider">Active</div>
                </div>
                <div className="bg-mag-danger/[0.04] border border-mag-danger/15 rounded-lg p-2 text-center transition-all duration-200 hover:border-mag-danger/35 hover:shadow-[0_0_12px_rgba(239,68,68,0.08)]">
                  <div className="font-mono text-sm font-bold text-mag-danger tabular-nums">{stats.stolen_devices}</div>
                  <div className="text-[7px] font-mono text-mag-text-dim/40 font-bold uppercase tracking-wider">Stolen</div>
                </div>
              </div>
              {stats.alerts_today > 0 && (
                <div className="flex items-center gap-1.5 mt-2 px-2 py-1.5 bg-mag-warning/[0.04] border border-mag-warning/10 rounded-lg">
                  <svg width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-mag-warning shrink-0">
                    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                    <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
                  </svg>
                  <span className="text-[8px] font-mono text-mag-warning font-bold">{stats.alerts_today} alert{stats.alerts_today !== 1 ? 's' : ''} today</span>
                </div>
              )}
            </div>
          )}

          {/* ─── Devices Section Header ────────────────────────────────────── */}
          <div className="px-4 py-2.5 border-b border-mag-border/30 shrink-0">
            <div className="flex items-center gap-2">
              <Smartphone size={12} className="text-mag-primary/60" />
              <span className="text-[10px] font-mono text-mag-text-dim/60 uppercase tracking-[0.2em] font-bold">
                Devices
              </span>
              <span className="ml-auto flex items-center gap-2 text-[10px] font-mono font-bold tabular-nums">
                {archivedDevices.length > 0 && (
                  <span className="text-amber-400/70">{archivedDevices.length} archived</span>
                )}
                <span className="text-mag-text-dim/40">{activeDevices.length}</span>
              </span>
              {/* Link a device — claim an ownerless phone via its pairing code */}
              <button
                onClick={() => setShowClaimModal(true)}
                title="Link a device (pairing code)"
                aria-label="Link a device"
                className="flex items-center gap-1 px-1.5 py-1 rounded-md text-[9px] font-mono font-bold uppercase tracking-wider text-mag-accent/80 hover:text-mag-accent hover:bg-mag-accent/10 border border-mag-accent/25 transition-all"
              >
                <Link2 size={10} />
                Link
              </button>
            </div>
            {/* Purge stale/archived devices — password-gated (step-up) */}
            {archivedDevices.length > 0 && (
              <button
                onClick={() => { setConfirmPurge(true); setPurgeError(''); }}
                title={`Delete all ${archivedDevices.length} archived device(s) permanently (requires password)`}
                aria-label="Delete all archived devices"
                className="mt-2 w-full flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-md text-[9px] font-mono font-bold uppercase tracking-wider text-amber-400/90 hover:text-amber-300 hover:bg-amber-500/10 border border-amber-500/25 transition-all"
              >
                <Trash2 size={10} />
                Delete {archivedDevices.length} archived
              </button>
            )}
          </div>

          {/* ─── Device List ────────────────────────────────────────────────── */}
          <div className="flex-1 overflow-y-auto overscroll-contain">
            {devices.length === 0 ? (
              <div className="p-6 text-center">
                <Smartphone size={22} className="mx-auto text-mag-text-dim/15 mb-3" />
                <div className="text-mag-text-dim/40 text-sm font-bold">
                  No devices registered.
                </div>
                <div className="text-mag-text-dim/25 text-[10px] font-mono mt-1">
                  Connect to server first.
                </div>
              </div>
            ) : (
              [...activeDevices, ...archivedDevices].map((device, idx) => {
                const archived = !!device.archived_at;
                const online = isOnline(device.last_seen);
                const signal = getSignalLevel(device.last_seen);
                const scoreColor =
                  device.is_stolen || device.sentinel_score >= 70 ? 'bg-mag-danger' :
                  device.sentinel_score >= 40 ? 'bg-mag-warning' :
                  'bg-mag-accent';
                const scoreText =
                  device.is_stolen ? 'text-mag-danger bg-mag-danger/10' :
                  device.sentinel_score >= 70 ? 'text-mag-danger bg-mag-danger/10' :
                  device.sentinel_score >= 40 ? 'text-mag-warning bg-mag-warning/10' :
                  'text-mag-accent bg-mag-accent/10';

                return (
                  <button
                    key={device.id}
                    onClick={() => selectDevice(device.id)}
                    className={cn(
                      'w-full text-left px-4 py-2.5 border-b border-mag-border/15 transition-all duration-150',
                      'hover:bg-mag-surface/15 group',
                      selectedDeviceId === device.id && 'bg-mag-primary/[0.02] border-l-[2px] border-l-mag-primary/40',
                      archived && 'opacity-45 hover:opacity-70'
                    )}
                    style={{ animationDelay: `${idx * 30}ms` }}
                  >
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="text-sm font-bold text-mag-text truncate group-hover:text-mag-text-bright transition-colors max-w-[65%]">
                        {deviceDisplayName(device)}
                      </span>
                      {archived && (
                        <span className="text-[8px] font-mono font-bold uppercase tracking-wider px-1 py-0.5 rounded border border-amber-500/25 text-amber-400 bg-amber-500/10 shrink-0">
                          Archived
                        </span>
                      )}
                      <StatusIndicator
                        isOnline={online}
                        signal={signal}
                        className="scale-[0.7] origin-right -mr-1"
                      />
                    </div>

                    <div className="font-mono text-[9px] text-mag-text-dim/40 truncate font-bold mb-0.5">
                      {device.id}
                    </div>

                    <div className="flex items-center gap-2">
                      <span className={cn(
                        'w-1.5 h-1.5 rounded-full',
                        online ? 'bg-mag-accent shadow-[0_0_6px_rgba(34,197,94,0.4)]' : 'bg-mag-text-dim/20'
                      )} />
                      <span className="font-mono text-[9px] text-mag-text-dim/35 font-bold">
                        {relativeTime(device.last_seen)}
                      </span>
                    </div>

                    {/* Mini Sentinel score — always visible, not just in the tab */}
                    <div className="flex items-center gap-1.5 mt-1.5">
                      <span className={cn(
                        'text-[8px] font-mono font-bold uppercase px-1.5 py-0.5 rounded',
                        scoreText
                      )}>
                        {device.is_stolen ? 'STOLEN' : sentinelLevel(device.sentinel_score)}
                      </span>
                      <span className="text-[9px] font-mono font-bold text-mag-text tabular-nums">
                        {device.sentinel_score}
                      </span>
                      <div className="flex-1 h-1 rounded-full bg-mag-bg/50 overflow-hidden">
                        <div
                          className={cn('h-full rounded-full transition-all duration-500', scoreColor)}
                          style={{ width: `${Math.min(device.sentinel_score, 100)}%` }}
                        />
                      </div>
                    </div>

                    {/* Last-known coordinates + battery + copy (works offline) */}
                    {(device.lat != null && device.lng != null) && (
                      <div className="flex items-center gap-1.5 mt-1">
                        <MapPin size={8} className="text-mag-text-dim/30 shrink-0" />
                        <span className="font-mono text-[8px] text-mag-text-dim/40 font-bold truncate">
                          {device.lat.toFixed(4)}, {device.lng.toFixed(4)}
                        </span>
                        <span
                          role="button"
                          tabIndex={-1}
                          onClick={(e) => {
                            e.stopPropagation();
                            navigator.clipboard?.writeText(`${device.lat},${device.lng}`);
                          }}
                          title="Copy coordinates"
                          className="text-mag-text-dim/40 hover:text-mag-accent cursor-pointer transition-colors shrink-0"
                        >
                          <Copy size={9} />
                        </span>
                        {device.battery_percent != null && (
                          <span className="ml-auto flex items-center gap-1 text-[8px] font-mono text-mag-text-dim/45 font-bold tabular-nums">
                            <Battery size={9} className={cn(device.battery_percent <= 20 ? 'text-mag-danger' : 'text-mag-accent')} />
                            {device.battery_percent}%
                          </span>
                        )}
                      </div>
                    )}
                  </button>
                );
              })
            )}
          </div>

          {/* ─── Footer ────────────────────────────────────────────────────── */}
          <div className="px-4 py-3 border-t border-mag-border/30 bg-mag-bg/20 shrink-0">
            {/* Online/Offline counts */}
            <div className="flex items-center justify-between text-[10px] font-mono font-bold mb-2.5">
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-mag-accent shadow-[0_0_6px_rgba(34,197,94,0.3)]" />
                <span className="text-mag-accent/70 tabular-nums">{onlineCount}</span>
                <span className="text-mag-text-dim/30">online</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-mag-text-dim/30" />
                <span className="text-mag-text-dim/50 tabular-nums">{offlineCount}</span>
                <span className="text-mag-text-dim/30">offline</span>
              </span>
            </div>

            {/* API Docs Links */}
            <div className="space-y-1 pt-2.5 border-t border-mag-border/15">
              <a
                href="https://api.magneetar.me/docs"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 px-2 py-1.5 rounded-lg text-[9px] font-mono text-mag-text-dim/50 hover:text-mag-accent hover:bg-mag-accent/[0.03] transition-all duration-150 group"
              >
                <FileText size={10} className="text-mag-text-dim/30 group-hover:text-mag-accent shrink-0" />
                <span className="font-bold tracking-wide">API Docs (Swagger)</span>
                <span className="ml-auto text-[7px] opacity-0 group-hover:opacity-100 transition-opacity">↗</span>
              </a>
              <a
                href="https://api.magneetar.me/redoc"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 px-2 py-1.5 rounded-lg text-[9px] font-mono text-mag-text-dim/50 hover:text-mag-accent hover:bg-mag-accent/[0.03] transition-all duration-150 group"
              >
                <BookOpen size={10} className="text-mag-text-dim/30 group-hover:text-mag-accent shrink-0" />
                <span className="font-bold tracking-wide">API Docs (ReDoc)</span>
                <span className="ml-auto text-[7px] opacity-0 group-hover:opacity-100 transition-opacity">↗</span>
              </a>
            </div>
          </div>
        </>
      )}

      {/* Link-a-device modal (pairing code claim) */}
      {showClaimModal && <ClaimDeviceModal onClose={() => setShowClaimModal(false)} />}

      {/* Purge archived devices — step-up password confirm */}
      {confirmPurge && (
        <div className="absolute inset-0 z-50 flex items-center justify-center bg-mag-bg/80 backdrop-blur-sm p-4">
          <div className="w-full max-w-sm rounded-2xl border border-amber-500/30 bg-mag-panel/95 shadow-2xl p-4 space-y-3 animate-fade-in">
            <div className="flex items-start gap-2">
              <AlertTriangle size={14} className="text-amber-400 shrink-0 mt-0.5" />
              <div>
                <div className="text-[11px] font-mono text-amber-400 font-bold uppercase tracking-wider">
                  Delete {archivedDevices.length} archived device{archivedDevices.length !== 1 ? 's' : ''}
                </div>
                <div className="text-[10px] font-mono text-mag-text-dim/70 mt-1 leading-relaxed">
                  These devices have been silent beyond the archive threshold. All their
                  locations, media, evidence & alerts are erased permanently. This cannot
                  be undone.
                </div>
              </div>
            </div>
            <input
              type="password"
              value={purgePassword}
              onChange={e => setPurgePassword(e.target.value)}
              placeholder={stepUpPasswordHint()}
              autoFocus
              aria-label="Confirm deletion password"
              onKeyDown={e => {
                if (e.key === 'Enter' && !purging) {
                  e.preventDefault();
                  confirmPurgeArchived();
                }
              }}
              className="w-full bg-mag-bg/60 border border-mag-border/40 rounded-lg px-3 py-2 text-xs font-mono text-mag-text placeholder:text-mag-text-dim/30 focus:outline-none focus:border-amber-500/60 transition-colors"
            />
            {purgeError && <div className="text-[10px] font-mono text-red-400">{purgeError}</div>}
            <div className="text-[10px] font-mono text-mag-text-dim/50 leading-relaxed">
              This session verifies with <span className="font-bold text-mag-text-dim/70">{stepUpPasswordHint()}</span>.
            </div>
            <div className="flex gap-2">
              <button
                onClick={confirmPurgeArchived}
                disabled={purging}
                className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg bg-amber-500/90 hover:bg-amber-500 disabled:opacity-50 text-white text-[11px] font-bold transition-all"
              >
                <Trash2 size={12} />
                {purging ? 'Deleting...' : 'Yes, Delete'}
              </button>
              <button
                onClick={() => { setConfirmPurge(false); setPurgePassword(''); setPurgeError(''); }}
                disabled={purging}
                className="flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg border border-mag-border/40 text-mag-text-dim/70 hover:text-mag-text text-[11px] font-bold transition-all"
              >
                <X size={12} />
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
