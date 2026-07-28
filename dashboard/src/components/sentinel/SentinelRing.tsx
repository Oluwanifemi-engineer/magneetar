'use client';

import { useEffect, useState } from 'react';

interface SentinelRingProps {
  score: number; // 0-100
  threatLevel: string;
  anomalies?: string[];
}

function getScoreColor(score: number): string {
  if (score <= 30) return '#22C55E'; // Green - SAFE
  if (score <= 60) return '#F59E0B'; // Amber - ELEVATED
  if (score <= 80) return '#F97316'; // Orange - HIGH
  return '#EF4444'; // Red - CRITICAL
}

function getScoreBg(score: number): string {
  if (score <= 30) return 'rgba(34,197,94,0.08)';
  if (score <= 60) return 'rgba(245,158,11,0.08)';
  if (score <= 80) return 'rgba(249,115,22,0.08)';
  return 'rgba(239,68,68,0.08)';
}

function getThreatLabel(level: string): string {
  switch (level) {
    case 'SAFE': return 'SAFE';
    case 'ELEVATED': return 'ELEVATED';
    case 'HIGH': return 'HIGH';
    case 'CRITICAL': return 'CRITICAL';
    default: return 'UNKNOWN';
  }
}

export function SentinelRing({ score, threatLevel, anomalies = [] }: SentinelRingProps) {
  const [animatedScore, setAnimatedScore] = useState(0);
  const color = getScoreColor(score);
  const circumference = 2 * Math.PI * 45;
  const strokeDashoffset = circumference - (animatedScore / 100) * circumference;

  useEffect(() => {
    const timer = setTimeout(() => {
      setAnimatedScore(score);
    }, 100);
    return () => clearTimeout(timer);
  }, [score]);

  return (
    <div className="flex flex-col items-center">
      {/* Ring SVG */}
      <div className="relative">
        <svg width="120" height="120" viewBox="0 0 100 100">
          {/* Background circle */}
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke="rgba(42,42,56,0.5)"
            strokeWidth="8"
          />
          {/* Progress circle */}
          <circle
            cx="50"
            cy="50"
            r="45"
            fill="none"
            stroke={color}
            strokeWidth="8"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            transform="rotate(-90 50 50)"
            style={{
              transition: 'stroke-dashoffset 1s ease-out, stroke 0.5s ease',
              filter: `drop-shadow(0 0 8px ${color}40)`,
            }}
          />
          {/* Score text */}
          <text
            x="50"
            y="44"
            textAnchor="middle"
            fill={color}
            fontSize="26"
            fontWeight="bold"
            fontFamily="'JetBrains Mono', monospace"
          >
            {animatedScore}
          </text>
          <text
            x="50"
            y="60"
            textAnchor="middle"
            fill="rgba(152,152,168,0.5)"
            fontSize="8"
            fontFamily="'JetBrains Mono', monospace"
            fontWeight="bold"
          >
            THREAT SCORE
          </text>
        </svg>

        {/* Glow effect */}
        <div
          className="absolute inset-0 rounded-full"
          style={{
            background: `radial-gradient(circle, ${color}20 0%, transparent 70%)`,
            animation: score > 60 ? 'pulse 2s infinite' : 'none',
          }}
        />
      </div>

      {/* Threat Level Badge */}
      <div
        className="mt-2.5 px-3 py-1 rounded-lg font-mono text-[10px] font-bold uppercase tracking-widest"
        style={{
          color: color,
          backgroundColor: getScoreBg(score),
          border: `1px solid ${color}30`,
        }}
      >
        {getThreatLabel(threatLevel)}
      </div>

      {/* Anomalies List */}
      {anomalies.length > 0 && (
        <div className="mt-4 w-full max-w-[200px]">
          <div className="text-[10px] font-mono text-mag-text-dim/60 uppercase tracking-wider mb-1.5 font-bold">
            Anomalies Detected
          </div>
          <div className="space-y-1">
            {anomalies.slice(0, 5).map((anomaly, idx) => (
              <div
                key={idx}
                className="flex items-start gap-1.5 text-[10px] font-mono text-mag-warning bg-mag-warning/8 border border-mag-warning/15 rounded-lg px-2.5 py-1.5 font-bold"
              >
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="shrink-0 mt-0.5"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                {anomaly}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
