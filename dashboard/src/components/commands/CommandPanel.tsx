'use client';

import { useState, useEffect, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { cn, getCommandLabel, isDestructiveCommand, formatTimestamp } from '@/lib/utils';
import { CommandButton, type CommandTone } from '@/components/ui/CommandButton';
import { Radio, Camera, Webcam, Mic, LocateFixed, Lock, Siren, AlertTriangle, CheckCircle2 } from 'lucide-react';
import type { CommandType } from '@/types';

// NOTE: buttons send the WIRE command name, which must match what the server
// (models.CommandRequest.validate_command) and the Android app
// (TrackingService.handleCommand) both accept. The siren button maps to
// 'alarm' — the server/app have no 'siren' command, so sending 'siren'
// would 422 on the server and never reach the device. Every command below is
// implemented end-to-end (dashboard → API → device poll → handleCommand).
const COMMANDS: {
  command: CommandType;
  label: string;
  icon: typeof Radio;
  tone: CommandTone;
  title: string;
}[] = [
  { command: 'ping', label: 'PING', icon: Radio, tone: 'primary', title: 'Check the device is reachable (acks instantly)' },
  { command: 'capture_photo_front', label: 'FRONT', icon: Webcam, tone: 'accent', title: 'Capture front camera photo' },
  { command: 'capture_photo', label: 'PHOTO', icon: Camera, tone: 'accent', title: 'Capture rear camera photo' },
  { command: 'capture_audio', label: 'AUDIO', icon: Mic, tone: 'accent', title: 'Record 20s of audio' },
  { command: 'location_burst', label: 'BURST', icon: LocateFixed, tone: 'primary', title: 'Send 5 rapid location fixes' },
  { command: 'lock', label: 'LOCK', icon: Lock, tone: 'warning', title: 'Lock the device screen instantly' },
  { command: 'alarm', label: 'SIREN', icon: Siren, tone: 'warning', title: 'Play a max-volume alarm' },
  { command: 'wipe', label: 'WIPE', icon: AlertTriangle, tone: 'danger', title: 'Factory reset — requires confirmation' },
];

export function CommandPanel() {
  const { commands, setCommands, selectedDeviceId } = useStore();
  const [sending, setSending] = useState<string | null>(null);
  const [confirmWipe, setConfirmWipe] = useState(false);
  const [commandError, setCommandError] = useState('');
  const [lastSent, setLastSent] = useState('');

  // Fetch commands
  const fetchCommands = useCallback(async () => {
    if (!selectedDeviceId) return;
    try {
      const api = getAPI();
      const res = await api.getCommands(selectedDeviceId);
      setCommands(res.commands);
    } catch (e) {
      console.error('Failed to fetch commands:', e);
    }
  }, [selectedDeviceId, setCommands]);

  useEffect(() => {
    fetchCommands();
    const interval = setInterval(fetchCommands, 10000);
    return () => clearInterval(interval);
  }, [fetchCommands]);

  // Send command. `params` is the wire param — wipe MUST be 'CONFIRMED_WIPE'
  // or the server rejects it with 400 (which is why the old WIPE button
  // silently did nothing).
  const handleSend = async (command: string, params = '') => {
    if (!selectedDeviceId) return;
    setSending(command);
    setCommandError('');
    setLastSent('');
    try {
      const api = getAPI();
      await api.issueCommand(selectedDeviceId, command, params);
      setLastSent(command);
      setTimeout(() => setLastSent(''), 3000);
      await fetchCommands();
    } catch (e: any) {
      setCommandError(e?.message || 'Command failed — check the server connection');
      console.error('Command failed:', e);
    } finally {
      setSending(null);
      setConfirmWipe(false);
    }
  };

  const handleClick = (command: string) => {
    setCommandError('');
    // Wipe is destructive and needs the CONFIRMED_WIPE wire param — require an
    // explicit confirmation first.
    if (command === 'wipe') {
      setConfirmWipe(true);
      return;
    }
    handleSend(command);
  };

  return (
    <div className="p-4 space-y-4">
      {/* Quick Actions */}
      <div>
        <div className="text-[11px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold mb-2.5 px-1">
          Quick Actions
        </div>
        <div className="grid grid-cols-4 gap-2">
          {COMMANDS.map(({ command, label, icon, tone, title }) => (
            <CommandButton
              key={command}
              command={command}
              label={label}
              icon={icon}
              tone={tone}
              title={title}
              loading={sending === command}
              onSend={() => handleClick(command)}
            />
          ))}
        </div>

        {/* Feedback strip */}
        {commandError && (
          <div className="mt-2.5 flex items-center gap-2 px-3 py-2 rounded-lg bg-mag-danger/[0.06] border border-mag-danger/25 text-mag-danger text-[10px] font-mono font-bold animate-fade-in">
            <AlertTriangle size={11} className="shrink-0" />
            {commandError}
          </div>
        )}
        {!commandError && lastSent && (
          <div className="mt-2.5 flex items-center gap-2 px-3 py-2 rounded-lg bg-mag-accent/[0.06] border border-mag-accent/25 text-mag-accent text-[10px] font-mono font-bold animate-fade-in">
            <CheckCircle2 size={11} className="shrink-0" />
            {getCommandLabel(lastSent)} command sent — the device will pick it up on its next poll.
          </div>
        )}

        {/* Wipe confirmation */}
        {confirmWipe && (
          <div className="mt-3 rounded-xl border border-mag-danger/35 bg-mag-danger/[0.05] p-3.5 space-y-2.5 animate-fade-in">
            <div className="flex items-start gap-2">
              <AlertTriangle size={14} className="text-mag-danger shrink-0 mt-0.5" />
              <div>
                <div className="text-[10px] font-mono text-mag-danger font-bold uppercase tracking-wider">
                  Permanent wipe
                </div>
                <div className="text-[10px] font-mono text-mag-text-dim/70 mt-1 leading-relaxed">
                  This factory-resets the device, erasing ALL data on it. It requires
                  device-admin permission on the phone and cannot be undone.
                </div>
              </div>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => handleSend('wipe', 'CONFIRMED_WIPE')}
                disabled={sending === 'wipe'}
                className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-mag-danger/90 hover:bg-mag-danger disabled:opacity-50 text-white text-[10px] font-mono font-bold uppercase tracking-wider transition-all"
              >
                {sending === 'wipe' ? 'SENDING...' : 'Confirm wipe'}
              </button>
              <button
                onClick={() => setConfirmWipe(false)}
                disabled={sending === 'wipe'}
                className="px-3 py-2 rounded-lg border border-mag-border/40 text-mag-text-dim/70 hover:text-mag-text text-[10px] font-mono font-bold transition-all"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Command History */}
      <div>
        <div className="text-[11px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold mb-2.5 px-1">
          Recent Commands
        </div>
        <div className="space-y-1.5 max-h-48 overflow-y-auto">
          {commands.length === 0 ? (
            <div className="text-mag-text-dim/40 text-xs font-mono text-center py-4">
              No commands sent yet.
            </div>
          ) : (
            commands.slice(0, 10).map((cmd) => (
              <div
                key={cmd.id}
                className="flex items-center gap-3 py-2 px-2 rounded-lg bg-mag-surface/20 border border-mag-border/20"
              >
                <div className={cn(
                  'w-2 h-2 rounded-full',
                  cmd.status === 'expired' ? 'bg-mag-text-dim/30' :
                  cmd.status === 'executed' ? 'bg-mag-accent' :
                  cmd.status === 'failed' ? 'bg-mag-danger' :
                  'bg-mag-warning animate-pulse-slow'
                )} />
                <div className="flex-1 min-w-0">
                  <div className="font-mono text-[11px] text-mag-text font-bold">
                    {getCommandLabel(cmd.command)}
                  </div>
                  <div className="font-mono text-[10px] text-mag-text-dim/50">
                    {formatTimestamp(cmd.issued_at)}
                  </div>
                </div>
                <span className={cn(
                  'text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded-md',
                  cmd.status === 'expired' ? 'text-mag-text-dim/45 bg-mag-text-dim/5 line-through decoration-mag-text-dim/30' :
                  cmd.status === 'executed' ? 'text-mag-accent bg-mag-accent/10' :
                  cmd.status === 'failed' ? 'text-mag-danger bg-mag-danger/10' :
                  'text-mag-warning bg-mag-warning/10'
                )}>
                  {cmd.status}
                </span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
