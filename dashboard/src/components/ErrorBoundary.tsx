'use client';

import React, { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

/**
 * Error Boundary — catches unhandled React errors and displays a
 * fallback UI instead of breaking the entire page.
 *
 * Usage:
 *   <ErrorBoundary>
 *     <YourComponent />
 *   </ErrorBoundary>
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('[ErrorBoundary]', error, errorInfo);
    this.props.onError?.(error, errorInfo);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="flex flex-col items-center justify-center h-full p-8 text-center">
          {/* Error icon */}
          <div className="w-12 h-12 rounded-xl bg-mag-danger/10 border border-mag-danger/20 flex items-center justify-center mb-4">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-mag-danger">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>

          <h3 className="text-sm font-bold text-mag-text mb-1">
            Something went wrong
          </h3>
          <p className="text-[10px] font-mono text-mag-text-dim/50 mb-4 max-w-xs">
            {this.state.error?.message || 'An unexpected error occurred'}
          </p>

          <button
            onClick={this.handleRetry}
            className="mag-btn-primary text-[10px]"
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
            </svg>
            RETRY
          </button>

          <p className="text-[8px] font-mono text-mag-text-dim/30 mt-4">
            If this persists, check the server error log.
          </p>
        </div>
      );
    }

    return this.props.children;
  }
}

/**
 * Error boundary wrapper for async API calls.
 * Usage: wrap async operations that might fail.
 */
export function withErrorBoundary<T>(
  promise: Promise<T>,
  onError?: (error: Error) => void
): Promise<T> {
  return promise.catch((error) => {
    console.error('[AsyncError]', error);
    onError?.(error instanceof Error ? error : new Error(String(error)));
    throw error;
  });
}
