'use client';

import { useEffect, useRef, type ReactNode } from 'react';

type Direction = 'up' | 'down' | 'left' | 'right' | 'scale' | 'none';

/**
 * Premium scroll-triggered reveal with directional animation.
 * Supports stagger for child elements.
 */
export function PremiumReveal({
  children,
  className = '',
  direction = 'up',
  delay = 0,
  duration = 700,
  distance = 40,
  stagger = 0,
  once = true,
}: {
  children: ReactNode;
  className?: string;
  direction?: Direction;
  delay?: number;
  duration?: number;
  distance?: number;
  stagger?: number;
  once?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const children = stagger > 0 ? el.children : [el];

    // Set initial state
    Array.from(children).forEach((child) => {
      const htmlEl = child as HTMLElement;
      htmlEl.style.opacity = '0';
      htmlEl.style.transition = `opacity ${duration}ms cubic-bezier(0.16, 1, 0.3, 1), transform ${duration}ms cubic-bezier(0.16, 1, 0.3, 1)`;

      if (direction === 'up') htmlEl.style.transform = `translateY(${distance}px)`;
      else if (direction === 'down') htmlEl.style.transform = `translateY(-${distance}px)`;
      else if (direction === 'left') htmlEl.style.transform = `translateX(${distance}px)`;
      else if (direction === 'right') htmlEl.style.transform = `translateX(-${distance}px)`;
      else if (direction === 'scale') htmlEl.style.transform = 'scale(0.95)';
      else htmlEl.style.transform = 'none';
    });

    if (typeof IntersectionObserver === 'undefined') {
      Array.from(children).forEach((child) => {
        const htmlEl = child as HTMLElement;
        htmlEl.style.opacity = '1';
        htmlEl.style.transform = 'none';
      });
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          Array.from(children).forEach((child, i) => {
            const htmlEl = child as HTMLElement;
            setTimeout(() => {
              htmlEl.style.opacity = '1';
              htmlEl.style.transform = 'none';
            }, delay + i * stagger);
          });
          if (once) observer.disconnect();
        } else if (!once) {
          Array.from(children).forEach((child) => {
            const htmlEl = child as HTMLElement;
            htmlEl.style.opacity = '0';
            if (direction === 'up') htmlEl.style.transform = `translateY(${distance}px)`;
            else if (direction === 'down') htmlEl.style.transform = `translateY(-${distance}px)`;
            else if (direction === 'left') htmlEl.style.transform = `translateX(${distance}px)`;
            else if (direction === 'right') htmlEl.style.transform = `translateX(-${distance}px)`;
            else if (direction === 'scale') htmlEl.style.transform = 'scale(0.95)';
          });
        }
      },
      { threshold: 0.15 }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [direction, delay, duration, distance, stagger, once]);

  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  );
}
