'use client';

import { useState, useEffect, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { cn, formatTimestamp } from '@/lib/utils';
import { Camera, Image, Music, Play, Pause, X, ChevronLeft } from 'lucide-react';

export function MediaGallery() {
  const { media, setMedia, selectedDeviceId } = useStore();
  const [selectedItem, setSelectedItem] = useState<any>(null);
  const [itemData, setItemData] = useState<any>(null);
  const [playing, setPlaying] = useState(false);

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
  };

  return (
    <div className="p-4 space-y-4">
      {selectedItem ? (
        /* Media Viewer */
        <div>
          <div className="flex items-center gap-2 mb-3">
            <button
              onClick={handleClose}
              className="text-mag-text-dim/60 hover:text-mag-text transition-colors"
            >
              <ChevronLeft size={18} />
            </button>
            <span className="text-[11px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold">
              {selectedItem.type === 'photo' ? 'PHOTO' : 'AUDIO'} — {formatTimestamp(selectedItem.timestamp)}
            </span>
          </div>

          {/* Media Content */}
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
                  onClick={() => setPlaying(!playing)}
                  className="mag-btn-primary text-xs"
                >
                  {playing ? <Pause size={14} /> : <Play size={14} />}
                  {playing ? 'PAUSE' : 'PLAY'}
                </button>
                <audio
                  src={`data:audio/mp4;base64,${itemData.data_b64}`}
                  autoPlay={playing}
                  onEnded={() => setPlaying(false)}
                />
              </div>
            )}
            {!itemData && (
              <div className="p-8 text-center">
                <div className="text-mag-text-dim/40 text-xs font-mono">Loading...</div>
              </div>
            )}
          </div>

          {/* Metadata */}
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
        /* Media Grid */
        <div>
          <div className="flex items-center gap-1.5 text-[11px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold mb-3 px-1">
            <Camera size={12} className="text-mag-primary" />
            Captured Media
          </div>

          {media.length === 0 ? (
            <div className="text-center py-8">
              <Camera size={28} className="mx-auto text-mag-text-dim/20 mb-3" />
              <div className="text-mag-text-dim/50 text-sm font-bold">No media captured.</div>
              <div className="text-mag-text-dim/30 text-xs font-mono mt-1">
                Use the Commands tab to capture.
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {media.map((item) => (
                <button
                  key={item.id}
                  onClick={() => handleSelect(item)}
                  className="mag-card text-left hover:border-mag-primary/30 hover:shadow-mag-glow transition-all duration-200 p-3"
                >
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
                    {formatTimestamp(item.timestamp)}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
