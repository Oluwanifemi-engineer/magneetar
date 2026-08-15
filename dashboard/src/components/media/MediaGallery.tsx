'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { cn, formatTimestamp, locationTimestamp, stepUpPasswordHint } from '@/lib/utils';
import { Camera, Music, Play, Pause, X, ChevronLeft, Trash2, ShieldCheck, Lock, ImageOff } from 'lucide-react';
import { MediaSkeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';

/**
 * Media management — viewing plus deletion of captured evidence.
 *
 * Deletion is deliberately gated by a STEP-UP PASSWORD (account password in
 * user mode, master API key in admin mode): a stolen dashboard session alone
 * is never enough to destroy evidence. The password is sent to the server for
 * verification on every delete and is never stored client-side.
 */
export function MediaGallery() {
  const { media, setMedia, selectedDeviceId, devices } = useStore();
  const { toast } = useToast();
  // Milestone 2 P1 RBAC: deleting evidence is owner/admin only (server-verified
  // step-up password too) — viewer/device_only shares are read-only here.
  const selectedDevice = devices.find(d => d.id === selectedDeviceId);
  const accessRole: 'owner' | 'admin' | 'viewer' | 'device_only' = selectedDevice?.access_role ?? 'owner';
  const canManage = accessRole === 'owner' || accessRole === 'admin';
  const [selectedItem, setSelectedItem] = useState<any>(null);
  const [itemData, setItemData] = useState<any>(null);
  const [playing, setPlaying] = useState(false);
  const [playError, setPlayError] = useState('');
  const audioRef = useRef<HTMLAudioElement>(null);

  // Manage / delete state
  const [manageMode, setManageMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deletePassword, setDeletePassword] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const [deleted, setDeleted] = useState('');

  const fetchMedia = useCallback(async () => {
    if (!selectedDeviceId) return;
    try {
      const api = getAPI();
      const res = await api.getMedia(selectedDeviceId);
      setMedia(res.media);
    } catch (e) {
      console.error('Failed to fetch media:', e);
    }
  }, [selectedDeviceId, setMedia]);

  useEffect(() => {
    fetchMedia();
  }, [fetchMedia]);

  const handleSelect = async (item: any) => {
    setSelectedItem(item);
    try {
      const api = getAPI();
      const data = await api.getMediaFile(item.id);
      setItemData(data);
    } catch (e) {
      console.error('Failed to load media:', e);
    }
  };

  const handleClose = () => {
    setSelectedItem(null);
    setItemData(null);
    setPlaying(false);
    setPlayError('');
  };

  /**
   * Playback is driven EXPLICITLY from the click handler (a real user
   * gesture) rather than a React-toggled autoPlay prop. autoPlay is only
   * honored at element load time — toggling it after mount does nothing on
   * most browsers, and Chrome's autoplay-with-sound policy can reject it
   * without a direct gesture. The play()/pause() promise also lets us
   * surface real failures (unsupported codec, blocked playback) instead of
   * a PLAY button that toggles but stays silent.
   */
  const togglePlay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) {
      audio.pause();
      setPlaying(false);
    } else {
      setPlayError('');
      audio.play().then(() => setPlaying(true)).catch((e) => {
        // Autoplay-policy rejection or codec/decode failure — tell the user
        // instead of leaving a silent, spinning player.
        console.error('Audio playback failed:', e);
        setPlaying(false);
        setPlayError('Playback failed — try downloading the file.');
      });
    }
  }, [playing]);

  const toggleManage = () => {
    setManageMode(!manageMode);
    setSelectedIds(new Set());
    setSelectedItem(null);
  };

  const toggleSelected = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // Delete one item with the (server-verified) step-up password.
  const deleteMediaItem = useCallback(async (id: number, password: string) => {
    await getAPI().deleteMedia(id, password);
  }, []);

  // Sequential deletion: the server rate-limits verification at 10/min, so
  // firing Promise.all for a bulk delete would 429 partway through a large
  // selection and Promise.all would present a total failure while some items
  // were already deleted. Each item is deleted one at a time; failures are
  // collected and reported per-item instead of aborting the batch.
  const handleDelete = async () => {
    if (deleting) return;
    const ids = [...selectedIds];
    if (ids.length === 0) return;
    setDeleting(true);
    setDeleteError('');
    const failed: string[] = [];
    for (const id of ids) {
      try {
        await deleteMediaItem(id, deletePassword);
      } catch (e: any) {
        failed.push(String(id));
      }
    }
    setDeletePassword('');
    setDeleteOpen(false);
    setSelectedIds(new Set());
    if (failed.length === 0) {
      const msg = ids.length > 1 ? `${ids.length} items deleted` : 'Media deleted';
      setDeleted(msg);
      toast(msg, 'success');
    } else {
      const msg = `${ids.length - failed.length}/${ids.length} deleted · ${failed.length} failed (rate-limited?)`;
      setDeleted(msg);
      toast(msg, 'warning');
    }
    setTimeout(() => setDeleted(''), 4000);
    await fetchMedia();
    setDeleting(false);
  };

  const viewerTimestamp = locationTimestamp(selectedItem);

  return (
    <div className="p-4 space-y-4">
      {selectedItem && !manageMode ? (
        /* ─── Media Viewer ─────────────────────────────────────────────── */
        <div>
          <div className="flex items-center gap-2 mb-3">
            <button
              onClick={handleClose}
              aria-label="Back to media grid"
              className="text-mag-text-dim/60 hover:text-mag-text transition-colors"
            >
              <ChevronLeft size={18} />
            </button>
            <span className="text-[11px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold flex-1 truncate">
              {selectedItem.type === 'photo' ? 'PHOTO' : 'AUDIO'} — {formatTimestamp(viewerTimestamp)}
            </span>
            {/* Single-item delete (step-up password) — owner/admin only */}
            {canManage && (
              <button
                onClick={() => {
                  setDeletePassword('');
                  setDeleteError('');
                  setDeleteOpen(true);
                }}
                aria-label="Delete this media item"
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] font-mono font-bold text-mag-danger/80 hover:text-mag-danger hover:bg-mag-danger/[0.06] border border-mag-danger/25 hover:border-mag-danger/50 transition-all"
              >
                <Trash2 size={11} />
                DELETE
              </button>
            )}
          </div>

          <div className="bg-mag-surface/30 border border-mag-border/30 rounded-xl overflow-hidden">
            {itemData?.type === 'photo' && itemData?.data_b64 && (
              <img
                src={`data:image/jpeg;base64,${itemData.data_b64}`}
                alt="Captured photo"
                className="w-full h-auto"
              />
            )}
            {itemData?.type === 'audio' && itemData?.data_b64 && (
              <div className="p-6 text-center">
                <div className="w-16 h-16 rounded-full bg-mag-primary/10 border border-mag-primary/30 flex items-center justify-center mx-auto mb-4">
                  <Music size={24} className="text-mag-primary" />
                </div>
                <button
                  onClick={togglePlay}
                  className="mag-btn-primary text-xs"
                >
                  {playing ? <Pause size={14} /> : <Play size={14} />}
                  {playing ? 'PAUSE' : 'PLAY'}
                </button>
                <audio
                  ref={audioRef}
                  src={`data:audio/mp4;base64,${itemData.data_b64}`}
                  preload="auto"
                  onEnded={() => setPlaying(false)}
                  onError={() => {
                    setPlaying(false);
                    setPlayError('Playback failed — the audio file may be unsupported by this browser.');
                  }}
                />
                {playError && (
                  <div className="mt-3 text-[10px] font-mono text-mag-danger/80 animate-fade-in">
                    {playError}
                  </div>
                )}
                <a
                  href={`data:audio/mp4;base64,${itemData.data_b64}`}
                  download={`evidence_${selectedItem.id}.m4a`}
                  className="mt-3 inline-flex items-center gap-1.5 text-[10px] font-mono font-bold text-mag-text-dim/60 hover:text-mag-primary transition-colors"
                >
                  <ChevronLeft size={11} className="rotate-90" />
                  DOWNLOAD FILE
                </a>
              </div>
            )}
            {!itemData && (
              <div className="p-8 text-center">
                <div className="text-mag-text-dim/40 text-xs font-mono">Loading...</div>
              </div>
            )}
          </div>

          <div className="mt-3 space-y-1.5">
            {selectedItem.lat && selectedItem.lng && (
              <div className="flex justify-between text-[10px] font-mono">
                <span className="text-mag-text-dim/60 font-bold">Location</span>
                <span className="text-mag-text font-bold">{selectedItem.lat.toFixed(6)}, {selectedItem.lng.toFixed(6)}</span>
              </div>
            )}
          </div>
        </div>
      ) : (
        /* ─── Media Grid ───────────────────────────────────────────────── */
        <div>
          <div className="flex items-center gap-1.5 text-[11px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold mb-3 px-1">
            <Camera size={12} className="text-mag-primary" />
            Captured Media
            {manageMode && (
              <span className="ml-auto flex items-center gap-1 text-mag-text-dim/50">
                <Lock size={9} />
                delete requires password
              </span>
            )}
            {canManage && !manageMode && (
              <button
                onClick={toggleManage}
                className="ml-auto flex items-center gap-1 px-2 py-1 rounded-lg border border-mag-border/40 text-mag-text-dim/50 hover:text-mag-text hover:border-mag-border text-[9px] font-mono font-bold transition-all"
              >
                <Trash2 size={9} />
                MANAGE
              </button>
            )}
          </div>

          {deleted && (
            <div className="mb-2.5 flex items-center gap-2 px-3 py-2 rounded-lg bg-mag-accent/[0.06] border border-mag-accent/25 text-mag-accent text-[10px] font-mono font-bold animate-fade-in">
              <ShieldCheck size={11} />
              {deleted}
            </div>
          )}

          {media.length === 0 ? (
            <div className="text-center py-10">
              <div className="w-14 h-14 rounded-2xl bg-mag-surface/40 border border-mag-border/30 flex items-center justify-center mx-auto mb-3">
                <ImageOff size={22} className="text-mag-text-dim/20" />
              </div>
              <div className="text-mag-text-dim/60 text-sm font-bold mb-1">No media captured</div>
              <div className="text-mag-text-dim/35 text-xs font-mono leading-relaxed max-w-[220px] mx-auto">
                Use the <span className="text-mag-primary/60 font-bold">Commands</span> tab to capture photos and audio remotely. All media is stored as evidence with cryptographic integrity.
              </div>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-2">
                {media.map((item) => {
                  const checked = selectedIds.has(item.id);
                  return (
                    <button
                      key={item.id}
                      onClick={() => (manageMode ? toggleSelected(item.id) : handleSelect(item))}
                      className={cn(
                        'mag-card text-left hover:border-mag-primary/30 hover:shadow-mag-glow transition-all duration-200 p-3 relative',
                        manageMode && checked && 'border-mag-primary/60 ring-1 ring-mag-primary/40'
                      )}
                    >
                      {manageMode && (
                        <span
                          className={cn(
                            'absolute top-2 right-2 w-4 h-4 rounded border flex items-center justify-center text-[9px] font-bold transition-all',
                            checked
                              ? 'bg-mag-primary border-mag-primary text-white'
                              : 'border-mag-border text-transparent'
                          )}
                        >
                          ✓
                        </span>
                      )}
                      <div className="flex items-center justify-center h-16 mb-2 rounded-lg bg-mag-bg/40">
                        {item.type === 'photo' ? (
                          <Camera size={20} className="text-mag-primary/40" />
                        ) : (
                          <Music size={20} className="text-mag-secondary/40" />
                        )}
                      </div>
                      <div className="font-mono text-[11px] text-mag-text font-bold flex items-center gap-1.5">
                        <span className={item.type === 'photo' ? 'text-mag-primary' : 'text-mag-secondary'}>
                          {item.type === 'photo' ? '📷' : '🎤'}
                        </span>
                        {item.type.toUpperCase()}
                      </div>
                      <div className="font-mono text-[10px] text-mag-text-dim/50 mt-0.5 font-bold">
                        {formatTimestamp(locationTimestamp(item))}
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Manage mode action bar */}
              {manageMode && (
                <div className="mt-3 flex items-center gap-2">
                  <button
                    onClick={() => setSelectedIds(new Set(media.map((m) => m.id)))}
                    className="px-3 py-2 rounded-lg border border-mag-border/40 text-mag-text-dim/60 hover:text-mag-text text-[10px] font-mono font-bold transition-all"
                  >
                    Select all
                  </button>
                  <button
                    onClick={() => setSelectedIds(new Set())}
                    className="px-3 py-2 rounded-lg border border-mag-border/40 text-mag-text-dim/60 hover:text-mag-text text-[10px] font-mono font-bold transition-all"
                  >
                    Clear
                  </button>
                  <button
                    onClick={() => {
                      setDeletePassword('');
                      setDeleteError('');
                      setDeleteOpen(true);
                    }}
                    disabled={selectedIds.size === 0}
                    className="ml-auto flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-mag-danger/90 hover:bg-mag-danger disabled:opacity-40 text-white text-[10px] font-mono font-bold uppercase tracking-wider transition-all"
                  >
                    <Trash2 size={11} />
                    Delete ({selectedIds.size})
                  </button>
                  <button
                    onClick={toggleManage}
                    className="px-3 py-2 rounded-lg border border-mag-border/40 text-mag-text-dim/60 hover:text-mag-text text-[10px] font-mono font-bold transition-all"
                  >
                    <X size={11} className="inline -mt-0.5 mr-1" />
                    Exit
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ─── Step-up password modal (portaled — escapes any clipped ancestor) ── */}
      {deleteOpen &&
        createPortal(
          <div className="fixed inset-0 z-[2100] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label="Confirm deletion">
            <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => !deleting && setDeleteOpen(false)} />
            <div className="relative mag-panel w-full max-w-sm p-5 space-y-4 animate-fade-in shadow-2xl">
              <div className="flex items-start gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-mag-danger/15 border border-mag-danger/30 flex items-center justify-center shrink-0">
                  <Trash2 size={14} className="text-mag-danger" />
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-bold text-mag-text tracking-wide">
                    DELETE MEDIA
                  </div>
                  <div className="text-[9px] font-mono text-mag-text-dim/50 uppercase tracking-[0.15em] font-bold mt-0.5">
                    {selectedIds.size > 0 ? `${selectedIds.size} item(s)` : '1 item'} · irreversible
                  </div>
                </div>
                <button
                  onClick={() => !deleting && setDeleteOpen(false)}
                  aria-label="Close"
                  className="ml-auto w-7 h-7 rounded-lg border border-mag-border/40 text-mag-text-dim/60 hover:text-mag-text flex items-center justify-center transition-all"
                >
                  <X size={13} />
                </button>
              </div>

              <div className="flex items-start gap-2 px-3 py-2.5 rounded-lg bg-mag-warning/[0.05] border border-mag-warning/20">
                <Lock size={12} className="text-mag-warning shrink-0 mt-0.5" />
                <div className="text-[10px] font-mono text-mag-text-dim/70 leading-relaxed">
                  For security, deletions require a step-up password. This session
                  verifies with <span className="font-bold text-mag-text-dim/90">{stepUpPasswordHint()}</span>.
                  Deleting evidence cannot be undone.
                </div>
              </div>

              <div>
                <label className="text-[10px] font-mono text-mag-text-dim/60 font-bold mb-1 block">
                  Password
                </label>
                <input
                  type="password"
                  value={deletePassword}
                  onChange={(e) => setDeletePassword(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleDelete()}
                  autoFocus
                  aria-label="Password"
                  className="w-full bg-mag-bg/60 border border-mag-border/40 rounded-lg px-3 py-2 text-xs font-mono text-mag-text placeholder:text-mag-text-dim/30 focus:outline-none focus:border-mag-primary/60 transition-colors"
                  placeholder="Enter password"
                />
              </div>

              {deleteError && (
                <div className="text-[10px] font-mono text-red-400 animate-fade-in">{deleteError}</div>
              )}

              <div className="flex gap-2">
                <button
                  onClick={handleDelete}
                  disabled={deleting || !deletePassword}
                  className="flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg bg-mag-danger/90 hover:bg-mag-danger disabled:opacity-40 text-white text-[10px] font-mono font-bold uppercase tracking-wider transition-all"
                >
                  <Trash2 size={11} />
                  {deleting ? 'Deleting...' : 'Confirm delete'}
                </button>
                <button
                  onClick={() => setDeleteOpen(false)}
                  disabled={deleting}
                  className="px-3 py-2 rounded-lg border border-mag-border/40 text-mag-text-dim/70 hover:text-mag-text text-[10px] font-mono font-bold transition-all"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
    </div>
  );
}
