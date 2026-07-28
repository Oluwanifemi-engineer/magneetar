'use client';

import { useState, useEffect, useCallback } from 'react';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { ErrorLogEntry } from '@/types';
import { AlertTriangle, Bug, CheckCircle, XCircle, ChevronDown, ChevronUp, RefreshCw, Clock, Server, Wifi } from 'lucide-react';

export function ErrorPanel() {
  const { isConnected } = useStore();
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
      fetchErrors();
    } catch (e: any) {
      setErrorMessage(e.message || 'Failed to resolve error');
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
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Bug size={16} className="text-mag-primary" />
          <span className="text-sm font-bold text-mag-text font-display tracking-wider">ERROR LOG</span>
        </div>
        <div className="flex items-center gap-2">
          {unresolvedCount > 0 && (
            <span className="px-2 py-0.5 text-[10px] font-mono font-bold bg-mag-danger/10 text-mag-danger border border-mag-danger/30 rounded">
              {unresolvedCount} open
            </span>
          )}
          <button
            onClick={fetchErrors}
            className="p-1.5 rounded hover:bg-mag-surface/50 text-mag-text-dim/60 hover:text-mag-text-dim transition-colors"
            title="Refresh"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Filter Toggle */}
      <div className="flex items-center gap-2 mb-3">
        <button
          onClick={() => setShowUnresolvedOnly(!showUnresolvedOnly)}
          className={`px-3 py-1 text-[10px] font-mono font-bold rounded border transition-all ${
            showUnresolvedOnly
              ? 'bg-mag-warning/10 border-mag-warning/30 text-mag-warning'
              : 'bg-mag-surface/20 border-mag-border/30 text-mag-text-dim/60 hover:text-mag-text-dim/80'
          }`}
        >
          Unresolved only
        </button>
        <span className="text-[10px] font-mono text-mag-text-dim/40">
          {totalCount} total
        </span>
      </div>

      {/* Error Message */}
      {errorMessage && (
        <div className="px-3 py-2 bg-mag-danger/5 border border-mag-danger/20 rounded-lg flex items-center gap-2">
          <XCircle size={12} className="text-mag-danger" />
          <span className="text-[11px] font-mono text-mag-danger">{errorMessage}</span>
        </div>
      )}

      {/* Loading */}
      {loading && errors.length === 0 && (
        <div className="py-12 text-center">
          <div className="animate-spin w-6 h-6 border-2 border-mag-primary/30 border-t-mag-primary rounded-full mx-auto mb-3" />
          <div className="text-[10px] font-mono text-mag-text-dim/40 font-bold tracking-wider">LOADING ERRORS...</div>
        </div>
      )}

      {/* Empty State */}
      {!loading && errors.length === 0 && (
        <div className="py-12 text-center">
          <CheckCircle size={32} className="mx-auto text-mag-accent/50 mb-3" />
          <div className="text-sm font-bold text-mag-text-dim/60 mb-1">All Clear</div>
          <div className="text-[10px] font-mono text-mag-text-dim/40">
            No {showUnresolvedOnly ? 'unresolved ' : ''}errors found
          </div>
        </div>
      )}

      {/* Error List */}
      <div className="space-y-2">
        {errors.map((error) => (
          <div
            key={error.id}
            className={`border rounded-lg transition-all duration-200 ${
              error.resolved
                ? 'border-mag-border/20 bg-mag-surface/10 opacity-60'
                : 'border-mag-border/40 bg-mag-surface/20 hover:bg-mag-surface/30'
            }`}
          >
            {/* Error Header */}
            <button
              onClick={() => setExpandedId(expandedId === error.id ? null : error.id)}
              className="w-full flex items-start gap-2 p-3 text-left"
            >
              <div className="mt-0.5 flex-shrink-0">
                {error.level === 'CRITICAL' ? (
                  <AlertTriangle size={14} className="text-mag-danger" />
                ) : (
                  <Bug size={14} className="text-mag-warning" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded ${
                    error.level === 'CRITICAL'
                      ? 'bg-mag-danger/10 text-mag-danger'
                      : 'bg-mag-warning/10 text-mag-warning'
                  }`}>
                    {error.level}
                  </span>
                  <span className="text-[10px] font-mono text-mag-text-dim/50 truncate flex-1">
                    {error.request_path || error.source || 'unknown'}
                  </span>
                  {expandedId === error.id ? (
                    <ChevronUp size={12} className="text-mag-text-dim/40 flex-shrink-0" />
                  ) : (
                    <ChevronDown size={12} className="text-mag-text-dim/40 flex-shrink-0" />
                  )}
                </div>
                <div className="text-xs text-mag-text font-medium truncate">
                  {error.message}
                </div>
                <div className="flex items-center gap-3 mt-1">
                  <span className="flex items-center gap-1 text-[9px] font-mono text-mag-text-dim/40">
                    <Clock size={9} />
                    {formatTimestamp(error.timestamp)}
                  </span>
                  {error.request_ip && (
                    <span className="flex items-center gap-1 text-[9px] font-mono text-mag-text-dim/40">
                      <Wifi size={9} />
                      {error.request_ip}
                    </span>
                  )}
                </div>
              </div>
            </button>

            {/* Expanded Details */}
            {expandedId === error.id && (
              <div className="px-3 pb-3 space-y-2 animate-fade-in border-t border-mag-border/20 pt-2 mt-1">
                {error.request_method && (
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] font-mono text-mag-text-dim/40 w-16">Method:</span>
                    <span className="text-[10px] font-mono text-mag-text font-bold">{error.request_method}</span>
                  </div>
                )}
                {error.request_path && (
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] font-mono text-mag-text-dim/40 w-16">Path:</span>
                    <span className="text-[10px] font-mono text-mag-text-dim/80 truncate">{error.request_path}</span>
                  </div>
                )}
                {error.request_ip && (
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] font-mono text-mag-text-dim/40 w-16">Client IP:</span>
                    <span className="text-[10px] font-mono text-mag-text-dim/80">{error.request_ip}</span>
                  </div>
                )}
                {error.device_id && (
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] font-mono text-mag-text-dim/40 w-16">Device:</span>
                    <span className="text-[10px] font-mono text-mag-text-dim/80 font-bold text-mag-accent">{error.device_id}</span>
                  </div>
                )}
                {error.traceback && (
                  <div className="mt-2">
                    <span className="text-[9px] font-mono text-mag-text-dim/40 block mb-1">Traceback:</span>
                    <pre className="text-[9px] font-mono text-mag-text-dim/70 bg-mag-bg/50 border border-mag-border/20 rounded p-2 overflow-x-auto max-h-32 leading-relaxed">
                      {error.traceback}
                    </pre>
                  </div>
                )}
                {error.resolved && (
                  <div className="flex items-center gap-2 pt-1">
                    <CheckCircle size={10} className="text-mag-accent" />
                    <span className="text-[9px] font-mono text-mag-accent/80">
                      Resolved by {error.resolved_by || 'unknown'} {error.resolved_at ? formatTimestamp(error.resolved_at) : ''}
                    </span>
                  </div>
                )}
                {!error.resolved && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleResolve(error.id);
                    }}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-[10px] font-mono font-bold text-mag-accent border border-mag-accent/30 rounded hover:bg-mag-accent/5 transition-colors"
                  >
                    <CheckCircle size={10} />
                    Mark Resolved
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
