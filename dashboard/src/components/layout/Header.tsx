'use client';

import { useState } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { cn } from '@/lib/utils';

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
    <header className="h-12 bg-mag-panel/90 backdrop-blur-sm border-b border-mag-border flex items-center px-4 gap-4 z-50">
      {/* Logo */}
      <div className="flex items-center gap-2 mr-2">
        <div className="w-6 h-6 rounded bg-mag-primary/10 border border-mag-primary/30 flex items-center justify-center">
          <span className="text-mag-primary text-xs font-bold">M</span>
        </div>
        <span className="font-display text-sm font-bold tracking-[0.2em] text-mag-primary">
          MAGNEE<span className="text-mag-text-dim">TAR</span>
        </span>
      </div>

      {/* Status Indicator */}
      <div className="flex items-center gap-2">
        <div className={cn(
          'w-2 h-2 rounded-full transition-colors duration-300',
          isConnected ? 'bg-mag-primary shadow-[0_0_8px_rgba(0,232,123,0.5)] animate-pulse-slow' : 'bg-mag-text-dim'
        )} />
        <span className="text-[10px] font-mono text-mag-text-dim uppercase tracking-widest">
          {connecting ? 'CONNECTING...' : isConnected ? 'CONNECTED' : 'DISCONNECTED'}
        </span>
      </div>

      {/* Connection Form (shown when not connected) */}
      {!isAuthenticated && (
        <div className="flex items-center gap-2 ml-auto">
          <input
            type="text"
            value={inputUrl}
            onChange={(e) => setInputUrl(e.target.value)}
            placeholder="Server URL"
            className="mag-input w-56 text-xs"
          />
          <input
            type="password"
            value={inputKey}
            onChange={(e) => setInputKey(e.target.value)}
            placeholder="API Key"
            className="mag-input w-32 text-xs"
            onKeyDown={(e) => e.key === 'Enter' && handleConnect()}
          />
          <button onClick={handleConnect} className="mag-btn-primary text-xs" disabled={connecting}>
            {connecting ? '...' : 'CONNECT'}
          </button>
        </div>
      )}

      {/* Connected Info */}
      {isAuthenticated && (
        <div className="flex items-center gap-3 ml-auto">
          <span className="text-[10px] font-mono text-mag-text-dim truncate max-w-[200px]">
            {serverUrl}
          </span>

          {/* Alerts indicator */}
          {unreadAlertCount > 0 && (
            <div className="relative">
              <span className="text-mag-warning text-sm">🔔</span>
              <span className="absolute -top-1 -right-1 w-3.5 h-3.5 bg-mag-danger text-[8px] font-bold text-white rounded-full flex items-center justify-center">
                {unreadAlertCount > 9 ? '9+' : unreadAlertCount}
              </span>
            </div>
          )}

          <button onClick={handleDisconnect} className="mag-btn-ghost text-xs">
            DISCONNECT
          </button>
        </div>
      )}
    </header>
  );
}
