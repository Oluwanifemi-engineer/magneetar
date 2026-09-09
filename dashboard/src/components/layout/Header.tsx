'use client';

import { useStore } from '@/store/useStore';
import { cn } from '@/lib/utils';
import { LogOut, Shield } from 'lucide-react';

export function Header() {
  const { isConnected, logout, userProfile } = useStore();
  const isAdmin = userProfile?.tier === 'admin';

  return (
    <header className="h-10 bg-mag-bg border-b border-mag-border flex items-center px-4 gap-3 z-50 relative">
      {/* Connection Status — Premium Pulse */}
      <div className="flex items-center gap-2">
        <div className={cn(
          'w-1.5 h-1.5 rounded-full transition-all duration-300',
          isConnected
            ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)] animate-pulse'
            : 'bg-mag-surface-raised'
        )} />
        <span className={cn(
          'text-[9px] font-mono uppercase tracking-widest font-bold transition-colors',
          isConnected ? 'text-emerald-400/70' : 'text-mag-text-muted'
        )}>
          {isConnected ? 'LIVE' : 'OFFLINE'}
        </span>
      </div>

      {/* Trust Signal — Security Badge */}
      <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-mag-surface border-mag-border">
        <Shield size={8} className="text-emerald-400/60" />
        <span className="text-[7px] font-mono text-mag-text-muted uppercase tracking-wider font-bold">
          E2E
        </span>
      </div>

      {/* Admin Badge */}
      {isAdmin && (
        <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-amber-500/[0.06] border border-amber-500/15">
          <span className="text-[7px] font-mono text-amber-400/70 uppercase tracking-wider font-bold">
            ADMIN
          </span>
        </div>
      )}

      <div className="flex-1" />

      {/* Disconnect — Minimal */}
      <button
        onClick={logout}
        className="flex items-center gap-1.5 px-2 py-1 rounded-lg text-[9px] font-mono font-bold text-mag-text-muted hover:text-red-400/70 hover:bg-red-500/[0.06] border border-transparent hover:border-red-500/15 transition-all duration-200 active:scale-95"
      >
        <LogOut size={10} />
        EXIT
      </button>
    </header>
  );
}
