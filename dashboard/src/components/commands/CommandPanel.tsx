'use client';

import { useState, useEffect, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { cn, getCommandLabel, isDestructiveCommand, formatTimestamp, stepUpPasswordHint } from '@/lib/utils';
import { MagInput, MagButton } from '@/components/ui/MagPrimitives';
import { CommandButton, type CommandTone } from '@/components/ui/CommandButton';
import { Radio, Camera, Webcam, Mic, LocateFixed, Lock, Siren, ShieldAlert, AlertTriangle, CheckCircle2, Trash2, X, MessageSquareText, Zap, ChevronDown } from 'lucide-react';
import { useToast } from '@/components/ui/Toast';
import type { CommandType } from '@/types';

const COMMANDS: {
  command: CommandType;
  label: string;
  icon: typeof Radio;
  tone: CommandTone;
  title: string;
}[] = [
  { command: 'ping', label: 'PING', icon: Radio, tone: 'primary', title: 'Check the device is reachable' },
  { command: 'capture_photo_front', label: 'FRONT', icon: Webcam, tone: 'accent', title: 'Capture front camera photo' },
  { command: 'capture_photo', label: 'PHOTO', icon: Camera, tone: 'accent', title: 'Capture rear camera photo' },
  { command: 'capture_audio', label: 'AUDIO', icon: Mic, tone: 'accent', title: 'Record 30s of audio' },
  { command: 'location_burst', label: 'BURST', icon: LocateFixed, tone: 'primary', title: 'Send 5 rapid location fixes' },
  { command: 'lock', label: 'LOCK', icon: Lock, tone: 'warning', title: 'Lock the device screen instantly' },
  { command: 'alarm', label: 'SIREN', icon: Siren, tone: 'warning', title: 'Play a max-volume alarm' },
  { command: 'lost_mode', label: 'LOST MODE', icon: ShieldAlert, tone: 'danger', title: 'Lock to full-screen recovery message' },
  { command: 'wipe', label: 'WIPE', icon: AlertTriangle, tone: 'danger', title: 'Factory reset — requires confirmation' },
];

const COMMAND_GROUPS: {
  id: string;
  label: string;
  icon: typeof Radio;
  commands: string[];
  color: string;
  gradient: string;
}[] = [
  { id: 'locate', label: 'Locate', icon: LocateFixed, commands: ['ping', 'location_burst'], color: 'emerald', gradient: 'from-emerald-500/10 to-emerald-500/[0.02]' },
  { id: 'evidence', label: 'Evidence', icon: Camera, commands: ['capture_photo_front', 'capture_photo', 'capture_audio'], color: 'blue', gradient: 'from-blue-500/10 to-blue-500/[0.02]' },
  { id: 'control', label: 'Control', icon: Siren, commands: ['lock', 'alarm', 'lost_mode'], color: 'amber', gradient: 'from-amber-500/10 to-amber-500/[0.02]' },
  { id: 'danger', label: 'Danger', icon: AlertTriangle, commands: ['wipe'], color: 'red', gradient: 'from-red-500/10 to-red-500/[0.02]' },
];

const commandById = (c: string) => COMMANDS.find(x => x.command === c)!;

export function CommandPanel() {
  const { commands, setCommands, selectedDeviceId, devices } = useStore();
  const { toast } = useToast();
  const selectedDevice = devices.find(d => d.id === selectedDeviceId);
  const accessRole: 'owner' | 'admin' | 'viewer' | 'device_only' = selectedDevice?.access_role ?? 'owner';
  const canCommand = accessRole === 'owner' || accessRole === 'admin';
  const smsRelayActive = !!selectedDevice &&
    !selectedDevice.is_online &&
    selectedDevice.sms_commands_enabled &&
    !!selectedDevice.sms_phone;
  const [sending, setSending] = useState<string | null>(null);
  const [confirmWipe, setConfirmWipe] = useState(false);
  const [commandError, setCommandError] = useState('');
  const [lastSent, setLastSent] = useState('');
  const [openGroups, setOpenGroups] = useState<Set<string>>(() => new Set(['locate']));
  const toggleGroup = (id: string) =>
    setOpenGroups(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  const [wipePassword, setWipePassword] = useState('');
  const [wipeError, setWipeError] = useState('');
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

  useEffect(() => {
    setDeleteTarget(null);
    setDeletePassword('');
    setDeleteError('');
    setDeleting(false);
  }, [selectedDeviceId]);

  const handleSend = async (command: string, params = '', password?: string) => {
    if (!selectedDeviceId) return;
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
    if (command === 'wipe') {
      setConfirmWipe(true);
      return;
    }
    handleSend(command);
  };

  return (
    <div className="p-3 space-y-3">
      {/* Offline SMS relay notice */}
      {smsRelayActive && (
        <div className="flex items-start gap-2.5 px-3 py-3 rounded-xl bg-blue-500/[0.08] border border-blue-500/15 text-blue-400/80 animate-fade-in">
          <MessageSquareText size={14} className="shrink-0 mt-0.5" />
          <div className="text-[10px] font-mono leading-relaxed">
            <span className="font-bold">Offline — SMS mode</span>
            <span className="opacity-70"> Commands sent to {selectedDevice?.sms_phone}</span>
          </div>
        </div>
      )}

      {/* Quick Actions — owner/admin only */}
      {canCommand && (
      <div>
        <div className="text-[11px] font-mono text-white/30 uppercase tracking-wider font-bold mb-2.5 px-1">
          Quick Actions
        </div>
        <div className="space-y-2">
          {COMMAND_GROUPS.map(group => {
            const open = openGroups.has(group.id);
            const GroupIcon = group.icon;
            const borderColor: Record<string, string> = {
              emerald: 'border-l-emerald-500/50',
              blue: 'border-l-blue-500/50',
              amber: 'border-l-amber-500/50',
              red: 'border-l-red-500/50',
            };
            const iconBg: Record<string, string> = {
              emerald: 'bg-emerald-500/10 text-emerald-400',
              blue: 'bg-blue-500/10 text-blue-400',
              amber: 'bg-amber-500/10 text-amber-400',
              red: 'bg-red-500/10 text-red-400',
            };
            return (
              <div
                key={group.id}
                className={cn(
                  'rounded-xl border-l-[3px] overflow-hidden transition-all duration-200',
                  borderColor[group.color],
                  open
                    ? 'bg-mag-surface-raised border-mag-border border-l-[3px]'
                    : 'bg-mag-surface border-transparent border-l-[3px] hover:bg-mag-surface-raised'
                )}
              >
                <button
                  onClick={() => toggleGroup(group.id)}
                  aria-expanded={open}
                  aria-label={`${group.label} commands`}
                  className="w-full flex items-center justify-between gap-3 px-3.5 py-3 hover:bg-mag-surface-raised transition-colors"
                >
                  <span className="flex items-center gap-3">
                    <span className={cn(
                      'w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200',
                      open ? iconBg[group.color] : 'bg-mag-surface-raised text-mag-text-dim'
                    )}>
                      <GroupIcon size={16} />
                    </span>
                    <div className="text-left">
                      <span className="text-[12px] font-mono font-bold uppercase tracking-wider text-mag-text-dim block">
                        {group.label}
                      </span>
                      <span className="text-[9px] font-mono text-mag-text-muted block mt-0.5">
                        {group.commands.length} command{group.commands.length !== 1 ? 's' : ''}
                      </span>
                    </div>
                  </span>
                  <ChevronDown
                    size={14}
                    className={cn(
                      'text-mag-text-muted transition-transform duration-200',
                      open && 'rotate-180 text-mag-text-dim'
                    )}
                  />
                </button>
                {open && (
                  <div className="grid grid-cols-2 gap-2 p-2.5 border-t border-mag-border bg-gradient-to-b from-white/5 to-transparent animate-fade-in">
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
          <div className="mt-3 flex items-center gap-2 px-3 py-2.5 rounded-xl bg-red-500/[0.08] border border-red-500/15 text-red-400/80 text-[10px] font-mono font-bold animate-fade-in">
            <AlertTriangle size={12} className="shrink-0" />
            {commandError}
          </div>
        )}
        {!commandError && lastSent && (
          <div className="mt-3 flex items-center gap-2 px-3 py-2.5 rounded-xl bg-emerald-500/[0.08] border border-emerald-500/15 text-emerald-400/80 text-[10px] font-mono font-bold animate-fade-in">
            <CheckCircle2 size={12} className="shrink-0" />
            {getCommandLabel(lastSent)} command sent
          </div>
        )}

        {/* Wipe confirmation */}
        {confirmWipe && (
          <div className="mt-3 rounded-xl border border-red-500/15 bg-red-500/[0.04] p-4 space-y-3 animate-fade-in">
            <div className="flex items-start gap-2">
              <AlertTriangle size={15} className="text-red-400/70 shrink-0 mt-0.5" />
              <div>
                <div className="text-[11px] font-mono text-red-400/80 font-bold uppercase tracking-wider">
                  Permanent Wipe
                </div>
                <div className="text-[10px] font-mono text-white/35 mt-1 leading-relaxed">
                  This erases ALL data. Cannot be undone.
                </div>
              </div>
            </div>
            <MagInput
              variant="danger"
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
                className="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white text-[10px] font-mono font-bold uppercase tracking-wider transition-all shadow-lg shadow-red-600/20"
              >
                {sending === 'wipe' ? 'SENDING...' : 'Confirm Wipe'}
              </button>
              <MagButton
                variant="ghost"
                size="sm"
                onClick={() => { setConfirmWipe(false); setWipePassword(''); setWipeError(''); }}
                disabled={sending === 'wipe'}
              >
                Cancel
              </MagButton>
            </div>
          </div>
        )}
      </div>
      )}

      {/* Command History */}
      <div>
        <div className="flex items-center justify-between mb-2 px-1">
          <div className="text-[11px] font-mono text-white/30 uppercase tracking-wider font-bold">
            Recent Commands
          </div>
          {canCommand && commands.filter(c => c.status !== 'pending').length > 0 && deleteTarget !== 'all-finished' && (
            <button
              onClick={() => { setDeleteTarget('all-finished'); setDeleteError(''); }}
              className="flex items-center gap-1 text-[9px] font-mono font-bold uppercase tracking-wider text-white/25 hover:text-red-400/70 transition-colors"
              title="Remove ALL finished commands"
            >
              <Trash2 size={10} />
              Clear all
            </button>
          )}
        </div>

        {/* Step-up confirm card */}
        {deleteTarget !== null && (
          <div className="mb-3 rounded-xl border border-red-500/15 bg-red-500/[0.04] p-3.5 space-y-2.5 animate-fade-in">
            <div className="text-[10px] font-mono text-red-400/70 leading-relaxed">
              {deleteTarget === 'all-finished'
                ? 'Delete all finished commands? Pending kept. Cannot be undone.'
                : `Delete this ${getCommandLabel(commands.find(c => c.id === deleteTarget)?.command || '')} command? Cannot be undone.`}
            </div>
            <MagInput
              variant="danger"
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
            />
            {deleteError && <div className="text-[10px] font-mono text-red-400">{deleteError}</div>}
            <div className="flex gap-2">
              <button
                onClick={confirmDelete}
                disabled={deleting}
                className="flex-1 flex items-center justify-center gap-2 py-2 rounded-xl bg-red-600 hover:bg-red-500 disabled:opacity-50 text-white text-[10px] font-bold transition-all shadow-lg shadow-red-600/20"
              >
                <Trash2 size={11} />
                {deleting ? 'Deleting...' : 'Delete'}
              </button>
              <MagButton
                variant="ghost"
                size="sm"
                onClick={() => { setDeleteTarget(null); setDeletePassword(''); setDeleteError(''); }}
                disabled={deleting}
              >
                <X size={11} />
                Cancel
              </MagButton>
            </div>
          </div>
        )}

        {/* Table-first command history — Stripe/Linear pattern */}
        <div className="max-h-64 overflow-y-auto">
          {commands.length === 0 ? (
            <div className="text-center py-10">
              <div className="w-12 h-12 rounded-2xl bg-mag-surface-raised flex items-center justify-center mx-auto mb-3">
                <Zap size={18} className="text-mag-text-muted" />
              </div>
              <div className="text-mag-text-dim text-[11px] font-bold mb-1">No commands yet</div>
              <div className="text-mag-text-muted text-[9px] font-mono leading-relaxed max-w-[180px] mx-auto">
                Use the buttons above to send your first command.
              </div>
            </div>
          ) : (
            <>
              {/* Table header */}
              <div className="flex items-center gap-3 px-3 py-2 border-b border-mag-border">
                <div className="w-2 shrink-0" />
                <span className="flex-1 text-[8px] font-mono text-mag-text-muted uppercase tracking-wider font-bold">Command</span>
                <span className="w-20 text-right text-[8px] font-mono text-mag-text-muted uppercase tracking-wider font-bold">Time</span>
                <span className="w-16 text-right text-[8px] font-mono text-mag-text-muted uppercase tracking-wider font-bold">Status</span>
                {canCommand && <div className="w-6" />}
              </div>

              {/* Exception-first: failed > pending > executed > expired */}
              {[...commands]
                .sort((a, b) => {
                  const order: Record<string, number> = { failed: 0, pending: 1, executed: 2, expired: 3 };
                  return (order[a.status] ?? 4) - (order[b.status] ?? 4);
                })
                .slice(0, 12)
                .map((cmd) => (
                <div
                  key={cmd.id}
                  className={cn(
                    'flex items-center gap-3 px-3 py-2.5 border-b border-mag-border transition-colors group',
                    'hover:bg-mag-surface-raised',
                    cmd.status === 'failed' && 'bg-red-500/[0.04]',
                    cmd.status === 'pending' && 'bg-amber-500/[0.03]',
                  )}
                >
                  {/* Status dot — color = state only */}
                  <div className={cn(
                    'w-1.5 h-1.5 rounded-full shrink-0',
                    cmd.status === 'executed' ? 'bg-emerald-500' :
                    cmd.status === 'failed' ? 'bg-red-500' :
                    cmd.status === 'pending' ? 'bg-amber-500 animate-pulse' :
                    'bg-mag-surface-raised'
                  )} />

                  {/* Command name — tabular numeral */}
                  <span className="flex-1 font-mono text-[11px] text-mag-text-dim font-bold truncate">
                    {getCommandLabel(cmd.command)}
                  </span>

                  {/* Timestamp — right-aligned tabular */}
                  <span className="w-20 text-right font-mono text-[9px] text-mag-text-muted tabular-nums shrink-0">
                    {formatTimestamp(cmd.issued_at).split(' ')[1] || formatTimestamp(cmd.issued_at)}
                  </span>

                  {/* Status chip — color = state only */}
                  <span className={cn(
                    'w-16 text-right text-[8px] font-mono font-bold uppercase shrink-0',
                    cmd.status === 'executed' ? 'text-emerald-400/60' :
                    cmd.status === 'failed' ? 'text-red-400/70' :
                    cmd.status === 'pending' ? 'text-amber-400/60' :
                    'text-mag-text-muted line-through'
                  )}>
                    {cmd.status}
                  </span>

                  {/* Delete — on hover only */}
                  {canCommand && (
                    <button
                      onClick={() => { setDeleteTarget(cmd.id); setDeleteError(''); }}
                      className="w-6 text-right opacity-0 group-hover:opacity-100 transition-opacity"
                      title="Delete"
                    >
                      <Trash2 size={10} className="text-mag-text-muted hover:text-red-400/60 transition-colors" />
                    </button>
                  )}
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
