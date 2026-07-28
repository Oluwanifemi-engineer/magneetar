'use client';

import { useState, useEffect, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { cn, getCommandLabel, isDestructiveCommand, formatTimestamp } from '@/lib/utils';
import { CommandButton } from '@/components/ui/CommandButton';
import { Terminal, MessageSquare, Send } from 'lucide-react';
import { CommandType } from '@/types';

const COMMANDS: { command: CommandType; label: string; icon: string }[] = [
  { command: 'ping', label: 'PING', icon: '📡' },
  { command: 'capture_photo', label: 'PHOTO', icon: '📷' },
  { command: 'capture_audio', label: 'AUDIO', icon: '🎤' },
  { command: 'lock', label: 'LOCK', icon: '🔒' },
  { command: 'siren', label: 'SIREN', icon: '🚨' },
  { command: 'wipe', label: 'WIPE', icon: '💣' },
];

export function CommandPanel() {
  const { commands, setCommands, selectedDeviceId } = useStore();
  const [sending, setSending] = useState<string | null>(null);
  const [displayMessage, setDisplayMessage] = useState('');
  const [messageSent, setMessageSent] = useState(false);

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

  // Send command
  const handleSend = async (command: string, params = '') => {
    if (!selectedDeviceId) return;
    setSending(command);
    try {
      const api = getAPI();
      await api.issueCommand(selectedDeviceId, command, params);
      await fetchCommands();
    } catch (e) {
      console.error('Command failed:', e);
    } finally {
      setSending(null);
    }
  };

  // Send display message
  const handleSendMessage = async () => {
    if (!displayMessage.trim() || !selectedDeviceId) return;
    await handleSend('display_message', displayMessage);
    setDisplayMessage('');
    setMessageSent(true);
    setTimeout(() => setMessageSent(false), 2000);
  };

  return (
    <div className="p-4 space-y-4">
      {/* Quick Actions */}
      <div>
        <div className="text-[11px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold mb-2.5 px-1">
          Quick Actions
        </div>
        <div className="grid grid-cols-3 gap-2">
          {COMMANDS.map(({ command, label, icon }) => (
            <CommandButton
              key={command}
              command={command}
              label={label}
              icon={icon}
              loading={sending === command}
              onSend={() => handleSend(command)}
            />
          ))}
        </div>
      </div>

      {/* Display Message */}
      <div>
        <div className="flex items-center gap-1.5 text-[11px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold mb-2.5 px-1">
          <MessageSquare size={12} className="text-mag-secondary" />
          Display Message
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={displayMessage}
            onChange={(e) => setDisplayMessage(e.target.value)}
            placeholder="Type message to display on device..."
            className="mag-input text-xs flex-1"
            onKeyDown={(e) => e.key === 'Enter' && handleSendMessage()}
          />
          <button
            onClick={handleSendMessage}
            disabled={!displayMessage.trim() || sending === 'display_message'}
            className="mag-btn-primary px-3 py-2 text-[11px]"
          >
            {messageSent ? (
              <span className="text-mag-accent">✓</span>
            ) : (
              <Send size={14} />
            )}
          </button>
        </div>
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
