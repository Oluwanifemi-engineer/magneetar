'use client';

import { cn, SignalLevel } from '@/lib/utils';

interface StatusIndicatorProps {
  isOnline: boolean;
  signal: SignalLevel;
  lastSeen?: string;
  className?: string;
}

export function StatusIndicator({ isOnline, signal, lastSeen, className }: StatusIndicatorProps) {
  const signalBars = {
    strong: 4,
    medium: 3,
    weak: 2,
    none: 0,
  };

  const signalColors = {
    strong: 'bg-mag-accent',
    medium: 'bg-mag-accent',
    weak: 'bg-mag-warning',
    none: 'bg-mag-text-dim/40',
  };

  const bars = signalBars[signal];

  return (
    <div className={cn('flex items-center gap-1.5', className)}>
      {/* Signal bars */}
      <div className="flex items-end gap-px h-3">
        {[1, 2, 3, 4].map((level) => (
          <div
            key={level}
            className={cn(
              'w-[3px] rounded-sm transition-colors duration-300',
              level <= bars ? signalColors[signal] : 'bg-mag-border/50',
              level <= bars && signal === 'strong' && 'shadow-[0_0_4px_rgba(34,197,94,0.3)]'
            )}
            style={{ height: `${level * 20}%` }}
          />
        ))}
      </div>

      {/* Status dot */}
      <div className={cn(
        'w-1.5 h-1.5 rounded-full transition-colors duration-300',
        isOnline ? 'bg-mag-accent shadow-[0_0_6px_rgba(34,197,94,0.4)]' : 'bg-mag-text-dim/30'
      )} />

      {/* Status text */}
      <span className={cn(
        'text-[10px] font-mono font-bold uppercase tracking-wider',
        isOnline ? 'text-mag-accent/80' : 'text-mag-text-dim/50'
      )}>
        {isOnline ? 'ONLINE' : 'OFFLINE'}
      </span>
    </div>
  );
}
