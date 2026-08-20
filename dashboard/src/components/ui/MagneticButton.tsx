'use client';

import { useRef, type ReactNode } from 'react';

/**
 * Button that subtly pulls toward the cursor on hover.
 * Premium micro-interaction seen on Linear, Stripe checkout.
 */
export function MagneticButton({ children, className = '', strength = 0.3, ...props }: {
  children: ReactNode;
  className?: string;
  strength?: number;
  [key: string]: unknown;
}) {
  const ref = useRef<HTMLDivElement>(null);

  const onMove = (e: React.MouseEvent) => {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const x = e.clientX - rect.left - rect.width / 2;
    const y = e.clientY - rect.top - rect.height / 2;
    el.style.transform = `translate(${x * strength}px, ${y * strength}px)`;
  };

  const onLeave = () => {
    if (ref.current) {
      ref.current.style.transform = 'translate(0, 0)';
    }
  };

  return (
    <div
      ref={ref}
      onMouseMove={onMove}
      onMouseLeave={onLeave}
      className={`inline-block transition-transform duration-200 ease-out ${className}`}
      style={{ willChange: 'transform' }}
      {...props}
    >
      {children}
    </div>
  );
}
