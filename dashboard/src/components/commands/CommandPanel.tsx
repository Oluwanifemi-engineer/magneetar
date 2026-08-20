'use client';

import { useState, useEffect, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { cn, getCommandLabel, isDestructiveCommand, formatTimestamp, stepUpPasswordHint } from '@/lib/utils';
import { CommandButton, type CommandTone } from '@/components/ui/CommandButton';
import { Radio, Camera, Webcam, Mic, LocateFixed, Lock, Siren, ShieldAlert, AlertTriangle, CheckCircle2, Trash2, X, MessageSquareText, Zap } from 'lucide-react';
import { CommandSkeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';
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
  { command: 'capture_audio', label: 'AUDIO', icon: Mic, tone: 'accent', title: 'Record 30s of audio' },
  { command: 'location_burst', label: 'BURST', icon: LocateFixed, tone: 'primary', title: 'Send 5 rapid location fixes' },
  { command: 'lock', label: 'LOCK', icon: Lock, tone: 'warning', title: 'Lock the device screen instantly' },
  { command: 'alarm', label: 'SIREN', icon: Siren, tone: 'warning', title: 'Play a max-volume alarm' },
  // Lost Mode (v1.5): locks the phone to a full-screen recovery message
  // ("This phone is lost — call +234...") that survives screen locks; the
  // finder can call the owner from it directly. Reversible on the device.
  { command: 'lost_mode', label: 'LOST MODE', icon: ShieldAlert, tone: 'danger', title: 'Lock the device to a full-screen recovery message with a call button' },
  { command: 'wipe', label: 'WIPE', icon: AlertTriangle, tone: 'danger', title: 'Factory reset — requires confirmation' },
];

// Vertical rollout groups: each group is a row that expands on click to
// reveal its commands (the old 2×4 tile grid crammed 9 buttons into a narrow
// column and pushed destructive + rare actions off-view). Grouped by intent
// so an operator sees the surface first, then rolls out what they need.
const COMMAND_GROUPS: {
  id: string;
  label: string;
  icon: typeof Radio;
  commands: string[];
}[] = [
  { id: 'locate', label: 'Locate', icon: LocateFixed, commands: ['ping', 'location_burst'] },
  { id: 'evidence', label: 'Evidence', icon: Camera, commands: ['capture_photo_front', 'capture_photo', 'capture_audio'] },
  { id: 'control', label: 'Control', icon: Siren, commands: ['lock', 'alarm', 'lost_mode'] },
  { id: 'danger', label: 'Danger', icon: AlertTriangle, commands: ['wipe'] },
];

const commandById = (c: string) => COMMANDS.find(x => x.command === c)!;

export function CommandPanel() {
  const { commands, setCommands, selectedDeviceId, devices } = useStore();
  const { toast } = useToast();
  const selectedDevice = devices.find(d => d.id === selectedDeviceId);
  // Milestone 2 P1 RBAC: only owner/admin may ISSUE commands or delete the
  // audit trail (server-enforced; this hides the controls for viewer/shared).
  const accessRole: 'owner' | 'admin' | 'viewer' | 'device_only' = selectedDevice?.access_role ?? 'owner';
  const canCommand = accessRole === 'owner' || accessRole === 'admin';
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
  // Vertical rollout groups — 'locate' starts open so the surface is never
  // empty; the rest expand on click. Each group stays independent so the
  // operator can keep Evidence open while firing a Control command.
  const [openGroups, setOpenGroups] = useState<Set<string>>(() => new Set(['locate']));
  const toggleGroup = (id: string) =>
    setOpenGroups(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
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
      toast('Command deleted', 'success');
      await fetchCommands();
    } catch (e: any) {
      setDeleteError(e?.message || 'Failed to delete command');
      toast(e?.message || 'Failed to delete command', 'error');
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
      toast(`${getCommandLabel(command)} command sent`, 'success');
      setTimeout(() => setLastSent(''), 3000);
      await fetchCommands();
    } catch (e: any) {
      const msg = e?.message || 'Command failed — check the server connection';
      setCommandError(msg);
      toast(msg, 'error');
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
        <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-gray-100/[0.06] border border-gray-900/25 text-gray-900 animate-fade-in">
          <MessageSquareText size={13} className="shrink-0 mt-0.5" />
          <div className="text-[10px] font-mono leading-relaxed">
            <span className="font-bold">Device offline — commands will be delivered via SMS</span>
            <span className="opacity-80"> to {selectedDevice?.sms_phone}. The phone executes them locally even
            without internet, and the ack returns when it next connects.</span>
          </div>
        </div>
      )}

      {/* Quick Actions — owner/admin only (viewer & device-only shares are
          read-only; the server rejects commands from them too) */}
      {canCommand && (
      <div>
        <div className="text-[11px] font-mono text-gray-700/70 uppercase tracking-wider font-bold mb-2.5 px-1">
          Quick Actions
        </div>
        <div className="space-y-1.5">
          {COMMAND_GROUPS.map(group => {
            const open = openGroups.has(group.id);
            const GroupIcon = group.icon;
            return (
              <div
                key={group.id}
                className="rounded-xl border border-gray-200/40 bg-gray-50/20 overflow-hidden"
              >
                <button
                  onClick={() => toggleGroup(group.id)}
                  aria-expanded={open}
                  aria-label={`${group.label} commands`}
                  className="w-full flex items-center justify-between gap-2 px-3 py-2.5 hover:bg-gray-50/40 transition-colors group"
                >
                  <span className="flex items-center gap-2">
                    <span className="w-6 h-6 rounded-lg bg-current/10 border border-current/20 flex items-center justify-center">
                      <GroupIcon size={12} className="text-gray-700/70 group-hover:text-gray-900 transition-colors" />
                    </span>
                    <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-gray-900/70 group-hover:text-gray-900 transition-colors">
                      {group.label}
                    </span>
                  </span>
                  <svg
                    width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
                    className={`text-gray-700/40 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
                  >
                    <polyline points="6 9 12 15 18 9" />
                  </svg>
                </button>
                {open && (
                  <div className="grid grid-cols-3 gap-1.5 p-2 border-t border-gray-200/30 animate-fade-in">
                    {group.commands.map(c => {
                      const { command, label, icon, tone, title } = commandById(c);
                      return (
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
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Feedback strip */}
        {commandError && (
          <div className="mt-2.5 flex items-center gap-2 px-3 py-2 rounded-lg bg-red-50/[0.06] border border-red-300/25 text-red-600 text-[10px] font-mono font-bold animate-fade-in">
            <AlertTriangle size={11} className="shrink-0" />
            {commandError}
          </div>
        )}
        {!commandError && lastSent && (
          <div className="mt-2.5 flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-100/[0.06] border border-gray-900/25 text-gray-900 text-[10px] font-mono font-bold animate-fade-in">
            <CheckCircle2 size={11} className="shrink-0" />
            {getCommandLabel(lastSent)} command sent —{' '}
            {smsRelayActive
              ? 'the phone will execute it from the SMS (no internet needed).'
              : 'the device will pick it up on its next poll.'}
          </div>
        )}

        {/* Wipe confirmation */}
        {confirmWipe && (
          <div className="mt-3 rounded-xl border border-red-300/35 bg-red-50/[0.05] p-3.5 space-y-2.5 animate-fade-in">
            <div className="flex items-start gap-2">
              <AlertTriangle size={14} className="text-red-600 shrink-0 mt-0.5" />
              <div>
                <div className="text-[10px] font-mono text-red-600 font-bold uppercase tracking-wider">
                  Permanent wipe
                </div>
                <div className="text-[10px] font-mono text-gray-700/70 mt-1 leading-relaxed">
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
              className="w-full bg-white/60 border border-red-300/40 rounded-lg px-3 py-2 text-xs font-mono text-gray-900 placeholder:text-gray-700/30 focus:outline-none focus:border-red-300/70 transition-colors"
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
                className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-red-50/90 hover:bg-red-50 disabled:opacity-50 text-white text-[10px] font-mono font-bold uppercase tracking-wider transition-all"
              >
                {sending === 'wipe' ? 'SENDING...' : 'Confirm wipe'}
              </button>
              <button
                onClick={() => { setConfirmWipe(false); setWipePassword(''); setWipeError(''); }}
                disabled={sending === 'wipe'}
                className="px-3 py-2 rounded-lg border border-gray-200/40 text-gray-700/70 hover:text-gray-900 text-[10px] font-mono font-bold transition-all"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
      )}

      {/* Command History */}
      <div>
        <div className="flex items-center justify-between mb-2.5 px-1">
          <div className="text-[11px] font-mono text-gray-700/70 uppercase tracking-wider font-bold">
            Recent Commands
          </div>
          {canCommand && commands.filter(c => c.status !== 'pending').length > 0 && deleteTarget !== 'all-finished' && (
            <button
              onClick={() => { setDeleteTarget('all-finished'); setDeleteError(''); }}
              className="flex items-center gap-1 text-[10px] font-mono font-bold uppercase tracking-wider text-gray-700/60 hover:text-red-600/80 transition-colors"
              title="Remove ALL executed, failed & expired entries (keeps pending commands)"
            >
              <Trash2 size={11} />
              Clear all finished
            </button>
          )}
        </div>

        {/* Step-up confirm card (password required) */}
        {deleteTarget !== null && (
          <div className="mb-2.5 rounded-xl border border-red-300/30 bg-red-50/[0.05] p-3.5 space-y-2.5 animate-fade-in">
            <div className="text-[10px] font-mono text-red-600/90 leading-relaxed">
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
              className="w-full bg-white/60 border border-gray-200/40 rounded-lg px-3 py-2 text-xs font-mono text-gray-900 placeholder:text-gray-700/30 focus:outline-none focus:border-red-300/60 transition-colors"
            />
            {deleteError && <div className="text-[10px] font-mono text-red-400">{deleteError}</div>}
            <div className="text-[10px] font-mono text-gray-700/50 leading-relaxed">
              This session verifies with <span className="font-bold text-gray-700/70">{stepUpPasswordHint()}</span>.
            </div>
            <div className="flex gap-2">
              <button
                onClick={confirmDelete}
                disabled={deleting}
                className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg bg-red-50/90 hover:bg-red-50 disabled:opacity-50 text-white text-[11px] font-bold transition-all"
              >
                <Trash2 size={12} />
                {deleting ? 'Deleting...' : 'Yes, Delete'}
              </button>
              <button
                onClick={() => { setDeleteTarget(null); setDeletePassword(''); setDeleteError(''); }}
                disabled={deleting}
                className="flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg border border-gray-200/40 text-gray-700/70 hover:text-gray-900 text-[11px] font-bold transition-all"
              >
                <X size={12} />
                Cancel
              </button>
            </div>
          </div>
        )}

        <div className="space-y-1.5 max-h-48 overflow-y-auto">
          {commands.length === 0 ? (
            <div className="text-center py-8">
              <div className="w-12 h-12 rounded-2xl bg-gray-50/40 border border-gray-200/30 flex items-center justify-center mx-auto mb-3">
                <Zap size={18} className="text-gray-700/20" />
              </div>
              <div className="text-gray-700/50 text-xs font-bold mb-1">No commands sent yet</div>
              <div className="text-gray-700/30 text-[10px] font-mono leading-relaxed max-w-[200px] mx-auto">
                Use the buttons above to ping, capture, lock, or alarm your device. Commands are delivered the next time the device checks in.
              </div>
            </div>
          ) : (
            commands.slice(0, 10).map((cmd) => (
              <div
                key={cmd.id}
                className="flex items-center gap-3 py-2 px-2 rounded-lg bg-gray-50/20 border border-gray-200/20"
              >
                <div className={cn(
                  'w-2 h-2 rounded-full',
                  cmd.status === 'expired' ? 'bg-mag-text-dim/30' :
                  cmd.status === 'executed' ? 'bg-gray-100' :
                  cmd.status === 'failed' ? 'bg-red-50' :
                  'bg-amber-50 animate-pulse-slow'
                )} />
                <div className="flex-1 min-w-0">
                  <div className="font-mono text-[11px] text-gray-900 font-bold">
                    {getCommandLabel(cmd.command)}
                  </div>
                  <div className="font-mono text-[10px] text-gray-700/50">
                    {formatTimestamp(cmd.issued_at)}
                  </div>
                  {cmd.status === 'failed' && (
                    <div
                      className="mt-1 font-mono text-[9px] text-red-600/90 leading-snug"
                      title="Why this command failed — fix the cause and retry."
                    >
                      {cmd.failure_reason || (
                        // Helpful fallback reasons based on command type
                        cmd.command === 'lock' ? 'Device Admin may not be active — enable in phone Settings > Security'
                        : cmd.command === 'alarm' ? 'Device may be in Silent mode'
                        : cmd.command === 'wipe' ? 'Device Admin required for factory reset'
                        : cmd.command === 'capture_photo' || cmd.command === 'capture_photo_front' ? 'Camera may not be available — re-arm the capture service'
                        : cmd.command === 'capture_audio' ? 'Microphone may not be available — check permission settings'
                        : 'Command could not be executed on the device'
                      )}
                    </div>
                  )}
                </div>
                <span className={cn(
                  'text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded-md',
                  cmd.status === 'expired' ? 'text-gray-700/45 bg-mag-text-dim/5 line-through decoration-mag-text-dim/30' :
                  cmd.status === 'executed' ? 'text-gray-900 bg-gray-100/10' :
                  cmd.status === 'failed' ? 'text-red-600 bg-red-50/10' :
                  'text-amber-600 bg-amber-50/10'
                )}>
                  {cmd.status}
                </span>

                {canCommand && (
                  <button
                    onClick={() => { setDeleteTarget(cmd.id); setDeleteError(''); }}
                    className="text-gray-700/35 hover:text-red-600/80 transition-colors p-0.5"
                    title="Delete this command from history"
                    aria-label={`Delete ${getCommandLabel(cmd.command)} command`}
                  >
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
