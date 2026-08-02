'use client';

import { cn } from '@/lib/utils';
import type { LucideIcon } from 'lucide-react';

export type CommandTone = 'primary' | 'accent' | 'warning' | 'danger';

interface CommandButtonProps {
  command: string;
  label: string;
  icon: LucideIcon;
  tone?: CommandTone;
  loading?: boolean;
  disabled?: boolean;
  onSend: () => void;
  title?: string;
}

// Tone-driven premium styling: glassy gradient tile, hairline highlight,
// colored glow on hover. Danger (wipe) reads unmistakably destructive.
const TONE_STYLES: Record<CommandTone, string> = {
  primary:
    'border-mag-primary/25 text-mag-primary bg-gradient-to-b from-mag-primary/[0.09] via-transparent to-transparent ' +
    'hover:border-mag-primary/60 hover:shadow-[0_0_24px_rgba(233,30,140,0.14)]',
  accent:
    'border-mag-secondary/25 text-mag-secondary bg-gradient-to-b from-mag-secondary/[0.09] via-transparent to-transparent ' +
    'hover:border-mag-secondary/60 hover:shadow-[0_0_24px_rgba(6,182,212,0.14)]',
  warning:
    'border-mag-warning/25 text-mag-warning bg-gradient-to-b from-mag-warning/[0.09] via-transparent to-transparent ' +
    'hover:border-mag-warning/60 hover:shadow-[0_0_24px_rgba(245,158,11,0.14)]',
  danger:
    'border-mag-danger/30 text-mag-danger bg-gradient-to-b from-mag-danger/[0.1] via-transparent to-transparent ' +
    'hover:border-mag-danger/70 hover:shadow-[0_0_24px_rgba(239,68,68,0.18)]',
};

export function CommandButton({
  command,
  label,
  icon: Icon,
  tone = 'primary',
  loading,
  disabled,
  onSend,
  title,
}: CommandButtonProps) {
  return (
    <button
      onClick={onSend}
      disabled={loading || disabled}
      title={title}
      aria-label={label}
      className={cn(
        'group relative flex flex-col items-center gap-2 py-3.5 px-1 rounded-xl border transition-all duration-200',
        'hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.97]',
        'disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:translate-y-0',
        TONE_STYLES[tone],
      )}
    >
      {/* Top hairline highlight */}
      <span className="pointer-events-none absolute inset-x-3 top-0 h-px bg-gradient-to-r from-transparent via-white/25 to-transparent opacity-0 transition-opacity duration-200 group-hover:opacity-100" />

      {loading ? (
        <svg className="animate-spin" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 12a9 9 0 1 1-6.219-8.56" />
        </svg>
      ) : (
        <span className="w-8 h-8 rounded-lg bg-current/10 border border-current/20 flex items-center justify-center transition-all duration-200 group-hover:bg-current/[0.16] group-hover:shadow-[0_0_12px_currentColor]">
          <Icon size={15} strokeWidth={2.2} />
        </span>
      )}
      <span className="text-[8px] font-mono font-bold uppercase tracking-widest leading-none">
        {label}
      </span>
    </button>
  );
}
