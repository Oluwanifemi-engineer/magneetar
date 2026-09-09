'use client';

import { useState, useEffect } from 'react';
import { useStore } from '@/store/useStore';
import { cn, relativeTime } from '@/lib/utils';
import { Shield, AlertTriangle, Battery, Wifi, MapPin, Clock, Smartphone, ShieldCheck } from 'lucide-react';

/**
 * SentinelPanel — Threat assessment with KPI hero.
 *
 * Design follows Linear/Stripe/Mercury patterns:
 * - KPI hero: one big number (sentinel score) at top
 * - Color = state only (emerald/amber/red)
 * - Quiet chrome: no borders, background shifts for grouping
 * - Tabular numerals: monospace for all data
 * - Trust through visual calm
 */

function sentinelLabel(score: number): string {
  if (score >= 70) return 'HIGH RISK';
  if (score >= 40) return 'ELEVATED';
  return 'SECURE';
}

export function SentinelPanel() {
  const { devices, selectedDeviceId, latestLocation } = useStore();
  const device = devices.find(d => d.id === selectedDeviceId);

  // ─── Empty state: no device selected ─────────────────────────────
  if (!device) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
        <div className="mag-empty-icon w-14 h-14">
          <Shield size={24} className="text-mag-text-muted" />
        </div>
        <div className="mag-empty-head">
          No device selected
        </div>
        <div className="mag-empty-sub">
          Select a device to view its threat assessment and security status.
        </div>
      </div>
    );
  }

  const score = device.sentinel_score;
  const isStolen = device.is_stolen;
  const isHighRisk = score >= 70 || isStolen;
  const isElevated = score >= 40 && !isHighRisk;

  return (
    <div className="p-4 space-y-4">
      {/* ═══ KPI Hero — One Big Number ═══ */}
      <div className={cn(
        'rounded-2xl p-5 text-center border transition-all duration-200',
        isStolen ? 'bg-red-500/10 border-red-500/20' :
        isHighRisk ? 'bg-red-500/8 border-red-500/15' :
        isElevated ? 'bg-amber-500/8 border-amber-500/15' :
        'bg-emerald-500/8 border-emerald-500/15'
      )}>
        {/* Status label */}
        <div className="flex items-center justify-center gap-2 mb-3">
          {isStolen ? (
            <AlertTriangle size={14} className="text-red-400" />
          ) : isHighRisk ? (
            <Shield size={14} className="text-red-400" />
          ) : (
            <ShieldCheck size={14} className="text-emerald-400" />
          )}
          <span className={cn(
            'text-[10px] font-mono font-bold uppercase tracking-[0.2em]',
            isStolen ? 'text-red-400' :
            isHighRisk ? 'text-red-400/70' :
            isElevated ? 'text-amber-400/70' :
            'text-emerald-400/70'
          )}>
            {isStolen ? 'STOLEN' : sentinelLabel(score)}
          </span>
        </div>

        {/* The Number — largest type on the page */}
        <div className={cn(
          'font-mono text-5xl font-bold tabular-nums leading-none mb-2',
          isStolen ? 'text-red-400' :
          isHighRisk ? 'text-red-400/80' :
          isElevated ? 'text-amber-400' :
          'text-emerald-400'
        )}>
          {score}
        </div>

        {/* Score bar */}
        <div className="h-1.5 rounded-full overflow-hidden mx-auto max-w-[160px]" style={{ background: 'rgba(31,41,55,0.5)' }}>
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{
              width: `${Math.min(score, 100)}%`,
              background: isStolen ? '#ef4444' :
                isHighRisk ? 'rgba(239,68,68,0.7)' :
                isElevated ? '#f59e0b' :
                '#10b981',
            }}
          />
        </div>

        {/* Sub-label */}
        <div className="text-[9px] font-mono text-mag-text-muted uppercase tracking-wider mt-2">
          Sentinel Score
        </div>
      </div>

      {/* ═══ Device Stats — Tabular Numerals ═══ */}
      <div className="grid grid-cols-2 gap-2">
        {[
          { icon: Battery, label: 'Battery', value: `${latestLocation?.battery_percent ?? '—'}%` },
          { icon: Wifi, label: 'Speed', value: latestLocation?.speed ? `${(latestLocation.speed * 3.6).toFixed(1)} km/h` : '—' },
          { icon: MapPin, label: 'Accuracy', value: `±${latestLocation?.accuracy?.toFixed(0) ?? '—'}m` },
          { icon: Clock, label: 'Last Seen', value: relativeTime(device.last_seen) },
        ].map((stat) => (
          <div key={stat.label} className="mag-stat-tile">
            <div className="mag-stat flex items-center gap-1.5 mb-1.5">
              <stat.icon size={10} className="text-mag-text-muted/50" />
              <span className="mag-stat-label">{stat.label}</span>
            </div>
            <span className="mag-stat-value">
              {stat.value}
            </span>
          </div>
        ))}
      </div>

      {/* ═══ Stolen Alert — Exception-First ═══ */}
      {isStolen && (
        <div className="mag-danger-block animate-fade-in">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-red-500/15 flex items-center justify-center">
              <AlertTriangle size={16} className="text-red-400" />
            </div>
            <div>
              <div className="text-[11px] font-mono text-red-400 font-bold uppercase tracking-wider">
                Device Stolen
              </div>
              <div className="text-[9px] font-mono text-mag-text-muted mt-0.5">
                All tracking data is being logged for evidence.
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
