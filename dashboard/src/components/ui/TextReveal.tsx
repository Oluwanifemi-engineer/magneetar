'use client';

import { useEffect, useState } from 'react';

/**
 * Text that reveals word-by-word with a staggered fade-up.
 * Uses CSS animation triggered by a class toggle — no IntersectionObserver needed.
 * Always visible after mount with a small delay for the animation.
 */
export function TextReveal({
  text,
  className = '',
  delay = 200,
  staggerDelay = 60,
  as: Tag = 'span',
}: {
  text: string;
  className?: string;
  delay?: number;
  staggerDelay?: number;
  as?: 'span' | 'p' | 'h1' | 'h2' | 'h3';
}) {
  const [started, setStarted] = useState(false);

  useEffect(() => {
    // Small delay to ensure DOM is painted, then trigger animation
    const timer = setTimeout(() => setStarted(true), 50);
    return () => clearTimeout(timer);
  }, []);

  const words = text.split(' ');

  return (
    <div className={`overflow-hidden ${className}`}>
      <Tag className="flex flex-wrap">
        {words.map((word, i) => (
          <span
            key={i}
            className="inline-block mr-[0.3em]"
            style={{
              opacity: started ? 1 : 0,
              transform: started ? 'translateY(0)' : 'translateY(100%)',
              transition: `opacity 0.5s cubic-bezier(0.16, 1, 0.3, 1) ${delay + i * staggerDelay}ms, transform 0.5s cubic-bezier(0.16, 1, 0.3, 1) ${delay + i * staggerDelay}ms`,
            }}
          >
            {word}
          </span>
        ))}
      </Tag>
    </div>
  );
}
