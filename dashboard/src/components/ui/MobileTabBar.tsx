'use client';

import { cn } from '@/lib/utils';
import { TabId } from '@/types';
import { LucideIcon, ChevronUp } from 'lucide-react';

/**
 * MobileTabBar — minimal horizontal scrollable tab bar for mobile.
 *
 * Shows only the current tab name with a chevron.
 * Tap to expand into a horizontal scrollable list.
 * Designed to sit inside the bottom sheet's peek area.
 */

interface MobileTabBarProps {
  tabs: { id: TabId; label: string; icon?: LucideIcon }[];
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
  className?: string;
}

export function MobileTabBar({ tabs, activeTab, onTabChange, className }: MobileTabBarProps) {
  const activeTabData = tabs.find(t => t.id === activeTab);

  return (
    <div className={cn('overflow-x-auto scrollbar-hide', className)}>
      <div className="flex gap-1.5 pb-1">
        {tabs.map(tab => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-lg whitespace-nowrap',
                'text-[10px] font-mono font-bold uppercase tracking-wider',
                'transition-all duration-200 active:scale-[0.95] shrink-0',
                isActive
                  ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/25'
                  : 'text-mag-text-muted bg-mag-surface/30 border border-transparent hover:text-mag-text hover:bg-mag-surface-raised/40',
              )}
            >
              {Icon && <Icon size={11} className={isActive ? 'text-emerald-400' : 'text-mag-text-muted'} />}
              {tab.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
