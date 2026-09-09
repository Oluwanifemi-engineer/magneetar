'use client';

import { useState, useEffect } from 'react';
import { useStore } from '@/store/useStore';
import { MapView } from '@/components/map/MapView';
import { CommandPanel } from '@/components/commands/CommandPanel';
import { MediaGallery } from '@/components/media/MediaGallery';
import { DevicePanel } from '@/components/devices/DevicePanel';
import { SentinelPanel } from '@/components/panels/SentinelPanel';
import { EvidencePanel } from '@/components/panels/EvidencePanel';
import { GeofencePanel } from '@/components/panels/GeofencePanel';
import { ErrorPanel } from '@/components/panels/ErrorPanel';

import { FloatingActions } from '@/components/map/FloatingActions';
import { DeviceDrawer } from '@/components/layout/DeviceDrawer';
import { BottomSheet } from '@/components/ui/BottomSheet';
import { MobileTabBar } from '@/components/ui/MobileTabBar';
import { Tabs } from '@/components/ui/Tabs';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { TabId } from '@/types';
import { cn, isOnline, deviceDisplayName, relativeTime } from '@/lib/utils';

import {
  Shield, Terminal, MapPin, Fence, Camera,
  ClipboardList, Bug,
  ChevronLeft, ChevronRight, Menu, Radio, X
} from 'lucide-react';

const PANEL_TABS = [
  { id: 'sentinel' as TabId, label: 'Sentinel', icon: Shield },
  { id: 'commands' as TabId, label: 'Commands', icon: Terminal },
  { id: 'location' as TabId, label: 'Location', icon: MapPin },
  { id: 'zones' as TabId, label: 'Zones', icon: Fence },
  { id: 'media' as TabId, label: 'Media', icon: Camera },
  { id: 'evidence' as TabId, label: 'Evidence', icon: ClipboardList },

  { id: 'errors' as TabId, label: 'Errors', icon: Bug },
];

function useIsMobile() {
  const [mobile, setMobile] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)');
    setMobile(mq.matches);
    const handler = (e: MediaQueryListEvent) => setMobile(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);
  return mobile;
}

function DashboardSkeleton() {
  return (
    <div className="flex h-full bg-mag-bg">
      <div className="w-64 border-r border-mag-border bg-mag-bg p-4 space-y-4 shrink-0 hidden md:block">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-mag-border-light/30 animate-pulse" />
          <div className="space-y-1.5">
            <div className="h-3 bg-mag-border-light/30 rounded w-24 animate-pulse" />
            <div className="h-2 bg-mag-border-light/20 rounded w-16 animate-pulse" />
          </div>
        </div>
        <div className="h-px bg-mag-border" />
        <div className="space-y-2">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-20 mag-skeleton rounded-xl animate-pulse" />
          ))}
        </div>
      </div>
      <div className="flex-1 bg-mag-bg relative">
        <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/[0.03] via-transparent to-blue-500/[0.03] animate-pulse" />
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-12 h-12 rounded-full border-2 border-emerald-500/20 border-t-emerald-500 animate-spin" />
        </div>
      </div>
      <div className="w-80 border-l border-mag-border bg-mag-bg p-4 space-y-4 shrink-0 hidden md:block">
        <div className="flex gap-2">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-10 flex-1 mag-skeleton rounded-xl animate-pulse" />
          ))}
        </div>
        <div className="space-y-3">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-16 mag-skeleton rounded-xl animate-pulse" />
          ))}
        </div>
      </div>
    </div>
  );
}

function TabContent({ tab }: { tab: TabId }) {
  return (
    <ErrorBoundary>
      {tab === 'sentinel' && <SentinelPanel />}
      {tab === 'commands' && <CommandPanel />}
      {tab === 'location' && <DevicePanel />}
      {tab === 'zones' && <GeofencePanel />}
      {tab === 'media' && <MediaGallery />}
      {tab === 'evidence' && <EvidencePanel />}

      {tab === 'errors' && <ErrorPanel />}
    </ErrorBoundary>
  );
}

/**
 * Mobile Peek Content — shows inside the bottom sheet at peek state.
 * Displays selected device name, online status, and distance.
 */
function MobilePeekContent() {
  const { devices, selectedDeviceId } = useStore();
  const selectedDevice = devices.find(d => d.id === selectedDeviceId);

  if (!selectedDevice) {
    return (
      <div className="flex items-center gap-3">          <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: 'rgba(31,41,55,0.4)', border: '1px solid rgba(31,41,55,0.5)' }}>
            <Radio size={16} className="text-mag-text-muted" />
        </div>
        <div>
          <div className="text-[12px] font-bold text-white/50">No device selected</div>
          <div className="text-[9px] font-mono text-white/20">Open device list to select one</div>
        </div>
      </div>
    );
  }

  const online = isOnline(selectedDevice.last_seen);

  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-3">
        <div className={cn(
          'w-9 h-9 rounded-xl flex items-center justify-center',
          online ? 'bg-emerald-500/10' : 'bg-mag-surface/40'
        )}>
          <span className={cn(
            'w-2.5 h-2.5 rounded-full',
            online ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)] animate-pulse' : 'bg-mag-surface-raised'
          )} />
        </div>
        <div>
          <div className="text-[13px] font-bold text-white/85">{deviceDisplayName(selectedDevice)}</div>
          <div className="flex items-center gap-2">
            <span className={cn(
              'text-[9px] font-mono font-bold uppercase',
              online ? 'text-emerald-400/70' : 'text-white/25'
            )}>
              {online ? 'Online' : 'Offline'}
            </span>
            <span className="text-[8px] font-mono text-white/20">·</span>
            <span className="text-[9px] font-mono text-white/25">{relativeTime(selectedDevice.last_seen)}</span>
          </div>
        </div>
      </div>
      <div className="text-right">
        <div className="text-[10px] font-mono font-bold text-white/30 tabular-nums">
          {selectedDevice.sentinel_score}
        </div>
        <div className="text-[7px] font-mono text-white/15 uppercase">Score</div>
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const { activeTab, setActiveTab, devices, selectedDeviceId, _hasHydrated, setSidebarOpen, sidebarOpen } = useStore();
  const [rightPanelOpen, setRightPanelOpen] = useState(false);
  const [mobileSheetState, setMobileSheetState] = useState<'peek' | 'half' | 'full' | 'hidden'>('hidden');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [desktopMenuOpen, setDesktopMenuOpen] = useState(false);
  const isMobile = useIsMobile();

  // Close the floating command menu when the sidebar opens (avoids overlap)
  useEffect(() => {
    if (sidebarOpen && desktopMenuOpen) setDesktopMenuOpen(false);
  }, [sidebarOpen]);

  const selectedDevice = devices.find(d => d.id === selectedDeviceId);
  const accessRole: 'owner' | 'admin' | 'viewer' | 'device_only' = selectedDevice?.access_role ?? 'owner';
  const visibleTabs = accessRole === 'device_only'
    ? PANEL_TABS.filter(t => !['location', 'zones', 'media', 'evidence'].includes(t.id))
    : PANEL_TABS;
  const effectiveTab = visibleTabs.some(t => t.id === activeTab) ? activeTab : 'sentinel';

  if (!_hasHydrated) {
    return <DashboardSkeleton />;
  }

  // ═══════════════════════════════════════════════════════════════════
  // MOBILE LAYOUT — Apple Find My / Google Maps pattern
  // Map is fullscreen. Everything else is in bottom sheets and drawers.
  // ═══════════════════════════════════════════════════════════════════
  if (isMobile) {
    return (
      <div className="relative w-full h-full bg-mag-bg overflow-hidden">
        {/* Full-screen map — the entire interface */}
        <div className="absolute inset-0 z-0">
          <MapView />
        </div>

        <DeviceDrawer />

        {selectedDeviceId && <FloatingActions />}

        {/* Device list toggle — top-left */}
        <button
          onClick={() => setSidebarOpen(true)}
          className="fixed top-3 left-3 z-[1500] w-10 h-10 rounded-xl mag-map-glass flex items-center justify-center shadow-lg active:scale-95 transition-all"
          aria-label="Open device list"
        >
          <Menu size={15} className="text-mag-text-dim" />
        </button>

        {/* Main menu — top-right, opens feature grid */}
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="fixed top-3 right-3 z-[1500] w-10 h-10 rounded-xl mag-map-glass flex items-center justify-center shadow-lg active:scale-95 transition-all"
          aria-label="Open menu"
        >
          {mobileMenuOpen ? (
            <X size={15} className="text-mag-text-dim" />
          ) : (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="1"/><circle cx="12" cy="5" r="1"/><circle cx="12" cy="19" r="1"/>
            </svg>
          )}
        </button>

        {/* ═══ Floating feature grid — appears on menu tap ═══ */}
        {mobileMenuOpen && (
          <div className="fixed top-16 right-3 z-[1600] w-48 mag-map-glass animate-fade-in">
            <div className="text-[8px] font-mono text-mag-text-muted uppercase tracking-widest mb-2 px-1">Features</div>
            <div className="grid grid-cols-2 gap-1.5">
              {PANEL_TABS.map(tab => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    onClick={() => {
                      setActiveTab(tab.id);
                      setMobileMenuOpen(false);
                      setMobileSheetState('half');
                    }}                     className="flex items-center gap-2 px-2.5 py-2 rounded-xl hover:bg-surface-hover transition-colors text-left"
                  >
                    <Icon size={12} className="text-mag-text-muted" />
                    <span className="text-[10px] font-mono font-bold text-mag-text-dim uppercase tracking-wider">{tab.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        <BottomSheet
          initial="hidden"
          onStateChange={setMobileSheetState}
          peekContent={<MobilePeekContent />}
        >
          <MobileTabBar
            tabs={visibleTabs}
            activeTab={effectiveTab}
            onTabChange={setActiveTab}
          />
          <div className="mt-3 pb-20">
            <TabContent tab={effectiveTab} />
          </div>
        </BottomSheet>
      </div>
    );
  }

  // ═══════════════════════════════════════════════════════════════════
  // DESKTOP LAYOUT — Sidebar + Map + Right Panel
  // ═══════════════════════════════════════════════════════════════════
  return (
    <div className="flex h-full relative bg-mag-bg noise-overlay">
      {/* ═══ Full-screen map — the entire interface ═══ */}
      <div className="flex-1 h-full">
        <MapView />
      </div>

      {/* ═══ Floating menu — positioned next to sidebar ═══ */}
      {!sidebarOpen && (
        <button
          onClick={() => setDesktopMenuOpen(!desktopMenuOpen)}           className="hidden md:flex fixed top-4 left-[52px] z-[1500] h-10 px-3 items-center gap-2 rounded-xl mag-map-glass shadow-lg hover:bg-surface-hover hover:border-mag-border/50 transition-all group"
          aria-label="Open menu"
        >
          {desktopMenuOpen ? (
            <X size={14} className="text-mag-text-dim" />
          ) : (
            <>
              <Menu size={14} className="text-mag-text-dim" />
              <span className="text-[10px] font-mono font-bold text-mag-text-dim uppercase tracking-wider">Menu</span>
            </>
          )}
        </button>
      )}

      {sidebarOpen && desktopMenuOpen && null}

      {/* ═══ Desktop feature dropdown ═══ */}
      {desktopMenuOpen && (
        <div className="hidden md:block fixed top-16 left-[52px] z-[1600] w-56 mag-map-glass animate-fade-in">
          <div className="text-[8px] font-mono text-mag-text-muted uppercase tracking-widest mb-2 px-1">Command Center</div>
          <div className="space-y-1">
            {PANEL_TABS.map(tab => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => {
                    setActiveTab(tab.id);
                    setDesktopMenuOpen(false);
                    setRightPanelOpen(true);
                  }}                   className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl hover:bg-surface-hover transition-colors text-left"
                >
                  <Icon size={14} className="text-mag-text-muted" />
                  <span className="text-[11px] font-mono font-bold text-mag-text-dim uppercase tracking-wider">{tab.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* ═══ Right Panel Toggle — only visible when panel is closed ═══ */}
      {!rightPanelOpen && (
        <button
          onClick={() => setRightPanelOpen(true)}           className="hidden md:flex fixed top-4 right-4 z-[1500] h-10 px-3 items-center gap-2 rounded-xl mag-map-glass shadow-lg hover:bg-surface-hover hover:border-mag-border/50 transition-all group"
          aria-label="Open panel"
        >
          <Terminal size={14} className="text-mag-text-dim" />
          <span className="text-[10px] font-mono font-bold text-mag-text-dim uppercase tracking-wider">Commands</span>
        </button>
      )}

      {/* ═══ Right Panel ═══ */}
      <div
        className={`hidden md:flex flex-col shadow-2xl transition-all duration-300 ease-out ${
          rightPanelOpen ? 'w-80' : 'w-0'
        }`}
      >
        {rightPanelOpen && (
          <div className="mag-panel-elevated flex flex-col border-l-0 shadow-2xl">
            {/* Panel header */}
            <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: 'rgba(31,41,55,0.5)' }}>
              <div className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)] animate-pulse" />
                <span className="text-[10px] font-mono text-emerald-400/70 font-bold uppercase tracking-wider">Live</span>
              </div>
              <button
                onClick={() => setRightPanelOpen(false)}                 className="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-surface-hover transition-colors"
                aria-label="Close panel"
              >
                <X size={13} className="text-mag-text-muted" />
              </button>
            </div>

            <Tabs tabs={visibleTabs} activeTab={effectiveTab} onTabChange={setActiveTab} />
            <div className="flex-1 overflow-y-auto">
              <TabContent tab={effectiveTab} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
