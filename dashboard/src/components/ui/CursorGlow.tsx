'use client';

import { useEffect, useRef } from 'react';

/**
 * A soft gradient orb that follows the cursor position within its parent.
 * Gives the premium "living background" effect seen on Linear, Stripe, Vercel.
 */
export function CursorGlow({ className = '', color = 'rgba(255,255,255,0.06)', size = 600 }: {
  className?: string;
  color?: string;
  size?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const parent = el.parentElement;
    if (!parent) return;

    let raf: number;
    let targetX = 0;
    let targetY = 0;
    let currentX = 0;
    let currentY = 0;

    const onMove = (e: MouseEvent) => {
      const rect = parent.getBoundingClientRect();
      targetX = e.clientX - rect.left;
      targetY = e.clientY - rect.top;
    };

    const animate = () => {
      // Smooth lerp for buttery motion
      currentX += (targetX - currentX) * 0.08;
      currentY += (targetY - currentY) * 0.08;
      el.style.transform = `translate(${currentX - size / 2}px, ${currentY - size / 2}px)`;
      raf = requestAnimationFrame(animate);
    };

    parent.addEventListener('mousemove', onMove, { passive: true });
    raf = requestAnimationFrame(animate);

    return () => {
      parent.removeEventListener('mousemove', onMove);
      cancelAnimationFrame(raf);
    };
  }, [size]);

  return (
    <div
      ref={ref}
      className={`absolute pointer-events-none z-0 ${className}`}
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        background: `radial-gradient(circle, ${color} 0%, transparent 70%)`,
        willChange: 'transform',
        filter: 'blur(40px)',
      }}
    />
  );
}
