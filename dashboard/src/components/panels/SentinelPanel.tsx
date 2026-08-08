'use client';

import { useStore } from '@/store/useStore';
import { cn, relativeTime } from '@/lib/utils';
import { Shield, AlertTriangle, Battery, Wifi, MapPin, Clock, Smartphone } from 'lucide-react';
// Smartphone may not exist in older lucide-react versions — fall back to Shield
import { SentinelSkeleton } from '@/components/ui/Skeleton';

export function SentinelPanel() {
  const { devices, selectedDeviceId, latestLocation } = useStore();
  const device = devices.find(d => d.id === selectedDeviceId);

  if (!device) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
        <div className="w-14 h-14 rounded-2xl bg-mag-surface/40 border border-mag-border/30 flex items-center justify-center mb-4">
          <Smartphone size={24} className="text-mag-text-dim/25" />
        </div>
        <div className="text-mag-text-dim/60 text-sm font-bold mb-1">
          No device selected
        </div>
        <div className="text-mag-text-dim/35 text-xs font-mono leading-relaxed max-w-[200px]">
          Select a device from the sidebar to view its threat assessment and security status.
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      {/* Sentinel Score */}
      <div className="bg-mag-surface/40 border border-mag-border/40 rounded-xl p-4">
        <div className="flex items-center gap-1.5 text-[11px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold mb-3">
          <Shield size={12} className="text-mag-primary" />
          Threat Assessment
        </div>

        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-mono text-mag-text-dim/60">Score</span>
            <span className={cn(
              'text-2xl font-mono font-bold tabular-nums',
              device.sentinel_score >= 70 ? 'text-mag-danger' :
              device.sentinel_score >= 40 ? 'text-mag-warning' :
              'text-mag-accent'
            )}>
              {device.sentinel_score}
            </span>
          </div>
          <span className={cn(
            'text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded-md',
            device.is_stolen ? 'text-mag-danger bg-mag-danger/10 border border-mag-danger/20' :
            'text-mag-accent bg-mag-accent/10 border border-mag-accent/20'
          )}>
            {device.is_stolen ? 'STOLEN' : 'SECURE'}
          </span>
        </div>

        {/* Score bar */}
        <div className="h-2 bg-mag-bg/50 rounded-full overflow-hidden">
          <div
            className={cn(
              'h-full rounded-full transition-all duration-500',
              device.sentinel_score >= 70 ? 'bg-mag-danger' :
              device.sentinel_score >= 40 ? 'bg-mag-warning' :
              'bg-mag-accent'
            )}
            style={{ width: `${Math.min(device.sentinel_score, 100)}%` }}
          />
        </div>
      </div>

      {/* Device Info Grid */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-mag-surface/30 border border-mag-border/30 rounded-lg p-3">
          <div className="flex items-center gap-1.5 text-[10px] font-mono text-mag-text-dim/60 mb-1">
            <Battery size={10} className="text-mag-accent" />
            Battery
          </div>
          <span className="font-mono text-sm font-bold text-mag-text">
            {latestLocation?.battery_percent ?? '—'}%
          </span>
        </div>

        <div className="bg-mag-surface/30 border border-mag-border/30 rounded-lg p-3">
          <div className="flex items-center gap-1.5 text-[10px] font-mono text-mag-text-dim/60 mb-1">
            <Wifi size={10} className="text-mag-secondary" />
            Speed
          </div>
          <span className="font-mono text-sm font-bold text-mag-text">
            {latestLocation?.speed ? `${(latestLocation.speed * 3.6).toFixed(1)} km/h` : '—'}
          </span>
        </div>

        <div className="bg-mag-surface/30 border border-mag-border/30 rounded-lg p-3">
          <div className="flex items-center gap-1.5 text-[10px] font-mono text-mag-text-dim/60 mb-1">
            <MapPin size={10} className="text-mag-primary" />
            Accuracy
          </div>
          <span className="font-mono text-sm font-bold text-mag-text">
            ±{latestLocation?.accuracy?.toFixed(0) ?? '—'}m
          </span>
        </div>

        <div className="bg-mag-surface/30 border border-mag-border/30 rounded-lg p-3">
          <div className="flex items-center gap-1.5 text-[10px] font-mono text-mag-text-dim/60 mb-1">
            <Clock size={10} className="text-mag-warning" />
            Last Seen
          </div>
          <span className="font-mono text-sm font-bold text-mag-text">
            {relativeTime(device.last_seen)}
          </span>
        </div>
      </div>

      {/* Alerts */}
      {device.is_stolen && (
        <div className="bg-mag-danger/5 border border-mag-danger/20 rounded-xl p-3">
          <div className="flex items-center gap-2 text-mag-danger text-xs font-bold">
            <AlertTriangle size={14} />
            DEVICE MARKED AS STOLEN
          </div>
          <div className="text-[10px] font-mono text-mag-text-dim/60 mt-1">
            All tracking data is being logged for evidence.
          </div>
        </div>
      )}
    </div>
  );
}
