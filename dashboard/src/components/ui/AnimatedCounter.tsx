'use client';

import { useEffect, useRef, useState } from 'react';
import { useScrollReveal } from '@/hooks/useScrollReveal';

interface AnimatedCounterProps {
  value: number;
  suffix?: string;
  prefix?: string;
  duration?: number;
  className?: string;
}

/**
 * Renders a numeric claim. The number is ALWAYS its true value — it starts
 * there on first paint (SSR included) and never counts up from 0. A count-up
 * animation made screenshots and cached HTML show wrong numbers ("SHA-0-bit",
 * "349 tests" mid-flight on a page that promises every claim is verifiable),
 * so the only animation left is a fade-in that never changes the digits.
 */
export function AnimatedCounter({
  value,
  suffix = '',
  prefix = '',
  className = '',
}: AnimatedCounterProps) {
  const { ref, isVisible } = useScrollReveal({ threshold: 0.5 });
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (isVisible && !shown) {
      setShown(true);
    }
  }, [isVisible, shown]);

  return (
    <span
      ref={ref}
      className={`tabular-nums transition-opacity duration-700 ${
        shown ? 'opacity-100' : 'opacity-0'
      } ${className}`}
    >
      {prefix}
      {value.toLocaleString()}
      {suffix}
    </span>
  );
}

// Stats section with animated counters
interface StatItem {
  value: number;
  suffix?: string;
  prefix?: string;
  label: string;
}

interface AnimatedStatsProps {
  stats: StatItem[];
  className?: string;
}

export function AnimatedStats({ stats, className = '' }: AnimatedStatsProps) {
  return (
    <div className={`grid grid-cols-2 sm:grid-cols-4 gap-6 ${className}`}>
      {stats.map((stat, index) => (
        <div key={stat.label} className="text-center">
          <AnimatedCounter
            value={stat.value}
            suffix={stat.suffix}
            prefix={stat.prefix}
            className="text-3xl sm:text-4xl font-extrabold font-mono text-white"
          />
          <div className="text-[10px] font-mono text-white/50 uppercase tracking-wider mt-2 font-semibold">
            {stat.label}
          </div>
        </div>
      ))}
    </div>
  );
}
