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

// Clean military-grade styling: solid borders, no gradients, no glows
const TONE_STYLES: Record<CommandTone, string> = {
  primary: 'border-gray-900 text-gray-900 hover:bg-gray-900 hover:text-white',
  accent: 'border-gray-700 text-gray-700 hover:bg-gray-700 hover:text-white',
  warning: 'border-amber-600 text-amber-600 hover:bg-amber-600 hover:text-white',
  danger: 'border-red-600 text-red-600 hover:bg-red-600 hover:text-white',
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
        'group relative flex flex-col items-center gap-2 py-3.5 px-1 rounded-xl border-2 transition-all duration-200',
        'active:scale-[0.97]',
        'disabled:opacity-40 disabled:cursor-not-allowed',
        TONE_STYLES[tone],
      )}
    >
      {loading ? (
        <svg className="animate-spin" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 12a9 9 0 0 1 14.08 0"/>
        </svg>
      ) : (
        <span className="w-8 h-8 rounded-lg bg-current/10 border border-current/20 flex items-center justify-center transition-all duration-200">
          <Icon size={15} strokeWidth={2.2} />
        </span>
      )}
      <span className="text-[8px] font-mono font-bold uppercase tracking-widest leading-none">
        {label}
      </span>
    </button>
  );
}
