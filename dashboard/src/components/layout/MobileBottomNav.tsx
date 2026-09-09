'use client';

import { useState } from 'react';
import { useStore } from '@/store/useStore';
import { cn } from '@/lib/utils';
import {
  Terminal,
  MapPin,
  Camera,
  Shield,
  Users,
  Settings,
  Menu,
  Fence,
  ClipboardList,
  ShieldCheck,
  Bug,
} from 'lucide-react';
import type { TabId } from '@/types';

import type { LucideIcon } from 'lucide-react';

interface NavItem {
  id: TabId;
  label: string;
  icon: LucideIcon;
  shortLabel: string;
}

const NAV_ITEMS: NavItem[] = [
  { id: 'sentinel', label: 'Safe', icon: Shield, shortLabel: 'Safe' },
  { id: 'commands', label: 'Commands', icon: Terminal, shortLabel: 'Cmd' },
  { id: 'location', label: 'Location', icon: MapPin, shortLabel: 'Loc' },
  { id: 'media', label: 'Media', icon: Camera, shortLabel: 'Media' },
  { id: 'family', label: 'Family', icon: Users, shortLabel: 'Family' },
];

const MORE_ITEMS: { id: TabId; label: string; icon: LucideIcon }[] = [
  { id: 'zones', label: 'Geofence', icon: Fence },
  { id: 'evidence', label: 'Evidence', icon: ClipboardList },
  { id: 'guardian', label: 'Guardian', icon: ShieldCheck },
  { id: 'errors', label: 'Errors', icon: Bug },
];

export function MobileBottomNav() {
  const { activeTab, setActiveTab, sidebarOpen, setSidebarOpen } = useStore();
  const [showMore, setShowMore] = useState(false);

  return (
    <>
      {/* More menu overlay */}
      {showMore && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div
            className="absolute inset-0 bg-mag-bg/80 backdrop-blur-md"
            onClick={() => setShowMore(false)}
          />
          <div className="absolute bottom-20 left-2 right-2 bg-mag-surface-raised/95 backdrop-blur-xl rounded-2xl shadow-2xl border-mag-border p-3 animate-fade-in">
            <div className="text-[8px] font-mono text-mag-text-muted uppercase tracking-wider font-bold px-2 mb-2">
              More Features
            </div>
            <div className="grid grid-cols-2 gap-1.5">
              {MORE_ITEMS.map((item) => {
                const Icon = item.icon;
                const isActive = activeTab === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => {
                      setActiveTab(item.id);
                      setShowMore(false);
                    }}
                    className={cn(
                      'flex items-center gap-2.5 px-3 py-3 rounded-xl transition-all text-left',
                      'active:scale-[0.97]',
                      isActive
                        ? 'bg-mag-surface text-mag-text'
                        : 'bg-mag-surface hover:bg-mag-surface-raised text-mag-text-muted hover:text-mag-text-dim'
                    )}
                  >
                    <Icon size={15} />
                    <span className="text-[11px] font-semibold">{item.label}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Bottom navigation bar — Premium Dark Glass */}
      <nav
        className="fixed bottom-0 left-0 right-0 z-30 md:hidden bg-mag-bg/95 backdrop-blur-xl border-t border-mag-border safe-area-bottom"
        aria-label="Main navigation"
        role="navigation"
      >
        <div className="flex items-center justify-around px-1 py-1.5">
          {/* Sidebar toggle (hamburger) */}
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            aria-label={sidebarOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={sidebarOpen}
            className={cn(
              'flex flex-col items-center justify-center gap-0.5 w-14 py-2.5 rounded-xl transition-all duration-200',
              'active:scale-[0.92]',
              sidebarOpen
                ? 'text-mag-text bg-mag-surface-raised'
                : 'text-mag-text-muted active:bg-mag-surface-raised'
            )}
          >
            <Menu size={18} aria-hidden="true" />
            <span className="text-[7px] font-bold">Menu</span>
          </button>

          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                aria-label={item.label}
                aria-current={isActive ? 'page' : undefined}
                className={cn(
                  'flex flex-col items-center justify-center gap-0.5 w-14 py-2.5 rounded-xl transition-all duration-200',
                  'active:scale-[0.92]',
                  isActive
                    ? 'text-emerald-400 bg-emerald-500/[0.08]'
                    : 'text-mag-text-muted active:bg-mag-surface-raised'
                )}
              >
                <Icon size={18} aria-hidden="true" />
                <span className="text-[7px] font-bold">{item.shortLabel}</span>
              </button>
            );
          })}

          {/* More button */}
          <button
            onClick={() => setShowMore(!showMore)}
            aria-label="More features"
            aria-expanded={showMore}
            aria-haspopup="true"
            className={cn(
              'flex flex-col items-center justify-center gap-0.5 w-14 py-2.5 rounded-xl transition-all duration-200',
              'active:scale-[0.92]',
              showMore
                ? 'text-mag-text bg-mag-surface-raised'
                : 'text-mag-text-muted active:bg-mag-surface-raised'
            )}
          >
            <Settings size={18} aria-hidden="true" />
            <span className="text-[7px] font-bold">More</span>
          </button>
        </div>
      </nav>
    </>
  );
}
