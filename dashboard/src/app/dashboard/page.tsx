'use client';

import { useState } from 'react';
import { useStore } from '@/store/useStore';
import { MapView } from '@/components/map/MapView';
import { CommandPanel } from '@/components/commands/CommandPanel';
import { MediaGallery } from '@/components/media/MediaGallery';
import { DevicePanel } from '@/components/devices/DevicePanel';
import { SentinelPanel } from '@/components/panels/SentinelPanel';
import { EvidencePanel } from '@/components/panels/EvidencePanel';
import { ErrorPanel } from '@/components/panels/ErrorPanel';
import { Tabs } from '@/components/ui/Tabs';
import { TabId } from '@/types';
import { Shield, Terminal, MapPin, Camera, ClipboardList, Bug } from 'lucide-react';

const PANEL_TABS = [
  { id: 'sentinel' as TabId, label: 'Sentinel', icon: Shield },
  { id: 'commands' as TabId, label: 'Commands', icon: Terminal },
  { id: 'location' as TabId, label: 'Location', icon: MapPin },
  { id: 'media' as TabId, label: 'Media', icon: Camera },
  { id: 'evidence' as TabId, label: 'Evidence', icon: ClipboardList },
  { id: 'errors' as TabId, label: 'Errors', icon: Bug },
];

export default function DashboardPage() {
  const { activeTab, setActiveTab } = useStore();
  const [rightPanelOpen, setRightPanelOpen] = useState(true);

  return (
    <div className="flex h-full">
      {/* Map (Main Area) */}
      <MapView />

      {/* Right Panel */}
      <div className={`bg-mag-panel/90 backdrop-blur-xl border-l border-mag-border/60 flex flex-col transition-all duration-300 ease-out relative ${rightPanelOpen ? 'w-80' : 'w-0 overflow-hidden'}`}>
        {/* Panel Toggle */}
        <button
          onClick={() => setRightPanelOpen(!rightPanelOpen)}
          className="absolute right-0 top-1/2 -translate-y-1/2 z-50 w-5 h-10 flex items-center justify-center bg-mag-panel/90 border border-mag-border/60 rounded-l-lg hover:bg-mag-surface transition-colors shadow-sm group"
        >
          <svg
            width="10" height="10" viewBox="0 0 24 24"
            fill="none" stroke="currentColor" strokeWidth="2"
            className={`text-mag-text-dim/40 group-hover:text-mag-text-dim transition-transform duration-200 ${rightPanelOpen ? 'rotate-180' : ''}`}
          >
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>

        {rightPanelOpen && (
          <>
            {/* Tabs */}
            <Tabs
              tabs={PANEL_TABS}
              activeTab={activeTab}
              onTabChange={setActiveTab}
            />

            {/* Tab Content */}
            <div className="flex-1 overflow-y-auto">
              {activeTab === 'sentinel' && <SentinelPanel />}
              {activeTab === 'commands' && <CommandPanel />}
              {activeTab === 'location' && <DevicePanel />}
              {activeTab === 'media' && <MediaGallery />}
              {activeTab === 'evidence' && <EvidencePanel />}
              {activeTab === 'errors' && <ErrorPanel />}
            </div>

            {/* Panel footer */}
            <div className="px-4 py-2 border-t border-mag-border/30 flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <div className="w-1 h-1 rounded-full bg-mag-accent/40" />
                <span className="text-[8px] font-mono text-mag-text-dim/30 font-bold uppercase tracking-wider">Live</span>
              </div>
              <div className="w-1 h-1 rounded-full bg-mag-primary/30" />
            </div>
          </>
        )}
      </div>
    </div>
  );
}
