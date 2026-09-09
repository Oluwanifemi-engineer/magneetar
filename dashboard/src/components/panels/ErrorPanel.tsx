'use client';

import { useState, useEffect, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { ErrorLogEntry } from '@/types';
import { cn } from '@/lib/utils';
import { AlertTriangle, Bug, CheckCircle, XCircle, ChevronDown, ChevronUp, RefreshCw, Clock, Wifi, ShieldCheck } from 'lucide-react';
import { MagStatusPill, MagButton } from '@/components/ui/MagPrimitives';
import { ErrorSkeleton } from '@/components/ui/Skeleton';
import { useToast } from '@/components/ui/Toast';

export function ErrorPanel() {
  const { isConnected } = useStore();
  const { toast } = useToast();
  const [errors, setErrors] = useState<ErrorLogEntry[]>([]);
  const [unresolvedCount, setUnresolvedCount] = useState(0);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [showUnresolvedOnly, setShowUnresolvedOnly] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState('');

  const fetchErrors = useCallback(async () => {
    if (!isConnected) return;
    setLoading(true);
    try {
      const api = getAPI();
      const data = await api.getErrors(showUnresolvedOnly);
      setErrors(data.errors);
      setUnresolvedCount(data.unresolved_count);
      setTotalCount(data.total_count);
      setErrorMessage('');
    } catch (e: any) {
      setErrorMessage(e.message || 'Failed to fetch errors');
    } finally {
      setLoading(false);
    }
  }, [isConnected, showUnresolvedOnly]);

  useEffect(() => {
    fetchErrors();
    const interval = setInterval(fetchErrors, 30000);
    return () => clearInterval(interval);
  }, [fetchErrors]);

  const handleResolve = async (errorId: number) => {
    try {
      const api = getAPI();
      await api.resolveError(errorId);
      toast('Error marked as resolved', 'success');
      fetchErrors();
    } catch (e: any) {
      setErrorMessage(e.message || 'Failed to resolve error');
      toast(e.message || 'Failed to resolve error', 'error');
    }
  };

  const formatTimestamp = (ts: string) => {
    try {
      const d = new Date(ts);
      const now = new Date();
      const diff = Math.floor((now.getTime() - d.getTime()) / 1000);
      if (diff < 60) return 'just now';
      if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
      if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch {
      return ts;
    }
  };

  return (
    <div className="p-4 space-y-4">
      <div className="mag-panel-header justify-between">
        <div className="flex items-center gap-2">
          <Bug size={14} className="text-mag-text" />
          <span className="text-sm font-bold text-mag-text font-display tracking-wider">ERROR LOG</span>
        </div>
        <div className="flex items-center gap-2">
          {unresolvedCount > 0 && (
            <MagStatusPill variant="danger">
              {unresolvedCount} open
            </MagStatusPill>
          )}
          <button
            onClick={fetchErrors}
            className="p-1.5 rounded hover:bg-mag-surface-hover transition-colors"
            title="Refresh"
          >
            <RefreshCw size={14} className={cn('text-mag-text-muted', loading && 'animate-spin')} />
          </button>
        </div>
      </div>

      {/* Filter Toggle */}
      <div className="flex items-center gap-2 mb-3">
        <MagButton
          variant={showUnresolvedOnly ? 'subtle' : 'ghost'}
          size="sm"
          onClick={() => setShowUnresolvedOnly(!showUnresolvedOnly)}
        >
          Unresolved only
        </MagButton>
        <span className="text-[10px] font-mono text-mag-text-muted/60">
          {totalCount} total
        </span>
      </div>

      {/* Error Message */}
      {errorMessage && (
        <div className="mag-danger-block flex items-center gap-2 p-3">
          <XCircle size={12} className="text-red-500 shrink-0" />
          <span className="text-[11px] font-mono text-red-500">{errorMessage}</span>
        </div>
      )}

      {/* Loading */}
      {loading && errors.length === 0 && (
        <ErrorSkeleton />
      )}

      {/* Empty State */}
      {!loading && errors.length === 0 && (
        <div className="mag-empty">
          <div className="mag-empty-icon">
            <ShieldCheck size={24} className="text-emerald-400/60" />
          </div>
          <div className="mag-empty-head">
            {showUnresolvedOnly ? 'All resolved' : 'All clear'}
          </div>
          <div className="mag-empty-sub">
            {showUnresolvedOnly
              ? 'All errors have been resolved. Toggle the filter to see the full history.'
              : 'No errors recorded. The server is running smoothly.'}
          </div>
        </div>
      )}

      {/* Error List */}
      <div className="space-y-2">
        {errors.map((error) => (
          <div
            key={error.id}
            className={cn(
              'rounded-lg transition-all duration-200',
              error.resolved
                ? 'mag-row opacity-60'
                : 'mag-row hover:bg-mag-surface-raised/40',
            )}
          >
            {/* Error Header */}
            <button
              onClick={() => setExpandedId(expandedId === error.id ? null : error.id)}
              className="w-full flex items-start gap-2 p-3 text-left"
            >
              <div className="mt-0.5 flex-shrink-0">
                {error.level === 'CRITICAL' ? (
                  <AlertTriangle size={14} className="text-red-500" />
                ) : (
                  <Bug size={14} className="text-amber-500" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <MagStatusPill
                    variant={error.level === 'CRITICAL' ? 'danger' : 'elevated'}
                    className="shrink-0"
                  >
                    {error.level}
                  </MagStatusPill>
                  <span className="text-[10px] font-mono text-mag-text-muted truncate flex-1">
                    {error.request_path || error.source || 'unknown'}
                  </span>
                  {expandedId === error.id ? (
                    <ChevronUp size={12} className="text-mag-text-muted flex-shrink-0" />
                  ) : (
                    <ChevronDown size={12} className="text-mag-text-muted flex-shrink-0" />
                  )}
                </div>
                <div className="text-xs text-mag-text font-medium truncate">
                  {error.message}
                </div>
                <div className="flex items-center gap-3 mt-1">
                  <span className="flex items-center gap-1 text-[9px] font-mono text-mag-text-muted/60">
                    <Clock size={9} className="text-mag-text-muted" />
                    {formatTimestamp(error.timestamp)}
                  </span>
                  {error.request_ip && (
                    <span className="flex items-center gap-1 text-[9px] font-mono text-mag-text-muted/60">
                      <Wifi size={9} className="text-mag-text-muted" />
                      {error.request_ip}
                    </span>
                  )}
                </div>
              </div>
            </button>

            {/* Expanded Details */}
            {expandedId === error.id && (
              <div className="px-3 pb-3 space-y-2 animate-fade-in border-t" style={{ borderColor: 'rgba(31,41,55,0.4)' }}>
                {error.request_method && (
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] font-mono text-mag-text-muted/60 w-16">Method:</span>
                    <span className="text-[10px] font-mono text-mag-text font-bold">{error.request_method}</span>
                  </div>
                )}
                {error.request_path && (
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] font-mono text-mag-text-muted/60 w-16">Path:</span>
                    <span className="text-[10px] font-mono text-mag-text-muted/80 truncate">{error.request_path}</span>
                  </div>
                )}
                {error.request_ip && (
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] font-mono text-mag-text-muted/60 w-16">Client IP:</span>
                    <span className="text-[10px] font-mono text-mag-text-muted">{error.request_ip}</span>
                  </div>
                )}
                {error.device_id && (
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] font-mono text-mag-text-muted/60 w-16">Device:</span>
                    <span className="text-[10px] font-mono text-mag-text font-bold">{error.device_id}</span>
                  </div>
                )}
                {error.traceback && (
                  <div className="mt-2">
                    <span className="text-[9px] font-mono text-mag-text-muted/60 block mb-1">Traceback:</span>
                    <pre className="text-[9px] font-mono text-mag-text-muted/70 bg-mag-surface/40 border border-mag-border rounded p-2 overflow-x-auto max-h-32 leading-relaxed">
                      {error.traceback}
                    </pre>
                  </div>
                )}
                {error.resolved && (
                  <div className="flex items-center gap-2 pt-1">
                    <CheckCircle size={10} className="text-mag-text" />
                    <span className="text-[9px] font-mono text-mag-text">
                      Resolved by {error.resolved_by || 'unknown'} {error.resolved_at ? formatTimestamp(error.resolved_at) : ''}
                    </span>
                  </div>
                )}
                {!error.resolved && (
                  <MagButton
                    variant="ghost"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleResolve(error.id);
                    }}
                  >
                    Mark Resolved
                  </MagButton>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
