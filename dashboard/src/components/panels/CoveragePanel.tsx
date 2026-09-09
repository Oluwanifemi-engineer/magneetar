'use client';

import { useState, useEffect } from 'react';
import { cn } from '@/lib/utils';
import { BarChart3, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';

interface CoverageData {
  timestamp: string;
  overall: { rate: number; total: number; covered: number };
  backend: { rate: number; tests: number; passed: number; failed: number };
  dashboard: { rate: number; tests: number; passed: number; failed: number };
  android: { tests: number; passed: number };
  modules: Array<{
    name: string;
    rate: number;
    total: number;
    covered: number;
  }>;
}

function getCoverageColor(rate: number): string {
  if (rate >= 80) return 'text-green-400';
  if (rate >= 60) return 'text-yellow-400';
  return 'text-red-400';
}

function getCoverageBg(rate: number): string {
  if (rate >= 80) return 'bg-green-400/10';
  if (rate >= 60) return 'bg-yellow-400/10';
  return 'bg-red-400/10';
}

function getCoverageIcon(rate: number) {
  if (rate >= 80) return <CheckCircle className="w-4 h-4 text-green-400" />;
  if (rate >= 60) return <AlertTriangle className="w-4 h-4 text-yellow-400" />;
  return <XCircle className="w-4 h-4 text-red-400" />;
}

export function CoveragePanel() {
  const [data, setData] = useState<CoverageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchCoverage() {
      try {
        const res = await fetch('/api/coverage');
        if (res.ok) {
          const json = await res.json();
          setData(json);
        } else {
          setError('Coverage data not available');
        }
      } catch {
        setError('Failed to load coverage data');
      } finally {
        setLoading(false);
      }
    }
    fetchCoverage();
  }, []);

  if (loading) {
    return (
      <div className="p-4 text-mag-text-muted">
        <div className="animate-pulse">Loading coverage data...</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-4">
        <div className="flex items-center gap-2 text-mag-text-muted">
          <BarChart3 className="w-4 h-4" />
          <span>{error || 'No coverage data available'}</span>
        </div>
        <p className="text-xs text-mag-text-muted mt-2">
          Coverage reports are generated during CI runs.
        </p>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center gap-2 mb-3">
        <BarChart3 className="w-4 h-4 text-blue-400" />
        <h3 className="text-sm font-semibold text-white">Test Coverage</h3>          <span className="text-xs text-mag-text-muted ml-auto">
          {new Date(data.timestamp).toLocaleDateString()}
        </span>
      </div>

      {/* Overall Coverage */}
      <div className={cn('p-3 rounded-lg', getCoverageBg(data.overall.rate))}>
        <div className="flex items-center justify-between">
          <span className="text-sm text-mag-text-dim">Overall</span>
          <div className="flex items-center gap-2">
            {getCoverageIcon(data.overall.rate)}
            <span className={cn('text-lg font-bold', getCoverageColor(data.overall.rate))}>
              {data.overall.rate.toFixed(1)}%
            </span>
          </div>
        </div>
        <div className="mt-2 h-1.5 bg-mag-border rounded-full overflow-hidden">
          <div
            className={cn('h-full rounded-full transition-all', {
              'bg-green-400': data.overall.rate >= 80,
              'bg-yellow-400': data.overall.rate >= 60 && data.overall.rate < 80,
              'bg-red-400': data.overall.rate < 60,
            })}
            style={{ width: `${data.overall.rate}%` }}
          />
        </div>
      </div>

      {/* Test Suites */}
      <div className="grid grid-cols-3 gap-2">
        <div className="p-2 bg-mag-surface-raised rounded">
          <div className="text-xs text-mag-text-muted">Backend</div>
          <div className="text-sm font-medium text-white">
            {data.backend.passed}/{data.backend.tests}
          </div>
          <div className={cn('text-xs', getCoverageColor(data.backend.rate))}>
            {data.backend.rate.toFixed(1)}% cov
          </div>
        </div>
        <div className="p-2 bg-mag-surface-raised rounded">
          <div className="text-xs text-mag-text-muted">Dashboard</div>
          <div className="text-sm font-medium text-white">
            {data.dashboard.passed}/{data.dashboard.tests}
          </div>
          <div className={cn('text-xs', getCoverageColor(data.dashboard.rate))}>
            {data.dashboard.rate.toFixed(1)}% cov
          </div>
        </div>
        <div className="p-2 bg-mag-surface-raised rounded">
          <div className="text-xs text-mag-text-muted">Android</div>
          <div className="text-sm font-medium text-white">
            {data.android.passed}/{data.android.tests}
          </div>
          <div className="text-xs text-mag-text-muted">JVM tests</div>
        </div>
      </div>

      {/* Module Breakdown */}
      {data.modules.length > 0 && (
        <div>
          <div className="text-xs text-mag-text-muted mb-2">Top Modules</div>
          <div className="space-y-1.5">
            {data.modules.slice(0, 5).map((mod) => (
              <div key={mod.name} className="flex items-center gap-2">
                <span className="text-xs text-mag-text-muted truncate w-24">{mod.name}</span>
                <div className="flex-1 h-1 bg-mag-border rounded-full overflow-hidden">
                  <div
                    className={cn('h-full rounded-full', {
                      'bg-green-400': mod.rate >= 80,
                      'bg-yellow-400': mod.rate >= 60 && mod.rate < 80,
                      'bg-red-400': mod.rate < 60,
                    })}
                    style={{ width: `${mod.rate}%` }}
                  />
                </div>
                <span className={cn('text-xs w-10 text-right', getCoverageColor(mod.rate))}>
                  {mod.rate.toFixed(0)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
