'use client';

import { useState } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { cn } from '@/lib/utils';
import { LogOut, Bell, Settings } from 'lucide-react';
import { SettingsModal } from '@/components/layout/SettingsModal';

export function Header() {
  const {
    serverUrl, apiKey, isAuthenticated, isConnected,
    setCredentials, setConnected, logout, unreadAlertCount,
  } = useStore();

  const [inputUrl, setInputUrl] = useState(serverUrl);
  const [inputKey, setInputKey] = useState(apiKey);
  const [connecting, setConnecting] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

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
    <header className="h-14 bg-white border-b border-gray-200 flex items-center px-5 gap-4 z-50 relative">
      {/* Subtle top hairline */}
      <div className="absolute top-0 left-0 right-0 h-px bg-gradient-to-r from-transparent via-gray-300 to-transparent pointer-events-none" />

      {/* ─── Brand — M Logo ──────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 shrink-0 relative">
        <img src="/magneetar-mhalf.svg" alt="Magneetar" className="w-8 h-8 rounded-lg" />
        <div className="flex flex-col leading-none">
          <span className="text-sm font-display font-bold tracking-[0.25em] text-gray-900">
            MAGNEETAR
          </span>
          <span className="mt-1 text-[7px] font-mono tracking-[0.3em] text-gray-400 font-bold">
            COMMAND CENTER
          </span>
        </div>
      </div>

      {/* ─── Status Indicator ────────────────────────────────────────────── */}
      <div className="flex items-center gap-2.5">
        <div className={cn(
          'w-2 h-2 rounded-full transition-all duration-300',
          isConnected ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.4)] animate-pulse-slow' : 'bg-gray-300'
        )} />
        <span className={cn(
          'text-[10px] font-mono uppercase tracking-widest font-bold transition-colors',
          isConnected ? 'text-emerald-600' : 'text-gray-400'
        )}>
          {connecting ? 'CONNECTING...' : isConnected ? 'CONNECTED' : 'DISCONNECTED'}
        </span>
      </div>

      {/* Vertical divider */}
      <div className="h-5 w-px bg-gray-200 shrink-0" />

      {/* ─── Connection Form (shown when not authenticated) ──────────────── */}
      {!isAuthenticated && (
        <div className="flex items-center gap-2 ml-auto">
          <div className="relative">
            <Settings size={12} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
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
                <path d="M21 12a9 9 0 0 1 14.08 0"/>
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
          <div className="flex items-center gap-1.5 text-[10px] font-mono text-gray-500 px-2 py-1 rounded-lg bg-gray-50 border border-gray-200">
            <Settings size={11} className="shrink-0" />
            <span className="truncate max-w-[140px]">{serverUrl}</span>
          </div>

          {/* Alerts indicator */}
          {unreadAlertCount > 0 && (
            <button className="relative hover:opacity-80 transition-opacity group">
              <Bell size={16} className="text-amber-500 group-hover:text-amber-600" />
              <span className="absolute -top-1.5 -right-1.5 min-w-[16px] h-[16px] bg-red-500 text-[9px] font-bold text-white rounded-full flex items-center justify-center px-1 shadow-lg shadow-red-500/30">
                {unreadAlertCount > 9 ? '9+' : unreadAlertCount}
              </span>
            </button>
          )}

          {/* Disconnect button */}
          <button
            onClick={handleDisconnect}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] font-mono font-bold text-gray-500 hover:text-red-600 hover:bg-red-50 border border-transparent hover:border-red-200 transition-all"
          >
            <LogOut size={11} />
            DISCONNECT
          </button>

          {/* Settings — account info + Danger Zone live in the modal, NOT the
              header, so a stressed operator can't delete the account by accident */}
          <button
            onClick={() => setSettingsOpen(true)}
            title="Settings"
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] font-mono font-bold text-gray-500 hover:text-gray-900 hover:bg-gray-100 border border-transparent hover:border-gray-200 transition-all"
          >
            <Settings size={11} />
            SETTINGS
          </button>
        </div>
      )}

      {/* Settings modal */}
      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </header>
  );
}
