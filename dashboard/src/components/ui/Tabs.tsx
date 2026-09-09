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
    <div className="flex flex-col h-full">
      <div className="px-2 pt-2 pb-0 border-b border-mag-border/50 bg-mag-bg">
        <div className="flex gap-1 overflow-x-auto scrollbar-hide pb-2">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => onTabChange(tab.id)}
                title={tab.label}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-2 rounded-lg whitespace-nowrap',
                  'text-[10px] font-bold font-mono uppercase tracking-wider',
                  'cursor-pointer transition-all duration-200',
                  'active:scale-[0.97] shrink-0',
                  isActive
                    ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/25 shadow-[0_0_12px_rgba(16,185,129,0.15)]'
                    : 'text-mag-text-muted hover:text-mag-text hover:bg-surface-hover bg-transparent border border-transparent',
                )}
              >
                {Icon && <Icon size={12} strokeWidth={2} className={isActive ? 'text-emerald-400' : 'text-mag-text-muted'} />}
                <span>{tab.label}</span>
                {tab.badge !== undefined && tab.badge > 0 && (
                  <span className="px-1 py-0.5 text-[7px] font-bold bg-red-500/90 text-white rounded-full leading-none">
                    {tab.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto">
        {tabs.find((t) => t.id === activeTab) && <div />}
      </div>
    </div>
  );
}
