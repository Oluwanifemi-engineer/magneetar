'use client';

import { useState } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';
import { cn, getCommandLabel, stepUpPasswordHint } from '@/lib/utils';
import { Radio, Siren, Lock, X, Zap } from 'lucide-react';

/**
 * FloatingActions — Uber/Lyft-style floating quick actions on the map.
 *
 * Shows 3 primary actions (Ping, Siren, Lock) as floating circles.
 * Tap to execute immediately. Long-press or tap overflow for more.
 * Hidden on desktop (desktop has the right panel).
 */

interface FloatingAction {
  id: string;
  label: string;
  icon: typeof Radio;
  color: string;
  glow: string;
  command: string;
}

const PRIMARY_ACTIONS: FloatingAction[] = [
  {
    id: 'ping',
    label: 'Ping',
    icon: Radio,
    color: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
    glow: 'shadow-[0_0_20px_rgba(16,185,129,0.25)]',
    command: 'ping',
  },
  {
    id: 'siren',
    label: 'Siren',
    icon: Siren,
    color: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    glow: 'shadow-[0_0_20px_rgba(245,158,11,0.25)]',
    command: 'alarm',
  },
  {
    id: 'lock',
    label: 'Lock',
    icon: Lock,
    color: 'bg-red-500/20 text-red-400 border-red-500/30',
    glow: 'shadow-[0_0_20px_rgba(239,68,68,0.25)]',
    command: 'lock',
  },
];

export function FloatingActions() {
  const { selectedDeviceId, devices } = useStore();
  const { toast } = useToast();
  const [sending, setSending] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [confirmAction, setConfirmAction] = useState<string | null>(null);

  const selectedDevice = devices.find(d => d.id === selectedDeviceId);
  const accessRole = selectedDevice?.access_role ?? 'owner';
  const canCommand = accessRole === 'owner' || accessRole === 'admin';

  if (!selectedDeviceId || !canCommand) return null;

  const handleCommand = async (command: string) => {
    setSending(command);
    try {
      const api = getAPI();
      await api.issueCommand(selectedDeviceId, command);
      toast(`${getCommandLabel(command)} sent`, 'success');
    } catch (e: any) {
      toast(e?.message || 'Command failed', 'error');
    } finally {
      setSending(null);
      setConfirmAction(null);
    }
  };

  return (
    <div className="md:hidden fixed bottom-[130px] right-4 z-[1500] flex flex-col items-end gap-3">
      {/* Confirmation tooltip */}
      {confirmAction && (
        <div className="mag-map-glass-compact animate-fade-in max-w-[200px]">
          <div className="text-[10px] font-mono text-mag-text-dim mb-2">
            Send {getCommandLabel(confirmAction)} command?
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => handleCommand(confirmAction)}
              disabled={!!sending}
              className="flex-1 py-1.5 rounded-xl bg-emerald-500 text-white text-[9px] font-mono font-bold uppercase"
            >
              {sending === confirmAction ? '...' : 'Yes'}
            </button>
            <button
              onClick={() => setConfirmAction(null)}
              className="flex-1 py-1.5 rounded-xl border border-mag-border text-mag-text-muted text-[9px] font-mono font-bold uppercase"
            >
              No
            </button>
          </div>
        </div>
      )}

      {/* Primary action buttons */}
      {PRIMARY_ACTIONS.map((action, i) => {
        const Icon = action.icon;
        const isActive = sending === action.command;
        return (
          <button
            key={action.id}
            onClick={() => {
              if (action.command === 'lock') {
                setConfirmAction(action.command);
              } else {
                handleCommand(action.command);
              }
            }}
            disabled={isActive}
            className={cn(
              'w-12 h-12 rounded-full flex items-center justify-center',
              'border backdrop-blur-xl transition-all duration-200',
              'active:scale-90',
              isActive
                ? 'bg-mag-surface-raised/70 border-mag-border/50 animate-pulse'
                : action.color,
              action.glow,
            )}
            title={action.label}
            aria-label={action.label}
          >
            {isActive ? (
              <div className="w-5 h-5 rounded-full border-2 border-current border-t-transparent animate-spin" />
            ) : (
              <Icon size={18} strokeWidth={2.2} />
            )}
          </button>
        );
      })}

      {/* Overflow button for more commands */}
      <button
        onClick={() => setExpanded(!expanded)}
        className={cn(
          'w-10 h-10 rounded-full flex items-center justify-center',
          'border backdrop-blur-xl transition-all duration-200 active:scale-90',
          expanded
            ? 'bg-mag-surface-raised/70 border-mag-border/50 text-mag-text-muted'
            : 'bg-mag-surface-raised border-mag-border/50 text-mag-text-muted',
        )}
        title="More commands"
        aria-label="More commands"
      >
        {expanded ? <X size={16} /> : <Zap size={16} />}
      </button>

      {/* Expanded overflow menu */}
      {expanded && (
        <div className="mag-map-glass rounded-2xl p-2 shadow-2xl animate-fade-in">
          <div className="grid grid-cols-3 gap-2">
            {[
              { label: 'Burst', command: 'location_burst', color: 'text-emerald-400' },
              { label: 'Photo', command: 'capture_photo', color: 'text-blue-400' },
              { label: 'Audio', command: 'capture_audio', color: 'text-blue-400' },
              { label: 'Front', command: 'capture_photo_front', color: 'text-blue-400' },
              { label: 'Lost', command: 'lost_mode', color: 'text-red-400' },
              { label: 'Wipe', command: 'wipe', color: 'text-red-500' },
            ].map(item => (
              <button
                key={item.command}
                onClick={() => {
                  if (item.command === 'wipe' || item.command === 'lost_mode') {
                    setConfirmAction(item.command);
                  } else {
                    handleCommand(item.command);
                  }
                  setExpanded(false);
                }}
                className="flex flex-col items-center gap-1 py-2 px-1 rounded-xl hover:bg-mag-surface-hover transition-colors"
              >
                <span className={cn('text-[9px] font-mono font-bold uppercase', item.color)}>
                  {item.label}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
