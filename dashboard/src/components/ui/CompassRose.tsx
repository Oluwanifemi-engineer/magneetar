'use client';

import { cn } from '@/lib/utils';

interface CompassRoseProps {
  bearing: number;
  label: string;
  className?: string;
}

export function CompassRose({ bearing, label, className }: CompassRoseProps) {
  return (
    <div className={cn('flex flex-col items-center', className)}>
      <div className="text-[11px] font-mono text-mag-text-dim/60 uppercase tracking-wider font-bold mb-1">
        Bearing
      </div>
      <div className="font-mono text-mag-primary text-2xl font-bold tracking-tight mb-4 tabular-nums">
        {label} ({Math.round(bearing)}°)
      </div>

      {/* Compass Circle */}
      <div className="relative w-32 h-32">
        {/* Outer ring */}
        <div className="absolute inset-0 rounded-full border-2 border-mag-primary/20" />
        {/* Inner ring */}
        <div className="absolute inset-3 rounded-full border border-mag-primary/10" />

        {/* Tick marks */}
        {Array.from({ length: 36 }).map((_, i) => {
          const angle = i * 10;
          const isCardinal = angle % 90 === 0;
          const isMajor = angle % 45 === 0;
          return (
            <div
              key={i}
              className="absolute top-1/2 left-1/2"
              style={{
                transform: `translate(-50%, -50%) rotate(${angle}deg)`,
                transformOrigin: '0 0',
              }}
            >
              <div className={cn(
                'w-px',
                isCardinal ? 'h-2.5 bg-mag-primary/40' : isMajor ? 'h-2 bg-mag-primary/20' : 'h-1.5 bg-mag-primary/10'
              )} />
            </div>
          );
        })}

        {/* Needle */}
        <div
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 transition-transform duration-500"
          style={{ transform: `translate(-50%, -50%) rotate(${bearing}deg)` }}
        >
          <div className="relative">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-0 h-0 border-l-[5px] border-l-transparent border-r-[5px] border-r-transparent border-b-[14px] border-b-mag-primary drop-shadow-[0_0_8px_rgba(233,30,140,0.4)]" />
            <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-0 h-0 border-l-[5px] border-l-transparent border-r-[5px] border-r-transparent border-t-[14px] border-t-mag-text-dim/30" />
          </div>
        </div>

        {/* Center dot */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-mag-primary shadow-[0_0_12px_rgba(233,30,140,0.6)]" />

        {/* Cardinal labels */}
        <div className="absolute top-1 left-1/2 -translate-x-1/2 text-[11px] font-mono text-mag-primary font-bold">N</div>
        <div className="absolute bottom-1 left-1/2 -translate-x-1/2 text-[11px] font-mono text-mag-text-dim/50 font-bold">S</div>
        <div className="absolute left-1 top-1/2 -translate-y-1/2 text-[11px] font-mono text-mag-text-dim/50 font-bold">W</div>
        <div className="absolute right-1 top-1/2 -translate-y-1/2 text-[11px] font-mono text-mag-text-dim/50 font-bold">E</div>
      </div>

      {/* Direction Label */}
      <div className="mt-4 flex items-center gap-1.5">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-mag-primary">
          <path d="M12 2L2 7l10 5 10-5-10-5z"/>
          <path d="M2 17l10 5 10-5"/>
          <path d="M2 12l10 5 10-5"/>
        </svg>
        <span className="font-mono text-mag-primary text-base font-bold tracking-wide">{label}</span>
        <span className="font-mono text-mag-text-dim/60 text-xs">({Math.round(bearing)}°)</span>
      </div>
    </div>
  );
}
