'use client';

import { useState } from 'react';
import { useStore } from '@/store/useStore';
import { MapView } from '@/components/map/MapView';
import { CommandPanel } from '@/components/commands/CommandPanel';
import { MediaGallery } from '@/components/media/MediaGallery';
import { DevicePanel } from '@/components/devices/DevicePanel';
import { SentinelPanel } from '@/components/panels/SentinelPanel';
import { EvidencePanel } from '@/components/panels/EvidencePanel';
import { GeofencePanel } from '@/components/panels/GeofencePanel';
import { ErrorPanel } from '@/components/panels/ErrorPanel';
import { GuardianPanel } from '@/components/panels/GuardianPanel';
import { Tabs } from '@/components/ui/Tabs';
import { TabId } from '@/types';
import { Shield, Terminal, MapPin, Fence, Camera, ClipboardList, Bug, ShieldCheck } from 'lucide-react';

const PANEL_TABS = [
  { id: 'sentinel' as TabId, label: 'Sentinel', icon: Shield },
  { id: 'commands' as TabId, label: 'Commands', icon: Terminal },
  { id: 'location' as TabId, label: 'Location', icon: MapPin },
  { id: 'zones' as TabId, label: 'Zones', icon: Fence },
  { id: 'media' as TabId, label: 'Media', icon: Camera },
  { id: 'evidence' as TabId, label: 'Evidence', icon: ClipboardList },
  { id: 'guardian' as TabId, label: 'Guardian', icon: ShieldCheck },
  { id: 'errors' as TabId, label: 'Errors', icon: Bug },
];

export default function DashboardPage() {
  const { activeTab, setActiveTab, devices, selectedDeviceId } = useStore();
  const [rightPanelOpen, setRightPanelOpen] = useState(true);

  // Milestone 2 P1 RBAC: a device_only share (status glance, no location)
  // must not see tabs whose endpoints would 403 — the server strips
  // coordinates anyway, so hiding them is honest UX, not the security
  // boundary (that is _assert_device_access min_role on every endpoint).
  const selectedDevice = devices.find(d => d.id === selectedDeviceId);
  const accessRole: 'owner' | 'admin' | 'viewer' | 'device_only' = selectedDevice?.access_role ?? 'owner';
  const visibleTabs = accessRole === 'device_only'
    ? PANEL_TABS.filter(t => !['location', 'zones', 'media', 'evidence'].includes(t.id))
    : PANEL_TABS;
  // If the active tab is hidden by the role (e.g. the user was on Location
  // and the selected device became a device_only share), fall back to a
  // visible tab so the panel area never renders blank.
  const effectiveTab = visibleTabs.some(t => t.id === activeTab) ? activeTab : 'sentinel';

  return (
    <div className="flex h-full">
      {/* Map (Main Area) */}
      <MapView />

      {/* Right Panel — Military Grade White */}
      <div className={`bg-white border-l border-gray-200 flex flex-col transition-all duration-300 ease-out relative ${rightPanelOpen ? 'w-80' : 'w-0 overflow-hidden'}`}>
        {/* Subtle left accent rail */}
        <div className="absolute left-0 top-0 bottom-0 w-px bg-gradient-to-b from-transparent via-gray-300 to-transparent pointer-events-none" />

        {/* Panel Toggle */}
        <button
          onClick={() => setRightPanelOpen(!rightPanelOpen)}
          className="absolute right-0 top-1/2 -translate-y-1/2 z-50 w-5 h-10 flex items-center justify-center bg-white border border-gray-200 rounded-l-lg hover:bg-gray-50 transition-colors shadow-sm group"
        >
          <svg
            width="10" height="10" viewBox="0 0 24 24"
            fill="none" stroke="currentColor" strokeWidth="2"
            className={`text-gray-400 group-hover:text-gray-600 transition-transform duration-200 ${rightPanelOpen ? 'rotate-180' : ''}`}
          >
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>

        {rightPanelOpen && (
          <>
            {/* Tabs — Military Style */}
            <Tabs
              tabs={visibleTabs}
              activeTab={effectiveTab}
              onTabChange={setActiveTab}
            />

            {/* Tab Content */}
            <div className="flex-1 overflow-y-auto">
              {effectiveTab === 'sentinel' && <SentinelPanel />}
              {effectiveTab === 'commands' && <CommandPanel />}
              {effectiveTab === 'location' && <DevicePanel />}
              {effectiveTab === 'zones' && <GeofencePanel />}
              {effectiveTab === 'media' && <MediaGallery />}
              {effectiveTab === 'evidence' && <EvidencePanel />}
              {effectiveTab === 'guardian' && <GuardianPanel />}
              {effectiveTab === 'errors' && <ErrorPanel />}
            </div>

            {/* Panel footer — Military Status */}
            <div className="px-4 py-2 border-t border-gray-200 flex items-center justify-between relative">
              <div className="flex items-center gap-1.5">
                <span className="w-1 h-1 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.4)] animate-pulse-slow" />
                <span className="text-[8px] font-mono text-emerald-600 font-bold uppercase tracking-wider">Live</span>
              </div>
              <span className="text-[8px] font-mono text-gray-400 font-bold uppercase tracking-wider">Magneetar OS</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
