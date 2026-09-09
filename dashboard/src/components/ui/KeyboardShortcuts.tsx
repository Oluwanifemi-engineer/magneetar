'use client';

import { useEffect, useState } from 'react';
import { X, Keyboard } from 'lucide-react';

interface Shortcut {
  keys: string[];
  description: string;
  category: string;
}

const SHORTCUTS: Shortcut[] = [
  // Navigation
  { keys: ['G', 'H'], description: 'Go to Home', category: 'Navigation' },
  { keys: ['G', 'D'], description: 'Go to Dashboard', category: 'Navigation' },
  { keys: ['G', 'S'], description: 'Go to Settings', category: 'Navigation' },

  // Devices
  { keys: ['↑', '↓'], description: 'Navigate devices', category: 'Devices' },
  { keys: ['Enter'], description: 'Select device', category: 'Devices' },
  { keys: ['Esc'], description: 'Deselect device', category: 'Devices' },

  // Commands
  { keys: ['C'], description: 'Open command panel', category: 'Commands' },
  { keys: ['M'], description: 'Capture photo', category: 'Commands' },
  { keys: ['A'], description: 'Capture audio', category: 'Commands' },
  { keys: ['L'], description: 'Lock device', category: 'Commands' },
  { keys: ['W'], description: 'Wipe device', category: 'Commands' },

  // Map
  { keys: ['+'], description: 'Zoom in', category: 'Map' },
  { keys: ['-'], description: 'Zoom out', category: 'Map' },
  { keys: ['F'], description: 'Fit bounds', category: 'Map' },

  // General
  { keys: ['?'], description: 'Show shortcuts', category: 'General' },
  { keys: ['K'], description: 'Show shortcuts', category: 'General' },
  { keys: ['/'], description: 'Focus search', category: 'General' },
  { keys: ['Esc'], description: 'Close modal', category: 'General' },
];

export function KeyboardShortcutsHelp() {
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger in input fields
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        return;
      }

      // ? or K to open shortcuts
      if (e.key === '?' || (e.key === 'k' && !e.metaKey && !e.ctrlKey)) {
        e.preventDefault();
        setIsOpen(true);
      }

      // Escape to close
      if (e.key === 'Escape' && isOpen) {
        setIsOpen(false);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  if (!isOpen) return null;

  const categories = [...new Set(SHORTCUTS.map(s => s.category))];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-mag-bg/70 backdrop-blur-sm">
      <div className="w-full max-w-2xl mx-5 p-6 max-h-[80vh] overflow-y-auto mag-panel-elevated">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center bg-mag-surface border border-mag-border">
              <Keyboard size={20} className="text-mag-text" />
            </div>
            <div>
              <h2 className="text-lg font-display font-extrabold text-mag-text">Keyboard Shortcuts</h2>
              <p className="text-[11px] font-mono text-mag-text-muted">Navigate faster with shortcuts</p>
            </div>
          </div>
          <button
            onClick={() => setIsOpen(false)}
            className="w-8 h-8 rounded-lg flex items-center justify-center hover:bg-surface-hover transition-all"
          >
            <X size={16} className="text-mag-text-muted hover:text-mag-text" />
          </button>
        </div>

        {/* Shortcuts by category */}
        <div className="space-y-6">
          {categories.map((category) => (
            <div key={category}>
              <div className="text-[10px] font-mono font-bold text-mag-text-muted uppercase tracking-wider mb-3">
                {category}
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {SHORTCUTS.filter(s => s.category === category).map((shortcut, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between py-2 px-3 rounded-lg bg-mag-surface/30 border border-mag-border/50"
                  >
                    <span className="text-[12px] text-mag-text-dim">{shortcut.description}</span>
                    <div className="flex items-center gap-1">
                      {shortcut.keys.map((key, j) => (
                        <span key={j}>
                          <kbd className="inline-flex items-center justify-center min-w-[24px] h-6 px-2 rounded-md bg-mag-surface-raised border border-mag-border text-[11px] font-mono font-bold text-mag-text">
                            {key}
                          </kbd>
                          {j < shortcut.keys.length - 1 && (
                            <span className="text-mag-text-muted mx-1">+</span>
                          )}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="mt-6 pt-4 border-t border-mag-border/50 text-center">
          <p className="text-[11px] font-mono text-mag-text-muted">
            Press <kbd className="px-1.5 py-0.5 rounded bg-mag-surface-raised border border-mag-border text-mag-text font-mono text-[11px] font-bold">?</kbd> or <kbd className="px-1.5 py-0.5 rounded bg-mag-surface-raised border border-mag-border text-mag-text font-mono text-[11px] font-bold">K</kbd> to toggle this panel
          </p>
        </div>
      </div>
    </div>
  );
}

// Hook for using keyboard shortcuts in components
export function useKeyboardShortcuts(handlers: Record<string, () => void>) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger in input fields
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        return;
      }

      const key = e.key.toLowerCase();
      const combo = e.ctrlKey || e.metaKey ? `mod+${key}` : key;

      if (handlers[combo]) {
        e.preventDefault();
        handlers[combo]();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handlers]);
}
