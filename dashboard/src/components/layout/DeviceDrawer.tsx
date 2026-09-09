'use client';

import { useState, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { cn, isOnline, relativeTime, deviceDisplayName, getSignalLevel } from '@/lib/utils';
import { StatusIndicator } from '@/components/ui/StatusIndicator';
import { Smartphone, X, ChevronRight, Wifi, WifiOff } from 'lucide-react';

/**
 * DeviceDrawer — slide-out device list for mobile.
 *
 * Replaces the sidebar on mobile. Slides from left edge.
 * Shows device list with online status, signal, and sentinel score.
 * Tap device → closes drawer → map centers on device → bottom sheet shows details.
 */

export function DeviceDrawer() {
  const { devices, selectedDeviceId, selectDevice, sidebarOpen, setSidebarOpen } = useStore();
  const [touchStart, setTouchStart] = useState(0);

  const activeDevices = devices.filter(d => !d.archived_at);
  const archivedDevices = devices.filter(d => !!d.archived_at);

  const handleSelect = useCallback((deviceId: string) => {
    selectDevice(deviceId);
    setSidebarOpen(false);
  }, [selectDevice, setSidebarOpen]);

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    setTouchStart(e.touches[0].clientX);
  }, []);

  const handleTouchEnd = useCallback((e: React.TouchEvent) => {
    const delta = e.changedTouches[0].clientX - touchStart;
    // Swipe left to close
    if (delta < -50) {
      setSidebarOpen(false);
    }
  }, [touchStart, setSidebarOpen]);

  return (
    <>
      {/* Backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-[1900] bg-mag-bg/80 backdrop-blur-sm md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Drawer */}
      <div
        className={cn(
          'fixed top-0 left-0 bottom-0 z-[1950] w-72',
          'bg-mag-bg/98 backdrop-blur-2xl',
          'border-r border-mag-border/',
          'flex flex-col',
          'transition-transform duration-300 ease-out',
          'md:hidden',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full',
        )}
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-4 pb-3 border-b border-mag-border">
          <div className="flex items-center gap-3">
            <img src="/magneetar-mhalf.svg" alt="" className="w-7 h-7 rounded-lg" />
            <div>
              <div className="text-[10px] font-bold tracking-[0.2em] text-mag-text">MAGNEETAR</div>
              <div className="text-[8px] font-mono text-mag-text-muted uppercase tracking-wider">Devices</div>
            </div>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="w-8 h-8 rounded-xl flex items-center justify-center hover:bg-mag-surface-raised transition-colors"
            aria-label="Close device list"
          >
            <X size={16} className="text-mag-text-muted" />
          </button>
        </div>

        {/* Device count */}
        <div className="px-5 py-2 border-b border-mag-border">
          <div className="flex items-center gap-2 text-[9px] font-mono font-bold text-mag-text-muted uppercase tracking-wider">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
            {activeDevices.length} active
            {archivedDevices.length > 0 && (
              <span className="text-amber-400/50">· {archivedDevices.length} archived</span>
            )}
          </div>
        </div>

        {/* Device list */}
        <div className="flex-1 overflow-y-auto overscroll-contain">
          {[...activeDevices, ...archivedDevices].map((device) => {
            const archived = !!device.archived_at;
            const online = isOnline(device.last_seen);
            const isSelected = selectedDeviceId === device.id;

            return (
              <button
                key={device.id}
                onClick={() => handleSelect(device.id)}
                className={cn(
                  'w-full text-left px-5 py-3.5 border-b border-mag-border',
                  'transition-all duration-200 active:scale-[0.98]',
                  isSelected
                    ? 'bg-emerald-500/[0.06] border-l-2 border-l-emerald-500'
                    : 'border-l-2 border-l-transparent hover:bg-mag-surface-raised',
                  archived && 'opacity-50',
                )}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[13px] font-bold text-mag-text truncate max-w-[70%]">
                    {deviceDisplayName(device)}
                  </span>
                  <div className="flex items-center gap-2">
                    <StatusIndicator isOnline={online} signal={getSignalLevel(device.last_seen)} className="scale-75" />
                    <ChevronRight size={12} className="text-mag-text-muted" />
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-[9px] text-mag-text-muted truncate">{device.id}</span>
                  <span className="flex items-center gap-1">
                    <span className={cn(
                      'w-1.5 h-1.5 rounded-full',
                      online ? 'bg-emerald-500' : 'bg-mag-surface-raised'
                    )} />
                    <span className="font-mono text-[8px] text-mag-text-muted">
                      {relativeTime(device.last_seen)}
                    </span>
                  </span>
                </div>
              </button>
            );
          })}

          {devices.length === 0 && (
            <div className="flex flex-col items-center justify-center py-12 px-6 text-center">
              <Smartphone size={24} className="text-mag-text-muted mb-3" />
              <div className="text-[12px] font-bold text-mag-text mb-1">No devices yet</div>
              <div className="text-[10px] font-mono text-mag-text-muted leading-relaxed">
                Connect your first device to start tracking
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
