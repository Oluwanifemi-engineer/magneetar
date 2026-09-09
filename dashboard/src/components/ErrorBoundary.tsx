/**
 * Sentry Error Boundary Component with Graceful Fallback
 *
 * Catches React component errors and optionally reports them to Sentry.
 * Provides a fallback UI when errors occur.
 */

"use client";

import React, { Component, ErrorInfo, ReactNode } from "react";

// Safe Sentry wrapper that gracefully degrades when @sentry/nextjs is not present
let Sentry: any = null;
try {
  // Dynamically require if available
  Sentry = require("@sentry/nextjs");
} catch {
  // Sentry not available in this environment
  Sentry = null;
}

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class SentryErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log to console
    console.error("ErrorBoundary caught an error:", error, errorInfo);

    // Report to Sentry if available
    if (Sentry && typeof Sentry.withScope === "function") {
      try {
        Sentry.withScope((scope: any) => {
          scope.setExtras(errorInfo);
          scope.setTag("component", "ErrorBoundary");
          Sentry.captureException(error);
        });
      } catch (sentryError) {
        console.warn("Failed to report error to Sentry:", sentryError);
      }
    }

    // Call optional error handler
    this.props.onError?.(error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      // Custom fallback UI
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default fallback UI
      return <DefaultErrorFallback error={this.state.error} />;
    }

    return this.props.children;
  }
}

// Default fallback component
function DefaultErrorFallback({ error }: { error: Error | null }) {
  const handleRetry = () => {
    window.location.reload();
  };

  const handleReport = () => {
    if (Sentry && typeof Sentry.showReportDialog === "function") {
      try {
        Sentry.showReportDialog({
          eventId: Sentry.lastEventId?.(),
        });
        return;
      } catch {
        // Fallback below
      }
    }
    // Fallback report action
    alert("Error logged. Thank you for reporting!");
  };

  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] p-8 text-center bg-mag-bg text-mag-text rounded-xl border border-mag-border/50 m-4">
      <div className="text-5xl mb-4">⚠️</div>
      <h2 className="text-xl font-bold mb-2">Something went wrong</h2>
      <p className="text-mag-text-dim text-sm mb-6 max-w-md">
        An unexpected error occurred. Please try reloading the page.
      </p>

      {process.env.NODE_ENV === "development" && error && (
        <pre className="text-xs text-left bg-mag-surface/40 p-4 rounded-lg mb-6 max-w-2xl overflow-auto border border-mag-border text-red-400/80">
          {error.message}
          {error.stack && `\n\n${error.stack}`}
        </pre>
      )}

      <div className="flex gap-3">
        <button
          onClick={handleRetry}
          className="px-5 py-2.5 bg-emerald-500 text-white text-xs font-bold uppercase tracking-wider rounded-xl hover:bg-emerald-400 transition-colors shadow-glow-md"
        >
          Try Again
        </button>
        <button
          onClick={handleReport}
          className="px-5 py-2.5 bg-mag-surface/40 text-mag-text text-xs font-bold uppercase tracking-wider rounded-xl hover:bg-mag-surface-raised/40 transition-colors border border-mag-border"
        >
          Report Issue
        </button>
      </div>
    </div>
  );
}

export { SentryErrorBoundary as ErrorBoundary };
export default SentryErrorBoundary;
