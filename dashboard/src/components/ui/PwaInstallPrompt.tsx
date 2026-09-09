'use client';

import { useState, useEffect } from 'react';
import { Download, X } from 'lucide-react';

/**
 * PwaInstallPrompt — shows a non-intrusive install banner for the PWA
 * on mobile devices when the beforeinstallprompt event fires.
 *
 * Dismissed state is persisted in localStorage for 7 days.
 */

const DISMISS_KEY = 'mt_pwa_install_dismissed';
const DISMISS_TTL = 7 * 24 * 60 * 60 * 1000; // 7 days

export function PwaInstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState<any>(null);
  const [show, setShow] = useState(false);
  const [installing, setInstalling] = useState(false);

  useEffect(() => {
    // Check if already dismissed recently
    const dismissed = localStorage.getItem(DISMISS_KEY);
    if (dismissed) {
      const ts = parseInt(dismissed, 10);
      if (Date.now() - ts < DISMISS_TTL) return;
    }

    // Check if already installed (standalone mode)
    if (window.matchMedia('(display-mode: standalone)').matches) return;

    // Check if on a supported platform (not desktop Chrome which shows its own bar)
    const isMobile = window.matchMedia('(max-width: 768px)').matches;
    if (!isMobile) return;

    const handler = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e);
      // Show after a short delay so it doesn't compete with onboarding
      setTimeout(() => setShow(true), 8000);
    };

    window.addEventListener('beforeinstallprompt', handler);
    return () => window.removeEventListener('beforeinstallprompt', handler);
  }, []);

  const handleInstall = async () => {
    if (!deferredPrompt) return;
    setInstalling(true);
    try {
      deferredPrompt.prompt();
      const { outcome } = await deferredPrompt.userChoice;
      if (outcome === 'accepted') {
        setShow(false);
      }
    } catch {
      // User cancelled or error
    } finally {
      setDeferredPrompt(null);
      setInstalling(false);
    }
  };

  const handleDismiss = () => {
    setShow(false);
    localStorage.setItem(DISMISS_KEY, Date.now().toString());
  };

  if (!show) return null;

  return (
    <div className="fixed bottom-4 left-4 right-4 z-50 sm:left-auto sm:right-4 sm:w-80 animate-slide-up">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl p-4 flex items-start gap-3">
        {/* Icon */}
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center shrink-0">
          <Download size={18} className="text-white" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="text-xs font-bold text-white mb-0.5">
            Install Magneetar
          </div>
          <p className="text-[10px] text-mag-text-muted leading-relaxed">
            Add to your home screen for instant access and offline support.
          </p>

          <div className="flex items-center gap-2 mt-2.5">
            <button
              onClick={handleInstall}
              disabled={installing}
              className="px-3 py-1.5 rounded-lg bg-emerald-500 hover:bg-emerald-600 disabled:opacity-50 text-[10px] font-bold text-white transition-colors"
            >
              {installing ? 'Installing...' : 'Install'}
            </button>
            <button
              onClick={handleDismiss}
              className="px-3 py-1.5 rounded-lg border-mag-border/50 text-[10px] font-bold text-mag-text-muted hover:text-mag-text hover:border-mag-border transition-colors"
            >
              Later
            </button>
          </div>
        </div>

        {/* Close */}
        <button
          onClick={handleDismiss}            className="text-mag-text-muted hover:text-mag-text-dim transition-colors shrink-0"
          aria-label="Dismiss install prompt"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
}
