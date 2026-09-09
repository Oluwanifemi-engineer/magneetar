'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { cn, formatTimestamp, locationTimestamp, stepUpPasswordHint } from '@/lib/utils';
import { Camera, Music, Play, Pause, X, ChevronLeft, Trash2, ShieldCheck, Lock, ImageOff } from 'lucide-react';
import { MagButton, MagInput } from '@/components/ui/MagPrimitives';
import { MediaSkeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';

export function MediaGallery() {
  const { media, setMedia, selectedDeviceId, devices } = useStore();
  const { toast } = useToast();
  const selectedDevice = devices.find(d => d.id === selectedDeviceId);
  const accessRole: 'owner' | 'admin' | 'viewer' | 'device_only' = selectedDevice?.access_role ?? 'owner';
  const canManage = accessRole === 'owner' || accessRole === 'admin';
  const [selectedItem, setSelectedItem] = useState<any>(null);
  const [itemData, setItemData] = useState<any>(null);
  const [playing, setPlaying] = useState(false);
  const [playError, setPlayError] = useState('');
  const audioRef = useRef<HTMLAudioElement>(null);

  const [manageMode, setManageMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePassword, setDeletePassword] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const [deleted, setDeleted] = useState('');

  const fetchMedia = useCallback(async () => {
    if (!selectedDeviceId) return;
    try { const api = getAPI(); const res = await api.getMedia(selectedDeviceId); setMedia(res.media); }
    catch (e) { console.error('Failed to fetch media:', e); }
  }, [selectedDeviceId, setMedia]);

  useEffect(() => { fetchMedia(); }, [fetchMedia]);

  const handleSelect = async (item: any) => {
    setSelectedItem(item);
    try { const api = getAPI(); const data = await api.getMediaFile(item.id); setItemData(data); }
    catch (e) { console.error('Failed to load media:', e); }
  };

  const handleClose = () => { setSelectedItem(null); setItemData(null); setPlaying(false); setPlayError(''); };

  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) { audio.pause(); setPlaying(false); }
    else {
      setPlayError('');
      audio.play().then(() => setPlaying(true)).catch((e) => {
        console.error('Audio playback failed:', e);
        setPlaying(false); setPlayError('Playback failed — try downloading the file.');
      });
    }
  }, [playing]);

  const toggleManage = () => { setManageMode(!manageMode); setSelectedIds(new Set()); setSelectedItem(null); };
  const toggleSelected = (id: number) => {
    setSelectedIds((prev) => { const next = new Set(prev); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  };

  const deleteMediaItem = useCallback(async (id: number, password: string) => {
    await getAPI().deleteMedia(id, password);
  }, []);

  const handleDelete = async () => {
    if (deleting) return;
    const ids = [...selectedIds];
    if (ids.length === 0) return;
    setDeleting(true); setDeleteError('');
    const failed: string[] = [];
    for (const id of ids) {
      try { await deleteMediaItem(id, deletePassword); } catch (e: any) { failed.push(String(id)); }
    }
    setDeletePassword(''); setDeleteOpen(false); setSelectedIds(new Set());
    if (failed.length === 0) {
      const msg = ids.length > 1 ? `${ids.length} items deleted` : 'Media deleted';
      setDeleted(msg); toast(msg, 'success');
    } else {
      const msg = `${ids.length - failed.length}/${ids.length} deleted · ${failed.length} failed`;
      setDeleted(msg); toast(msg, 'warning');
    }
    setTimeout(() => setDeleted(''), 4000);
    await fetchMedia(); setDeleting(false);
  };

  const viewerTimestamp = locationTimestamp(selectedItem);

  if (selectedDeviceId && media.length === 0 && !selectedItem) {
    return <div className="p-4"><MediaSkeleton /></div>;
  }

  return (
    <div className="p-4 space-y-4">
      {selectedItem && !manageMode ? (
        <div>
          <div className="mag-panel-header flex items-center gap-2">
            <button onClick={handleClose} className="text-mag-text-muted hover:text-mag-text transition-colors">
              <ChevronLeft size={18} />
            </button>
            <span className="flex-1 truncate mag-panel-label">
              {selectedItem.type === 'photo' ? 'PHOTO' : 'AUDIO'} — {formatTimestamp(viewerTimestamp)}
            </span>
            {canManage && (
              <MagButton variant="danger" size="sm" onClick={() => { setDeletePassword(''); setDeleteError(''); setDeleteOpen(true); }}>
                <Trash2 size={11} />
                DELETE
              </MagButton>
            )}
          </div>

          <div className="mag-panel-elevated overflow-hidden">
            {itemData?.type === 'photo' && itemData?.data_b64 && (
              <img src={`data:image/jpeg;base64,${itemData.data_b64}`} alt="Captured photo" className="w-full h-auto" />
            )}
            {itemData?.type === 'audio' && itemData?.data_b64 && (
              <div className="p-6 text-center">
                <div className="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4 mag-stat-tile">
                  <Music size={24} className="text-mag-text-dim" />
                </div>
                <MagButton variant="subtle" onClick={togglePlay} icon={playing ? <Pause size={14} /> : <Play size={14} />}>
                  {playing ? 'PAUSE' : 'PLAY'}
                </MagButton>
                <audio ref={audioRef} src={`data:audio/mp4;base64,${itemData.data_b64}`} preload="auto"
                  onEnded={() => setPlaying(false)}
                  onError={() => { setPlaying(false); setPlayError('Playback failed — the audio file may be unsupported.'); }} />
                {playError && (
                  <div className="mt-3 text-[10px] font-mono text-red-400 animate-fade-in">{playError}</div>
                )}
                <a href={`data:audio/mp4;base64,${itemData.data_b64}`} download={`evidence_${selectedItem.id}.m4a`}
                  className="mt-3 inline-flex items-center gap-1.5 text-[10px] font-mono font-bold text-mag-text-muted hover:text-mag-text transition-colors">
                  <ChevronLeft size={11} className="rotate-90" />
                  DOWNLOAD FILE
                </a>
              </div>
            )}
            {!itemData && (
              <div className="p-8 text-center">
                <div className="text-mag-text-muted text-xs font-mono">Loading...</div>
              </div>
            )}
          </div>

          <div className="mt-3 space-y-1.5">
            {selectedItem.lat && selectedItem.lng && (
              <div className="flex justify-between text-[10px] font-mono">
                <span className="text-mag-text-muted font-bold">Location</span>
                <span className="text-mag-text font-bold">{selectedItem.lat.toFixed(6)}, {selectedItem.lng.toFixed(6)}</span>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div>
          <div className="mag-panel-header">
            <Camera size={12} className="text-mag-text-muted" />
            <span className="mag-panel-label">Captured Media</span>
            {manageMode && (
              <span className="ml-auto flex items-center gap-1 text-mag-text-muted">
                <Lock size={9} />
                delete requires password
              </span>
            )}
            {canManage && !manageMode && (
              <MagButton variant="ghost" size="sm" onClick={toggleManage} icon={<Trash2 size={9} />}>
                MANAGE
              </MagButton>
            )}
          </div>

          {deleted && (
            <div className="mb-2.5 flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/15 text-emerald-400 text-[10px] font-mono font-bold animate-fade-in">
              <ShieldCheck size={11} />
              {deleted}
            </div>
          )}

          {media.length === 0 ? (
            <div className="mag-empty">
              <div className="mag-empty-icon">
                <ImageOff size={22} className="text-mag-text-muted" />
              </div>
              <div className="mag-empty-head">No media captured</div>
              <div className="mag-empty-sub">
                Use the <span className="text-mag-text font-bold">Commands</span> tab to capture photos and audio remotely.
              </div>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-2">
                {media.map((item) => {
                  const checked = selectedIds.has(item.id);
                  return (
                    <button key={item.id}
                      onClick={() => (manageMode ? toggleSelected(item.id) : handleSelect(item))}
                      className={cn(
                        'text-left rounded-xl transition-all duration-200 p-3 relative',
                        manageMode && checked ? 'mag-row border-emerald-500/40 bg-emerald-500/6' : 'mag-row'
                      )}>
                      {manageMode && (
                        <span className={cn(
                          'absolute top-2 right-2 w-4 h-4 rounded border flex items-center justify-center text-[9px] font-bold transition-all',
                          checked ? 'bg-emerald-500 border-emerald-500 text-white' : 'border-mag-border text-transparent'
                        )}>✓</span>
                      )}
                      <div className="flex items-center justify-center h-16 mb-2 rounded-lg bg-mag-surface/40 border border-mag-border/50">
                        {item.type === 'photo' ? (
                          <Camera size={20} className="text-mag-text-muted/40" />
                        ) : (
                          <Music size={20} className="text-mag-text-muted/40" />
                        )}
                      </div>
                      <div className="font-mono text-[11px] text-mag-text-dim font-bold flex items-center gap-1.5">
                        <span>{item.type === 'photo' ? '📷' : '🎤'}</span>
                        {item.type.toUpperCase()}
                      </div>
                      <div className="font-mono text-[10px] text-mag-text-muted mt-0.5 font-bold">
                        {formatTimestamp(locationTimestamp(item))}
                      </div>
                    </button>
                  );
                })}
              </div>

              {manageMode && (
                <div className="mt-3 flex items-center gap-2 flex-wrap">
                  <MagButton variant="ghost" size="sm" onClick={() => setSelectedIds(new Set(media.map((m) => m.id)))}>
                    Select all
                  </MagButton>
                  <MagButton variant="ghost" size="sm" onClick={() => setSelectedIds(new Set())}>
                    Clear
                  </MagButton>
                  <MagButton
                    variant="danger"
                    size="sm"
                    disabled={selectedIds.size === 0}
                    onClick={() => { setDeletePassword(''); setDeleteError(''); setDeleteOpen(true); }}
                  >
                    <Trash2 size={11} />
                    Delete ({selectedIds.size})
                  </MagButton>
                  <MagButton variant="ghost" size="sm" onClick={toggleManage} icon={<X size={11} />}>
                    Exit
                  </MagButton>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {deleteOpen && createPortal(
        <div className="fixed inset-0 z-[2100] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Confirm deletion">
          <div className="absolute inset-0 bg-mag-bg/80 backdrop-blur-sm" onClick={() => !deleting && setDeleteOpen(false)} />
          <div className="relative mag-panel-elevated w-full max-w-sm p-5 space-y-4 animate-fade-in">
            <div className="flex items-start gap-2.5">
              <div className="w-8 h-8 rounded-lg bg-red-500/10 border border-red-500/20 flex items-center justify-center shrink-0">
                <Trash2 size={14} className="text-red-400" />
              </div>
              <div className="min-w-0">
                <div className="text-sm font-bold text-mag-text tracking-wide">DELETE MEDIA</div>
                <div className="text-[9px] font-mono text-mag-text-muted uppercase tracking-[0.15em] font-bold mt-0.5">
                  {selectedIds.size > 0 ? `${selectedIds.size} item(s)` : '1 item'} · irreversible
                </div>
              </div>
              <button onClick={() => !deleting && setDeleteOpen(false)} className="ml-auto w-7 h-7 rounded-lg flex items-center justify-center hover:bg-mag-surface-raised transition-all">
                <X size={13} className="text-mag-text-muted hover:text-mag-text" />
              </button>
            </div>

            <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-amber-500/5 border border-amber-500/12">
              <Lock size={12} className="text-amber-400 shrink-0 mt-0.5" />
              <div className="text-[10px] font-mono text-mag-text-dim leading-relaxed">
                Deletions require a step-up password: <span className="font-bold text-mag-text">{stepUpPasswordHint()}</span>.
              </div>
            </div>

            <MagInput
              label="Password"
              type="password"
              value={deletePassword}
              onChange={(e) => setDeletePassword(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleDelete()}
              autoFocus
              aria-label="Password"
              placeholder="Enter password"
            />

            {deleteError && <div className="text-[10px] font-mono text-red-400 animate-fade-in">{deleteError}</div>}

            <div className="flex gap-2">
              <MagButton
                variant="danger"
                fullWidth
                loading={deleting}
                disabled={!deletePassword}
                icon={<Trash2 size={11} />}
                onClick={handleDelete}
              >
                {deleting ? 'Deleting...' : 'Confirm delete'}
              </MagButton>
              <MagButton
                variant="ghost"
                fullWidth
                disabled={deleting}
                onClick={() => setDeleteOpen(false)}
              >
                Cancel
              </MagButton>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
