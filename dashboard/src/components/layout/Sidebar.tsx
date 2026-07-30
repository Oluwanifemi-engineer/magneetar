'use client';

import { useState, useEffect, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { cn, relativeTime, isOnline, getSignalLevel } from '@/lib/utils';
import { StatusIndicator } from '@/components/ui/StatusIndicator';
import { ChevronLeft, ChevronRight, Smartphone, BarChart3, FileText, BookOpen } from 'lucide-react';

interface DashboardStats {
  total_devices: number;
  active_devices: number;
  stolen_devices: number;
  total_locations: number;
  total_media: number;
  alerts_today: number;
}

export function Sidebar() {
  const { devices, selectedDeviceId, selectDevice, sidebarOpen, setSidebarOpen, isConnected } = useStore();
  const [stats, setStats] = useState<DashboardStats | null>(null);

  const onlineCount = devices.filter(d => isOnline(d.last_seen)).length;
  const offlineCount = devices.filter(d => !isOnline(d.last_seen)).length;

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

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 15000);
    return () => clearInterval(interval);
  }, [fetchStats]);

  return (
    <aside className={cn(
      'bg-mag-panel/90 backdrop-blur-xl border-r border-mag-border/60 flex flex-col transition-all duration-300 ease-out relative',
      sidebarOpen ? 'w-72' : 'w-12'
    )}>
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
          <div className="px-4 py-3 border-b border-mag-border/30 flex items-center gap-3 shrink-0">
            <div className="w-7 h-7 rounded-lg bg-white/[0.03] border border-white/[0.06] flex items-center justify-center shrink-0 overflow-hidden">
              <img src="/m-logo.svg" alt="M" className="w-4 h-4" />
            </div>
            <div>
              <div className="text-[11px] font-bold tracking-[0.2em] text-mag-text/80">MAGNEETAR</div>
              <div className="text-[8px] font-mono text-mag-text-dim/30 tracking-[0.2em] font-bold">COMMAND CENTER</div>
            </div>
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
                <div className="bg-mag-surface/20 border border-mag-border/25 rounded-lg p-2 text-center">
                  <div className="font-mono text-sm font-bold text-mag-text tabular-nums">{stats.total_devices}</div>
                  <div className="text-[7px] font-mono text-mag-text-dim/40 font-bold uppercase tracking-wider">Total</div>
                </div>
                <div className="bg-mag-accent/[0.04] border border-mag-accent/15 rounded-lg p-2 text-center">
                  <div className="font-mono text-sm font-bold text-mag-accent tabular-nums">{stats.active_devices}</div>
                  <div className="text-[7px] font-mono text-mag-text-dim/40 font-bold uppercase tracking-wider">Active</div>
                </div>
                <div className="bg-mag-danger/[0.04] border border-mag-danger/15 rounded-lg p-2 text-center">
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
              <span className="ml-auto text-[10px] font-mono text-mag-text-dim/40 font-bold tabular-nums">
                {devices.length}
              </span>
            </div>
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
              devices.map((device, idx) => {
                const online = isOnline(device.last_seen);
                const signal = getSignalLevel(device.last_seen);

                return (
                  <button
                    key={device.id}
                    onClick={() => selectDevice(device.id)}
                    className={cn(
                      'w-full text-left px-4 py-2.5 border-b border-mag-border/15 transition-all duration-150',
                      'hover:bg-mag-surface/15 group',
                      selectedDeviceId === device.id && 'bg-mag-primary/[0.02] border-l-[2px] border-l-mag-primary/40'
                    )}
                    style={{ animationDelay: `${idx * 30}ms` }}
                  >
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="text-sm font-bold text-mag-text truncate group-hover:text-mag-text-bright transition-colors max-w-[65%]">
                        {device.alias || 'Device'}
                      </span>
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
    </aside>
  );
}
