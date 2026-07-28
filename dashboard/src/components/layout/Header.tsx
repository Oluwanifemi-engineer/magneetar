'use client';

import { useState } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { cn } from '@/lib/utils';
import { LogOut, Wifi, Bell, Settings } from 'lucide-react';

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
      {/* Brand */}
      <div className="flex items-center gap-3 shrink-0">
        <img src="/logo.svg" alt="Magneetar" className="h-8 w-auto" onError={(e) => (e.currentTarget.style.display = 'none')} />
        <span className="text-sm font-display font-bold tracking-[0.25em] text-mag-text">
          MAGNEETAR
        </span>
      </div>

      {/* Status Indicator */}
      <div className="flex items-center gap-2.5">
        <div className={cn(
          'w-2.5 h-2.5 rounded-full transition-all duration-300',
          isConnected ? 'bg-mag-accent shadow-[0_0_12px_rgba(34,197,94,0.5)]' : 'bg-mag-text-dim/40'
        )} />
        <span className={cn(
          'text-[11px] font-mono uppercase tracking-widest font-bold transition-colors',
          isConnected ? 'text-mag-accent' : 'text-mag-text-dim/60'
        )}>
          {connecting ? 'CONNECTING...' : isConnected ? 'CONNECTED' : 'DISCONNECTED'}
        </span>
      </div>

      {/* Divider */}
      <div className="h-5 w-px bg-mag-border/40" />

      {/* Connection Form (shown when not authenticated) */}
      {!isAuthenticated && (
        <div className="flex items-center gap-2 ml-auto">
          <input
            type="text"
            value={inputUrl}
            onChange={(e) => setInputUrl(e.target.value)}
            placeholder="Server URL"
            className="mag-input w-52 text-xs"
          />
          <input
            type="password"
            value={inputKey}
            onChange={(e) => setInputKey(e.target.value)}
            placeholder="API Key"
            className="mag-input w-28 text-xs"
            onKeyDown={(e) => e.key === 'Enter' && handleConnect()}
          />
          <button onClick={handleConnect} className="mag-btn-primary text-[11px]" disabled={connecting}>
            {connecting ? (
              <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
            ) : (
              <Wifi size={14} />
            )}
            CONNECT
          </button>
        </div>
      )}

      {/* Connected Info */}
      {isAuthenticated && (
        <div className="flex items-center gap-4 ml-auto">
          {/* Server URL */}
          <div className="flex items-center gap-1.5 text-[11px] font-mono text-mag-text-dim/60">
            <Settings size={12} />
            <span className="truncate max-w-[180px]">{serverUrl}</span>
          </div>

          {/* Alerts indicator */}
          {unreadAlertCount > 0 && (
            <button className="relative hover:opacity-80 transition-opacity">
              <Bell size={18} className="text-mag-warning" />
              <span className="absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px] bg-mag-danger text-[10px] font-bold text-white rounded-full flex items-center justify-center px-1 shadow-lg">
                {unreadAlertCount > 9 ? '9+' : unreadAlertCount}
              </span>
            </button>
          )}

          {/* Disconnect button */}
          <button
            onClick={handleDisconnect}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-mono font-bold text-mag-text-dim/70 hover:text-mag-danger hover:bg-mag-danger/5 border border-transparent hover:border-mag-danger/20 transition-all"
          >
            <LogOut size={12} />
            DISCONNECT
          </button>
        </div>
      )}
    </header>
  );
}
