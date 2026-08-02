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
  return (
    // Horizontally scrollable so a full tab set is never clipped/hidden — the
    // right panel is narrow (w-80) and seven tabs at flex-1 each overflow it.
    <div className="flex border-b border-mag-border/40 overflow-x-auto no-scrollbar">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            title={tab.label}
            className={cn('mag-tab flex-1 relative shrink-0 min-w-[52px]', isActive && 'active')}
          >
            {Icon && <Icon size={13} className={cn(isActive ? 'text-mag-primary' : 'text-mag-text-dim/50')} />}
            <span className="font-bold whitespace-nowrap">{tab.label}</span>
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
