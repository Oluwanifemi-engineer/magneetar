'use client';

import { useState, useEffect, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { useToast } from '@/components/ui/Toast';
import { cn } from '@/lib/utils';
import { ClipboardList, FileText, Loader, ShieldCheck } from 'lucide-react';
import { MagButton } from '@/components/ui/MagPrimitives';
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
    try { const api = getAPI(); const res = await api.getEvidence(selectedDeviceId); setEvidence(res); }
    catch (e) { console.error('Failed to fetch evidence:', e); }
  }, [selectedDeviceId]);

  useEffect(() => { fetchEvidence(); }, [fetchEvidence]);

  const handleGenerate = async () => {
    if (!selectedDeviceId) return;
    setGenerating(true); setError('');
    try {
      const api = getAPI();
      await api.generateEvidencePDF(selectedDeviceId);
      toast('Recovery dossier downloaded', 'success');
      await fetchEvidence();
    } catch (e: any) {
      const message = e?.message || 'Failed to generate dossier';
      setError(message); toast(message, 'error');
    } finally { setGenerating(false); }
  };

  return (
    <div className="p-4 space-y-4">
      <div className="mag-panel-header border-b border-mag-border/50">
        <ClipboardList size={12} className="text-mag-text-muted" />
        <span className="mag-panel-label">Evidence Locker</span>
      </div>

      <div className="mag-panel-elevated p-4 space-y-3">
        {loading && !evidence ? (
          <EvidenceSkeleton />
        ) : evidence?.case_id ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div className="mag-stat-tile">
                <div className="text-[9px] font-mono text-mag-text-muted font-bold uppercase tracking-wider">Case ID</div>
                <div className="text-sm font-mono font-bold text-mag-text">#{evidence.case_id}</div>
              </div>
              <div className={cn(
                'mag-stat-tile',
                evidence.status === 'active' ? 'border-amber-500/20 bg-amber-500/5' : ''
              )}>
                <div className="text-[9px] font-mono text-mag-text-muted font-bold uppercase tracking-wider">Status</div>
                <div className={cn(
                  'text-sm font-mono font-bold uppercase',
                  evidence.status === 'active' ? 'text-amber-400' : 'text-mag-text'
                )}>
                  {evidence.status?.toUpperCase()}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2">
              {[
                { label: 'LOCATIONS', value: evidence.item_counts?.locations || 0 },
                { label: 'PHOTOS', value: evidence.item_counts?.photos || 0 },
                { label: 'AUDIO', value: evidence.item_counts?.audio || 0 },
              ].map(({ label, value }) => (
                <div key={label} className="mag-stat-tile">
                  <div className="font-mono text-lg font-bold text-mag-text tabular-nums">{value}</div>
                  <div className="text-[9px] font-mono text-mag-text-muted font-bold uppercase tracking-wider">{label}</div>
                </div>
              ))}
            </div>

            {evidence.sha256_chain && (
              <div className="text-[10px] font-mono text-mag-text-muted break-all">
                <span className="text-mag-text-dim font-bold">Integrity Chain: </span>
                {evidence.sha256_chain.slice(0, 32)}...
              </div>
            )}
          </div>
        ) : (
          <div className="mag-empty">
            <div className="mag-empty-icon">
              <ShieldCheck size={20} className="text-mag-text-muted" />
            </div>
            <div className="mag-empty-head">No active evidence case</div>
            <div className="mag-empty-sub">
              Evidence is automatically created when theft is detected.
            </div>
          </div>
        )}
      </div>

      {!selectedDeviceId ? null : (
        <MagButton
          variant="subtle"
          fullWidth
          loading={generating}
          icon={<FileText size={14} />}
          onClick={handleGenerate}
        >
          {generating ? 'GENERATING DOSSIER...' : 'EXPORT RECOVERY DOSSIER (PDF)'}
        </MagButton>
      )}

      {error && (
        <div className="text-[10px] font-mono text-red-400 break-words">{error}</div>
      )}

      <p className="text-[10px] font-mono text-mag-text-muted leading-relaxed">
        One-click PDF for police or insurers: device info, location trail, command
        timeline, tamper-proof photos & audio, and alert history.
      </p>
    </div>
  );
}
