'use client';

import { cn, isDestructiveCommand } from '@/lib/utils';
import { Lock, Camera } from 'lucide-react';

interface CommandButtonProps {
  command: string;
  label: string;
  icon: string;
  loading?: boolean;
  onSend: () => void;
}

export function CommandButton({ command, label, icon, loading, onSend }: CommandButtonProps) {
  const isDestructive = isDestructiveCommand(command);
  const isLock = command === 'lock';
  const isCapture = command.includes('capture');

  return (
    <button
      onClick={onSend}
      disabled={loading}
      className={cn(
        'flex flex-col items-center gap-1.5 p-3 rounded-xl border transition-all duration-200',
        'hover:scale-[1.02] active:scale-[0.98]',
        'disabled:opacity-40 disabled:cursor-not-allowed',
        isDestructive && 'border-mag-danger/30 text-mag-danger bg-mag-danger/5 hover:bg-mag-danger/10 hover:border-mag-danger/50',
        isLock && 'border-mag-warning/30 text-mag-warning bg-mag-warning/5 hover:bg-mag-warning/10 hover:border-mag-warning/50',
        isCapture && 'border-mag-secondary/30 text-mag-secondary bg-mag-secondary/5 hover:bg-mag-secondary/10 hover:border-mag-secondary/50',
        !isDestructive && !isLock && !isCapture && 'border-mag-primary/30 text-mag-primary bg-mag-primary/5 hover:bg-mag-primary/10 hover:border-mag-primary/50',
      )}
    >
      {loading ? (
        <svg className="animate-spin" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
        </svg>
      ) : (
        <span className="text-lg">{icon}</span>
      )}
      <span className="text-[10px] font-mono font-bold uppercase tracking-wider">
        {label}
      </span>
    </button>
  );
}
