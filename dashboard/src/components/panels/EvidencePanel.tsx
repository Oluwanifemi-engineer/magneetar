'use client';

import { useState, useEffect, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';
import { cn } from '@/lib/utils';
import { ClipboardList, FileText, Loader, ShieldCheck } from 'lucide-react';
import { EvidenceSkeleton } from '@/components/ui/Skeleton';

export function EvidencePanel() {
  const { selectedDeviceId } = useStore();
  const { toast } = useToast();
  const [evidence, setEvidence] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');

  const fetchEvidence = useCallback(async () => {
    if (!selectedDeviceId) return;
    try {
      const api = getAPI();
      const res = await api.getEvidence(selectedDeviceId);
      setEvidence(res);
    } catch (e) {
      console.error('Failed to fetch evidence:', e);
    }
  }, [selectedDeviceId]);

  useEffect(() => {
    fetchEvidence();
  }, [fetchEvidence]);

  const handleGenerate = async () => {
    if (!selectedDeviceId) return;
    setGenerating(true);
    setError('');
    try {
      const api = getAPI();
      await api.generateEvidencePDF(selectedDeviceId);
      toast('Recovery dossier downloaded — PDF saved to your device', 'success');
      await fetchEvidence();
    } catch (e: any) {
      const message = e?.message || 'Failed to generate dossier';
      setError(message);
      toast(message, 'error');
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-1.5 text-[11px] font-mono text-gray-700/70 uppercase tracking-wider font-bold mb-3 px-1">
        <ClipboardList size={12} className="text-gray-900" />
        Evidence Locker
      </div>

      {/* Evidence Summary */}
      <div className="bg-gray-50/40 border border-gray-200/40 rounded-xl p-4">
        {loading && !evidence ? (
          <EvidenceSkeleton />
        ) : evidence?.case_id ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
              <div>
                <span className="text-gray-700/60 font-bold">Case ID</span>
                <div className="text-gray-900 font-bold">#{evidence.case_id}</div>
              </div>
              <div>
                <span className="text-gray-700/60 font-bold">Status</span>
                <div className={cn(
                  'font-bold',
                  evidence.status === 'active' ? 'text-amber-600' : 'text-gray-900'
                )}>
                  {evidence.status?.toUpperCase()}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <div className="bg-white/40 border border-gray-200/30 rounded-lg p-2 text-center">
                <div className="font-mono text-lg font-bold text-gray-900">{evidence.item_counts?.locations || 0}</div>
                <div className="text-[9px] font-mono text-gray-700/50 font-bold">LOCATIONS</div>
              </div>
              <div className="bg-white/40 border border-gray-200/30 rounded-lg p-2 text-center">
                <div className="font-mono text-lg font-bold text-gray-900">{evidence.item_counts?.photos || 0}</div>
                <div className="text-[9px] font-mono text-gray-700/50 font-bold">PHOTOS</div>
              </div>
              <div className="bg-white/40 border border-gray-200/30 rounded-lg p-2 text-center">
                <div className="font-mono text-lg font-bold text-gray-900">{evidence.item_counts?.audio || 0}</div>
                <div className="text-[9px] font-mono text-gray-700/50 font-bold">AUDIO</div>
              </div>
            </div>

            {evidence.sha256_chain && (
              <div className="text-[10px] font-mono text-gray-700/40 break-all">
                <span className="text-gray-700/60 font-bold">SHA-256 Chain: </span>
                {evidence.sha256_chain.slice(0, 32)}...
              </div>
            )}
          </div>
        ) : (
          <div className="text-center py-6">
            <div className="w-12 h-12 rounded-2xl bg-gray-50/40 border border-gray-200/30 flex items-center justify-center mx-auto mb-3">
              <ShieldCheck size={20} className="text-gray-900/40" />
            </div>
            <div className="text-gray-700/60 text-sm font-bold mb-1">No active evidence case</div>
            <div className="text-gray-700/35 text-xs font-mono leading-relaxed max-w-[240px] mx-auto">
              Evidence is automatically created when theft is detected. All location data, photos, and audio are cryptographically chained for forensic integrity.
            </div>
          </div>
        )}
      </div>

      {/* Export Recovery Dossier */}
      <button
        onClick={handleGenerate}
        disabled={generating || !selectedDeviceId}
        className="mag-btn-primary w-full text-xs"
      >
        {generating ? (
          <>
            <Loader size={14} className="animate-spin" />
            GENERATING DOSSIER...
          </>
        ) : (
          <>
            <FileText size={14} />
            EXPORT RECOVERY DOSSIER (PDF)
          </>
        )}
      </button>

      {error && <div className="text-[10px] font-mono text-red-400 break-words">{error}</div>}

      <p className="text-[10px] font-mono text-gray-700/40 leading-relaxed">
        One-click PDF for police or insurers: device info, location trail, command
        timeline (lock / siren / wipe), SHA-256-chained photos & audio, and alert
        history.
      </p>
    </div>
  );
}
