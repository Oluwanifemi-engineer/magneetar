'use client';

import { useState, useEffect, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { cn, getCommandLabel, isDestructiveCommand, formatTimestamp, stepUpPasswordHint } from '@/lib/utils';
import { CommandButton, type CommandTone } from '@/components/ui/CommandButton';
import { Radio, Camera, Webcam, Mic, LocateFixed, Lock, Siren, AlertTriangle, CheckCircle2, Trash2, X, MessageSquareText } from 'lucide-react';
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
  const { commands, setCommands, selectedDeviceId, devices } = useStore();
  const selectedDevice = devices.find(d => d.id === selectedDeviceId);
  // Offline Command Relay: when the device is offline (no data) but the owner
  // enabled SMS commands, every issued command is ALSO texted to the phone and
  // executed locally. Show an honest notice so the operator knows the delivery
  // path before tapping a command.
  const smsRelayActive = !!selectedDevice &&
    !selectedDevice.is_online &&
    selectedDevice.sms_commands_enabled &&
    !!selectedDevice.sms_phone;
  const [sending, setSending] = useState<string | null>(null);
  const [confirmWipe, setConfirmWipe] = useState(false);
  const [commandError, setCommandError] = useState('');
  const [lastSent, setLastSent] = useState('');
  // Wipe is a factory reset — the server requires the step-up password
  // (account password for users, master API key for admin) before queuing,
  // so this prompt collects it (the server re-verifies; this is not the
  // security boundary).
  const [wipePassword, setWipePassword] = useState('');
  const [wipeError, setWipeError] = useState('');
  // History cleanup (step-up password, mirroring the device/media delete
  // contract): deleting one command or clearing finished history re-
  // authenticates with the account password (users) or master API key (admin).
  const [deleteTarget, setDeleteTarget] = useState<number | 'all-finished' | null>(null);
  const [deletePassword, setDeletePassword] = useState('');
  const [deleteError, setDeleteError] = useState('');
  const [deleting, setDeleting] = useState(false);

  const confirmDelete = async () => {
    if (!selectedDeviceId || deleteTarget === null || deleting) return;
    if (!deletePassword.trim()) {
      setDeleteError('Enter your password to confirm.');
      return;
    }
    setDeleting(true);
    setDeleteError('');
    try {
      const api = getAPI();
      if (deleteTarget === 'all-finished') {
        await api.clearCommandHistory(selectedDeviceId, deletePassword);
      } else {
        await api.deleteCommand(deleteTarget, deletePassword);
      }
      setDeleteTarget(null);
      setDeletePassword('');
      await fetchCommands();
    } catch (e: any) {
      setDeleteError(e?.message || 'Failed to delete command');
    } finally {
      setDeleting(false);
    }
  };

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

  // Device switch while the step-up card is open: a pending deleteTarget from
  // the OLD device must never apply to the NEW device ('all-finished' would
  // clear the wrong device's history; a command id could 404 or hit a same-id
  // row on another owned device). Reset the confirm state whenever the
  // selected device changes.
  useEffect(() => {
    setDeleteTarget(null);
    setDeletePassword('');
    setDeleteError('');
    setDeleting(false);
  }, [selectedDeviceId]);

  // Send command. `params` is the wire param — wipe MUST be 'CONFIRMED_WIPE'
  // or the server rejects it with 400 (which is why the old WIPE button
  // silently did nothing).
  const handleSend = async (command: string, params = '', password?: string) => {
    if (!selectedDeviceId) return;
    // Wipe is a factory reset: the step-up password is mandatory. Validating
    // here (not just in the button's onClick) means the Enter-key path can't
    // bypass it either.
    if (command === 'wipe' && !(password || '').trim()) {
      setWipeError('Enter your password to confirm the wipe.');
      return;
    }
    setSending(command);
    setCommandError('');
    setLastSent('');
    setWipeError('');
    try {
      const api = getAPI();
      await api.issueCommand(selectedDeviceId, command, params, password);
      setLastSent(command);
      setTimeout(() => setLastSent(''), 3000);
      await fetchCommands();
    } catch (e: any) {
      setCommandError(e?.message || 'Command failed — check the server connection');
      console.error('Command failed:', e);
    } finally {
      setSending(null);
      setConfirmWipe(false);
      setWipePassword('');
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
      {/* Offline SMS relay notice — commands reach the phone even with no data */}
      {smsRelayActive && (
        <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-mag-accent/[0.06] border border-mag-accent/25 text-mag-accent animate-fade-in">
          <MessageSquareText size={13} className="shrink-0 mt-0.5" />
          <div className="text-[10px] font-mono leading-relaxed">
            <span className="font-bold">Device offline — commands will be delivered via SMS</span>
            <span className="opacity-80"> to {selectedDevice?.sms_phone}. The phone executes them locally even
            without internet, and the ack returns when it next connects.</span>
          </div>
        </div>
      )}

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
            {getCommandLabel(lastSent)} command sent —{' '}
            {smsRelayActive
              ? 'the phone will execute it from the SMS (no internet needed).'
              : 'the device will pick it up on its next poll.'}
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
            {/* Step-up password: the server re-verifies before queueing the
                wipe (account password for users, master API key for admin) —
                a stolen dashboard session alone can never factory-reset a
                device. */}
            <input
              type="password"
              value={wipePassword}
              onChange={e => setWipePassword(e.target.value)}
              placeholder={stepUpPasswordHint()}
              aria-label="Confirm wipe password"
              autoFocus
              onKeyDown={e => {
                if (e.key === 'Enter' && sending !== 'wipe') {
                  e.preventDefault();
                  handleSend('wipe', 'CONFIRMED_WIPE', wipePassword);
                }
              }}
              className="w-full bg-mag-bg/60 border border-mag-danger/40 rounded-lg px-3 py-2 text-xs font-mono text-mag-text placeholder:text-mag-text-dim/30 focus:outline-none focus:border-mag-danger/70 transition-colors"
            />
            {wipeError && <div className="text-[10px] font-mono text-red-400">{wipeError}</div>}
            <div className="flex gap-2">
              <button
                onClick={() => {
                  if (!wipePassword.trim()) {
                    setWipeError('Enter your password to confirm the wipe.');
                    return;
                  }
                  handleSend('wipe', 'CONFIRMED_WIPE', wipePassword);
                }}
                disabled={sending === 'wipe'}
                className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-mag-danger/90 hover:bg-mag-danger disabled:opacity-50 text-white text-[10px] font-mono font-bold uppercase tracking-wider transition-all"
              >
                {sending === 'wipe' ? 'SENDING...' : 'Confirm wipe'}
              </button>
              <button
                onClick={() => { setConfirmWipe(false); setWipePassword(''); setWipeError(''); }}
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
        <div className="flex items-center justify-between mb-2.5 px-1">
          <div className="text-[11px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold">
            Recent Commands
          </div>
          {commands.filter(c => c.status !== 'pending').length > 0 && deleteTarget !== 'all-finished' && (
            <button
              onClick={() => { setDeleteTarget('all-finished'); setDeleteError(''); }}
              className="flex items-center gap-1 text-[10px] font-mono font-bold uppercase tracking-wider text-mag-text-dim/60 hover:text-mag-danger/80 transition-colors"
              title="Remove ALL executed, failed & expired entries (keeps pending commands)"
            >
              <Trash2 size={11} />
              Clear all finished
            </button>
          )}
        </div>

        {/* Step-up confirm card (password required) */}
        {deleteTarget !== null && (
          <div className="mb-2.5 rounded-xl border border-mag-danger/30 bg-mag-danger/[0.05] p-3.5 space-y-2.5 animate-fade-in">
            <div className="text-[10px] font-mono text-mag-danger/90 leading-relaxed">
              {deleteTarget === 'all-finished'
                ? 'Delete all executed, failed & expired commands for this device? Pending commands are kept. This cannot be undone.'
                : `Delete this ${getCommandLabel(commands.find(c => c.id === deleteTarget)?.command || '')} command from history? This cannot be undone.`}
            </div>
            <input
              type="password"
              value={deletePassword}
              onChange={e => setDeletePassword(e.target.value)}
              placeholder={stepUpPasswordHint()}
              autoFocus
              aria-label="Confirm deletion password"
              onKeyDown={e => {
                if (e.key === 'Enter' && !deleting) {
                  e.preventDefault();
                  confirmDelete();
                }
              }}
              className="w-full bg-mag-bg/60 border border-mag-border/40 rounded-lg px-3 py-2 text-xs font-mono text-mag-text placeholder:text-mag-text-dim/30 focus:outline-none focus:border-mag-danger/60 transition-colors"
            />
            {deleteError && <div className="text-[10px] font-mono text-red-400">{deleteError}</div>}
            <div className="text-[10px] font-mono text-mag-text-dim/50 leading-relaxed">
              This session verifies with <span className="font-bold text-mag-text-dim/70">{stepUpPasswordHint()}</span>.
            </div>
            <div className="flex gap-2">
              <button
                onClick={confirmDelete}
                disabled={deleting}
                className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg bg-mag-danger/90 hover:bg-mag-danger disabled:opacity-50 text-white text-[11px] font-bold transition-all"
              >
                <Trash2 size={12} />
                {deleting ? 'Deleting...' : 'Yes, Delete'}
              </button>
              <button
                onClick={() => { setDeleteTarget(null); setDeletePassword(''); setDeleteError(''); }}
                disabled={deleting}
                className="flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg border border-mag-border/40 text-mag-text-dim/70 hover:text-mag-text text-[11px] font-bold transition-all"
              >
                <X size={12} />
                Cancel
              </button>
            </div>
          </div>
        )}

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
                  {cmd.status === 'failed' && cmd.failure_reason && (
                    <div
                      className="mt-1 font-mono text-[9px] text-mag-danger/90 leading-snug"
                      title="Why this capture failed — fix the cause and retry."
                    >
                      {cmd.failure_reason}
                    </div>
                  )}
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

                <button
                  onClick={() => { setDeleteTarget(cmd.id); setDeleteError(''); }}
                  className="text-mag-text-dim/35 hover:text-mag-danger/80 transition-colors p-0.5"
                  title="Delete this command from history"
                  aria-label={`Delete ${getCommandLabel(cmd.command)} command`}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
