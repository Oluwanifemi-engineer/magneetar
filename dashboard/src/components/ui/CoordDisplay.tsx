'use client';

import { cn } from '@/lib/utils';

interface CoordDisplayProps {
  lat: number;
  lng: number;
}

export function CoordDisplay({ lat, lng }: CoordDisplayProps) {
  return (
    <div className="bg-mag-surface/30 border border-mag-border/30 rounded-xl p-4">
      <div className="text-[11px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold flex items-center gap-1.5 mb-3">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-mag-primary">
          <circle cx="12" cy="12" r="10"/>
          <path d="M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20z"/>
          <path d="M2 12h20"/>
        </svg>
        Coordinates
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-mag-bg/40 border border-mag-border/30 rounded-lg p-3">
          <div className="font-mono text-mag-primary text-sm font-bold tracking-tight">
            {lat.toFixed(6)}
          </div>
          <div className="text-[10px] font-mono text-mag-text-dim/50 mt-0.5 font-bold">Latitude</div>
        </div>
        <div className="bg-mag-bg/40 border border-mag-border/30 rounded-lg p-3">
          <div className="font-mono text-mag-primary text-sm font-bold tracking-tight">
            {lng.toFixed(6)}
          </div>
          <div className="text-[10px] font-mono text-mag-text-dim/50 mt-0.5 font-bold">Longitude</div>
        </div>
      </div>
    </div>
  );
}
