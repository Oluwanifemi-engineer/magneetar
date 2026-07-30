'use client';

import { useState } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { cn } from '@/lib/utils';
import { LogOut, Bell, Settings } from 'lucide-react';

export function Header() {
  const {
    serverUrl, apiKey, isAuthenticated, isConnected,
    setCredentials, setConnected, logout, unreadAlertCount,
  } = useStore();

  const [inputUrl, setInputUrl] = useState(serverUrl);
  const [inputKey, setInputKey] = useState(apiKey);
  const [connecting, setConnecting] = useState(false);

  const handleConnect = async () => {
    if (!inputUrl || !inputKey) return;
    setConnecting(true);
    try {
      const api = getAPI(inputUrl, inputKey);
      await api.healthCheck();
      setCredentials(inputUrl, inputKey);
      setConnected(true);
    } catch (e) {
      console.error('Connection failed:', e);
      setConnected(false);
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnect = () => {
    logout();
    setInputUrl('');
    setInputKey('');
  };

  return (
    <header className="h-14 bg-mag-panel/95 backdrop-blur-xl border-b border-mag-border/60 flex items-center px-5 gap-4 z-50 shadow-mag-panel">
      {/* ─── Brand — M Logo ──────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 shrink-0">
        <div className="w-8 h-8 rounded-lg bg-white/[0.03] border border-white/[0.08] flex items-center justify-center overflow-hidden">
          <img src="/m-logo.svg" alt="M" className="w-5 h-5" />
        </div>
        <span className="text-sm font-display font-bold tracking-[0.25em] text-mag-text">
          MAGNEETAR
        </span>
      </div>

      {/* ─── Status Indicator ────────────────────────────────────────────── */}
      <div className="flex items-center gap-2.5">
        <div className={cn(
          'w-2 h-2 rounded-full transition-all duration-300',
          isConnected ? 'bg-mag-accent shadow-[0_0_12px_rgba(34,197,94,0.5)] animate-pulse-slow' : 'bg-mag-text-dim/30'
        )} />
        <span className={cn(
          'text-[10px] font-mono uppercase tracking-widest font-bold transition-colors',
          isConnected ? 'text-mag-accent' : 'text-mag-text-dim/40'
        )}>
          {connecting ? 'CONNECTING...' : isConnected ? 'CONNECTED' : 'DISCONNECTED'}
        </span>
      </div>

      {/* Vertical divider */}
      <div className="h-5 w-px bg-mag-border/30 shrink-0" />

      {/* ─── Connection Form (shown when not authenticated) ──────────────── */}
      {!isAuthenticated && (
        <div className="flex items-center gap-2 ml-auto">
          <div className="relative">
            <Settings size={12} className="absolute left-3 top-1/2 -translate-y-1/2 text-mag-text-dim/30" />
            <input
              type="text"
              value={inputUrl}
              onChange={(e) => setInputUrl(e.target.value)}
              placeholder="https://api.magneetar.me"
              className="mag-input w-52 text-[11px] pl-8"
            />
          </div>
          <input
            type="password"
            value={inputKey}
            onChange={(e) => setInputKey(e.target.value)}
            placeholder="API Key"
            className="mag-input w-28 text-[11px]"
            onKeyDown={(e) => e.key === 'Enter' && handleConnect()}
          />
          <button
            onClick={handleConnect}
            disabled={connecting}
            className="mag-btn-primary text-[10px] h-[42px]"
          >
            {connecting ? (
              <svg className="animate-spin" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
              </svg>
            ) : (
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 12.55a11 11 0 0 1 14.08 0"/>
                <path d="M1.42 9a16 16 0 0 1 21.16 0"/>
                <path d="M8.53 16.11a6 6 0 0 1 6.95 0"/>
                <circle cx="12" cy="20" r="1"/>
              </svg>
            )}
            CONNECT
          </button>
        </div>
      )}

      {/* ─── Connected Info ──────────────────────────────────────────────── */}
      {isAuthenticated && (
        <div className="flex items-center gap-4 ml-auto">
          {/* Server URL */}
          <div className="flex items-center gap-1.5 text-[10px] font-mono text-mag-text-dim/40 px-2 py-1 rounded-lg bg-mag-surface/20 border border-mag-border/20">
            <Settings size={11} className="shrink-0" />
            <span className="truncate max-w-[140px]">{serverUrl}</span>
          </div>

          {/* Alerts indicator */}
          {unreadAlertCount > 0 && (
            <button className="relative hover:opacity-80 transition-opacity group">
              <Bell size={16} className="text-mag-warning/80 group-hover:text-mag-warning" />
              <span className="absolute -top-1.5 -right-1.5 min-w-[16px] h-[16px] bg-mag-danger text-[9px] font-bold text-white rounded-full flex items-center justify-center px-1 shadow-lg shadow-mag-danger/30">
                {unreadAlertCount > 9 ? '9+' : unreadAlertCount}
              </span>
            </button>
          )}

          {/* Disconnect button */}
          <button
            onClick={handleDisconnect}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] font-mono font-bold text-mag-text-dim/50 hover:text-mag-danger hover:bg-mag-danger/[0.04] border border-transparent hover:border-mag-danger/15 transition-all"
          >
            <LogOut size={11} />
            DISCONNECT
          </button>
        </div>
      )}
    </header>
  );
}
