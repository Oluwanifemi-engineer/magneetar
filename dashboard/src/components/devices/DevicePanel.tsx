'use client';

import { useStore } from '@/store/useStore';
import { cn, relativeTime, formatCoordinate } from '@/lib/utils';
import { MapPin, LocateFixed, Navigation, ExternalLink } from 'lucide-react';
import { CoordDisplay } from '@/components/ui/CoordDisplay';

export function DevicePanel() {
  const { devices, selectedDeviceId, latestLocation } = useStore();
  const device = devices.find(d => d.id === selectedDeviceId);

  if (!device) {
    return (
      <div className="flex flex-col items-center justify-center py-12 px-4">
        <MapPin size={28} className="mx-auto text-mag-text-dim/20 mb-3" />
        <div className="text-mag-text-dim/50 text-sm font-bold">
          No device selected.
        </div>
        <div className="text-mag-text-dim/30 text-xs font-mono mt-1">
          Select a device from the sidebar.
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      {/* Device Header */}
      <div className="bg-mag-surface/40 border border-mag-border/40 rounded-xl p-4">
        <h3 className="text-base font-bold text-mag-text flex items-center gap-2 mb-3">
          <div className="w-2.5 h-2.5 rounded-full bg-mag-primary shadow-[0_0_10px_rgba(233,30,140,0.5)]" />
          {device.alias || 'Device'}
        </h3>

        <div className="space-y-2">
          <div className="flex justify-between items-center">
            <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Device ID</span>
            <span className="text-[11px] font-mono text-mag-text font-bold">{device.id}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Registered</span>
            <span className="text-[11px] font-mono text-mag-text-dim font-bold">{relativeTime(device.registered)}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Last Seen</span>
            <span className="text-[11px] font-mono text-mag-text-dim font-bold">{relativeTime(device.last_seen)}</span>
          </div>
        </div>
      </div>

      {/* Coordinates */}
      {latestLocation && (
        <CoordDisplay lat={latestLocation.lat} lng={latestLocation.lng} />
      )}

      {/* Location Details */}
      {latestLocation && (
        <div className="bg-mag-surface/30 border border-mag-border/30 rounded-xl p-4 space-y-2">
          <div className="flex items-center gap-1.5 text-[11px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold mb-2">
            <LocateFixed size={12} className="text-mag-accent" />
            Location Details
          </div>

          <div className="flex justify-between items-center">
            <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Provider</span>
            <span className="text-[11px] font-mono text-mag-accent font-bold">{latestLocation.provider}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Accuracy</span>
            <span className="text-[11px] font-mono text-mag-text font-bold">±{latestLocation.accuracy?.toFixed(1) || '?'}m</span>
          </div>
          {latestLocation.speed != null && (
            <div className="flex justify-between items-center">
              <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Speed</span>
              <span className="text-[11px] font-mono text-mag-text font-bold">{(latestLocation.speed * 3.6).toFixed(1)} km/h</span>
            </div>
          )}
          {latestLocation.altitude != null && (
            <div className="flex justify-between items-center">
              <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Altitude</span>
              <span className="text-[11px] font-mono text-mag-text font-bold">{latestLocation.altitude.toFixed(0)}m</span>
            </div>
          )}
          {latestLocation.bearing != null && (
            <div className="flex justify-between items-center">
              <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Bearing</span>
              <span className="text-[11px] font-mono text-mag-text font-bold">{latestLocation.bearing.toFixed(0)}°</span>
            </div>
          )}
        </div>
      )}

      {/* Open in Maps */}
      {latestLocation && (
        <a
          href={`https://www.google.com/maps?q=${latestLocation.lat},${latestLocation.lng}`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-2 py-3 rounded-xl border border-mag-border/40 text-mag-text-dim hover:text-mag-text hover:border-mag-border transition-all text-xs font-bold"
        >
          <ExternalLink size={14} />
          Open in Google Maps
        </a>
      )}

      {!latestLocation && (
        <div className="text-mag-text-dim/30 text-[10px] font-mono text-center py-4">
          No location data available yet.
        </div>
      )}
    </div>
  );
}
