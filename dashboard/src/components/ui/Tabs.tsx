'use client';

import { cn } from '@/lib/utils';
import { TabId } from '@/types';
import { LucideIcon } from 'lucide-react';

interface Tab {
  id: TabId;
  label: string;
  icon?: LucideIcon;
  badge?: number;
}

interface TabsProps {
  tabs: Tab[];
  activeTab: TabId;
  onTabChange: (tab: TabId) => void;
}

export function Tabs({ tabs, activeTab, onTabChange }: TabsProps) {
  // Two-row wrap grid: 8 tabs at 4-per-row always fit the narrow right panel
  // (w-80) without clipping — a horizontal scrollbar hid the trailing tabs
  // (Guardian, Errors) with no visible affordance, so they were unreachable.
  return (
    <div className="grid grid-cols-4 border-b border-mag-border/40">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            title={tab.label}
            className={cn('mag-tab relative shrink-0 min-w-0 flex-col gap-1', isActive && 'active')}
          >
            {Icon && <Icon size={13} className={cn(isActive ? 'text-mag-primary' : 'text-mag-text-dim/50')} />}
            <span className="font-bold whitespace-nowrap text-[9px]">{tab.label}</span>
            {tab.badge !== undefined && tab.badge > 0 && (
              <span className="ml-1 px-1.5 py-0.5 text-[9px] font-bold bg-mag-danger/15 text-mag-danger rounded-full">
                {tab.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
