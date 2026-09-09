'use client';

export default function DashboardError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="h-screen flex items-center justify-center bg-mag-bg">
      <div className="text-center max-w-md mx-auto p-8">
        <div className="text-4xl mb-4">⚠️</div>
        <h2 className="text-mag-text text-xl font-bold mb-2">Something went wrong</h2>
        <p className="text-mag-text-dim text-sm font-mono mb-4 break-all">
          {error.message || 'Unknown error'}
        </p>
        {error.digest && (
          <p className="text-mag-text-muted text-xs font-mono mb-4">
            Digest: {error.digest}
          </p>
        )}
        <pre className="text-mag-text-muted text-xs font-mono text-left rounded-xl p-4 mb-4 overflow-auto max-h-40 mag-panel-elevated">
          {error.stack || 'No stack trace'}
        </pre>
        <button
          onClick={reset}
          className="px-6 py-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-white text-sm font-bold transition-colors shadow-glow-md"
        >
          Try Again
        </button>
      </div>
    </div>
  );
}
