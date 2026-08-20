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
    <div className="grid grid-cols-4 border-b border-gray-200">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            title={tab.label}
            className={cn(
              'flex items-center justify-center gap-1.5 px-3 py-3',
              'text-[10px] font-bold tracking-wide font-mono uppercase',
              'cursor-pointer transition-all duration-200',
              'border-b-2 border-transparent',
              isActive
                ? 'text-gray-900 border-gray-900 bg-gray-50'
                : 'text-gray-400 hover:text-gray-600',
              'relative shrink-0 min-w-0 flex-col gap-1'
            )}
          >
            {Icon && <Icon size={13} className={cn(isActive ? 'text-gray-900' : 'text-gray-400')} />}
            <span className="font-bold whitespace-nowrap text-[9px]">{tab.label}</span>
            {tab.badge !== undefined && tab.badge > 0 && (
              <span className="ml-1 px-1.5 py-0.5 text-[9px] font-bold bg-red-50 text-red-600 border border-red-200 rounded-full">
                {tab.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
