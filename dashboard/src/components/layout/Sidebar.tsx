'use client';

import { useState, useEffect, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { cn, relativeTime, isOnline, getSignalLevel } from '@/lib/utils';
import { StatusIndicator } from '@/components/ui/StatusIndicator';
import { ChevronLeft, ChevronRight, Smartphone, Wifi, WifiOff, AlertTriangle, BarChart3, FileText, BookOpen } from 'lucide-react';

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
      'bg-mag-panel/90 backdrop-blur-xl border-r border-mag-border/60 flex flex-col transition-all duration-300 ease-out',
      sidebarOpen ? 'w-72' : 'w-12'
    )}>
      {/* Toggle */}
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        className="h-10 flex items-center justify-center border-b border-mag-border/40 hover:bg-mag-surface/30 transition-colors group"
      >
        {sidebarOpen ? (
          <ChevronLeft size={14} className="text-mag-text-dim/50 group-hover:text-mag-text-dim transition-colors" />
        ) : (
          <ChevronRight size={14} className="text-mag-text-dim/50 group-hover:text-mag-text-dim transition-colors" />
        )}
      </button>

      {sidebarOpen && (
        <>
          {/* ── Stats Overview ── */}
          {stats && (
            <div className="px-4 py-3 border-b border-mag-border/40">
              <div className="flex items-center gap-2 mb-2.5">
                <BarChart3 size={12} className="text-mag-primary" />
                <span className="text-[10px] font-mono text-mag-text-dim/70 uppercase tracking-[0.15em] font-bold">
                  Overview
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div className="bg-mag-surface/30 border border-mag-border/30 rounded-lg p-2 text-center">
                  <div className="font-mono text-sm font-bold text-mag-text">{stats.total_devices}</div>
                  <div className="text-[8px] font-mono text-mag-text-dim/40 font-bold uppercase">Total</div>
                </div>
                <div className="bg-mag-accent/5 border border-mag-accent/20 rounded-lg p-2 text-center">
                  <div className="font-mono text-sm font-bold text-mag-accent">{stats.active_devices}</div>
                  <div className="text-[8px] font-mono text-mag-text-dim/40 font-bold uppercase">Active</div>
                </div>
                <div className="bg-mag-danger/5 border border-mag-danger/20 rounded-lg p-2 text-center">
                  <div className="font-mono text-sm font-bold text-mag-danger">{stats.stolen_devices}</div>
                  <div className="text-[8px] font-mono text-mag-text-dim/40 font-bold uppercase">Stolen</div>
                </div>
              </div>
              {stats.alerts_today > 0 && (
                <div className="flex items-center gap-1.5 mt-2 px-2 py-1 bg-mag-warning/5 border border-mag-warning/15 rounded-lg">
                  <AlertTriangle size={10} className="text-mag-warning" />
                  <span className="text-[9px] font-mono text-mag-warning font-bold">{stats.alerts_today} alerts today</span>
                </div>
              )}
            </div>
          )}

          {/* Section Title */}
          <div className="px-4 py-3 border-b border-mag-border/40">
            <div className="flex items-center gap-2">
              <Smartphone size={13} className="text-mag-primary" />
              <span className="text-[11px] font-mono text-mag-text-dim/70 uppercase tracking-[0.2em] font-bold">
                Devices
              </span>
              <span className="ml-auto text-[11px] font-mono text-mag-text-dim/50 font-bold">
                {devices.length}
              </span>
            </div>
          </div>

          {/* Device List */}
          <div className="flex-1 overflow-y-auto">
            {devices.length === 0 ? (
              <div className="p-6 text-center">
                <Smartphone size={24} className="mx-auto text-mag-text-dim/20 mb-3" />
                <div className="text-mag-text-dim/50 text-sm font-bold">
                  No devices registered.
                </div>
                <div className="text-mag-text-dim/30 text-xs font-mono mt-1">
                  Connect to server first.
                </div>
              </div>
            ) : (
              devices.map((device) => {
                const online = isOnline(device.last_seen);
                const signal = getSignalLevel(device.last_seen);

                return (
                  <button
                    key={device.id}
                    onClick={() => selectDevice(device.id)}
                    className={cn(
                      'w-full text-left px-4 py-3 border-b border-mag-border/20 transition-all duration-150',
                      'hover:bg-mag-surface/20 group',
                      selectedDeviceId === device.id && 'bg-mag-primary/5 border-l-[3px] border-l-mag-primary shadow-[inset_0_0_16px_rgba(233,30,140,0.04)]'
                    )}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-bold text-mag-text truncate group-hover:text-mag-text-bright transition-colors">
                        {device.alias || 'Device'}
                      </span>
                      <StatusIndicator
                        isOnline={online}
                        signal={signal}
                        className="scale-75 origin-right"
                      />
                    </div>

                    <div className="font-mono text-[10px] text-mag-text-dim/50 truncate font-bold">
                      {device.id}
                    </div>

                    <div className="flex items-center gap-1.5 mt-1">
                      {online ? (
                        <Wifi size={10} className="text-mag-accent/60" />
                      ) : (
                        <WifiOff size={10} className="text-mag-text-dim/30" />
                      )}
                      <span className="font-mono text-[10px] text-mag-text-dim/40 font-bold">
                        Last seen: {relativeTime(device.last_seen)}
                      </span>
                    </div>
                  </button>
                );
              })
            )}
          </div>

          {/* Footer Stats */}
          <div className="px-4 py-3 border-t border-mag-border/40 bg-mag-bg/30">
            <div className="flex items-center justify-between text-[11px] font-mono font-bold">
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-mag-accent" />
                <span className="text-mag-accent/80">{onlineCount}</span>
                <span className="text-mag-text-dim/40">online</span>
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-mag-text-dim/40" />
                <span className="text-mag-text-dim/60">{offlineCount}</span>
                <span className="text-mag-text-dim/40">offline</span>
              </span>
            </div>

            {/* API Docs Links */}
            <div className="mt-2.5 pt-2.5 border-t border-mag-border/20 space-y-1">
              <a
                href="https://api.magneetar.me/docs"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 px-2 py-1.5 rounded-lg text-[10px] font-mono text-mag-text-dim/60 hover:text-mag-accent hover:bg-mag-accent/5 transition-all duration-150 group"
              >
                <FileText size={11} className="text-mag-text-dim/40 group-hover:text-mag-accent" />
                <span className="font-bold tracking-wide">API Docs (Swagger)</span>
                <span className="ml-auto text-[8px] opacity-0 group-hover:opacity-100 transition-opacity">↗</span>
              </a>
              <a
                href="https://api.magneetar.me/redoc"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 px-2 py-1.5 rounded-lg text-[10px] font-mono text-mag-text-dim/60 hover:text-mag-accent2 hover:bg-mag-accent2/5 transition-all duration-150 group"
              >
                <BookOpen size={11} className="text-mag-text-dim/40 group-hover:text-mag-accent2" />
                <span className="font-bold tracking-wide">API Docs (ReDoc)</span>
                <span className="ml-auto text-[8px] opacity-0 group-hover:opacity-100 transition-opacity">↗</span>
              </a>
            </div>
          </div>
        </>
      )}
    </aside>
  );
}
