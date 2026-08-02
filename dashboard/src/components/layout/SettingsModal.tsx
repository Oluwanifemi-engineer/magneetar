'use client';

import { useState } from 'react';
import { createPortal } from 'react-dom';
import { useStore } from '@/store/useStore';
import { getAPI } from '@/lib/api';
import { X, Trash2, ShieldAlert } from 'lucide-react';

/**
 * Settings modal (opened from the header gear). Account info + the Danger
 * Zone. Account deletion lives HERE — deliberately NOT in the main header,
 * where a stressed user could hit it by accident.
 */
export function SettingsModal({ onClose }: { onClose: () => void }) {
  const { serverUrl, logout } = useStore();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState('');

  const authMode =
    typeof window !== 'undefined' ? sessionStorage.getItem('mt_auth_mode') : null;

  const handleDelete = async () => {
    setDeleting(true);
    setError('');
    try {
      await getAPI().deleteAccount();
      logout();
      window.location.href = '/login';
    } catch (e: any) {
      setError(e.message || 'Account deletion failed');
      setDeleting(false);
    }
  };

  // Rendered through a portal into document.body. The modal used to live
  // inside the <header>, whose backdrop-blur (backdrop-filter) establishes a
  // containing block for fixed-position descendants — the "fixed" modal was
  // contained by the 56px header and clipped by its overflow-hidden, so
  // clicking SETTINGS appeared to do nothing.
  return createPortal(
    <div
      className="fixed inset-0 z-[2000] flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Settings"
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      <div className="relative mag-panel w-full max-w-md p-6 space-y-6 animate-fade-in shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-bold text-mag-text tracking-wide">SETTINGS</h2>
            <div className="text-[9px] font-mono text-mag-text-dim/50 uppercase tracking-[0.2em] font-bold mt-0.5">
              Account &amp; security
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close settings"
            className="w-8 h-8 rounded-lg border border-mag-border/40 text-mag-text-dim/60 hover:text-mag-text hover:border-mag-border flex items-center justify-center transition-all"
          >
            <X size={14} />
          </button>
        </div>

        {/* Account */}
        <div className="bg-mag-surface/30 border border-mag-border/30 rounded-xl p-4 space-y-2">
          <div className="text-[10px] font-mono text-mag-text-dim/70 uppercase tracking-wider font-bold mb-1">
            Account
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Auth Mode</span>
            <span className="text-[11px] font-mono text-mag-accent font-bold">
              {authMode === 'user' ? 'USER ACCOUNT' : 'API KEY'}
            </span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-[11px] font-mono text-mag-text-dim/60 font-bold">Server</span>
            <span className="text-[11px] font-mono text-mag-text font-bold truncate max-w-[220px]">
              {serverUrl}
            </span>
          </div>
          <div className="text-[10px] font-mono text-mag-text-dim/40 leading-relaxed pt-2 border-t border-mag-border/20">
            Alert recipients (SMS / WhatsApp / email) are set per device under Location →
            Alert Settings.
          </div>
        </div>

        {/* Danger Zone */}
        <div className="bg-mag-danger/[0.03] border border-mag-danger/20 rounded-xl p-4">
          <div className="flex items-center gap-1.5 text-[10px] font-mono text-mag-danger uppercase tracking-wider font-bold mb-2">
            <ShieldAlert size={12} />
            Danger Zone
          </div>
          {!confirmDelete ? (
            <button
              onClick={() => { setConfirmDelete(true); setError(''); }}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border border-mag-danger/30 text-mag-danger/90 hover:text-mag-danger hover:border-mag-danger/60 hover:bg-mag-danger/[0.05] text-[11px] font-mono font-bold uppercase tracking-wider transition-all"
            >
              <Trash2 size={13} />
              Delete Account Permanently
            </button>
          ) : (
            <div className="space-y-2.5">
              <div className="text-[11px] font-mono text-mag-danger/90 leading-relaxed">
                Permanently delete this account and ALL linked devices? Every location,
                media file, evidence case, alert and recovery request is erased. This
                cannot be undone.
              </div>
              {error && <div className="text-[10px] font-mono text-red-400">{error}</div>}
              <div className="flex gap-2">
                <button
                  onClick={handleDelete}
                  disabled={deleting}
                  className="flex-1 flex items-center justify-center gap-2 py-2 rounded-lg bg-mag-danger/90 hover:bg-mag-danger disabled:opacity-50 text-white text-[11px] font-bold transition-all"
                >
                  <Trash2 size={12} />
                  {deleting ? 'DELETING...' : 'Yes, Delete Everything'}
                </button>
                <button
                  onClick={() => setConfirmDelete(false)}
                  disabled={deleting}
                  className="px-4 py-2 rounded-lg border border-mag-border/40 text-mag-text-dim/70 hover:text-mag-text text-[11px] font-bold transition-all"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
