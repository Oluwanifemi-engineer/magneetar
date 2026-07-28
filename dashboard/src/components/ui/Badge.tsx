'use client';

import { cn } from '@/lib/utils';

interface BadgeProps {
  variant: 'online' | 'offline' | 'danger' | 'info' | 'warning';
  children: React.ReactNode;
  className?: string;
}

export function Badge({ variant, children, className }: BadgeProps) {
  const variants = {
    online: 'mag-badge bg-mag-accent/10 text-mag-accent border border-mag-accent/25',
    offline: 'mag-badge bg-mag-warning/10 text-mag-warning border border-mag-warning/25',
    danger: 'mag-badge bg-mag-danger/10 text-mag-danger border border-mag-danger/25',
    info: 'mag-badge bg-mag-secondary/10 text-mag-secondary border border-mag-secondary/25',
    warning: 'mag-badge bg-mag-warning/10 text-mag-warning border border-mag-warning/25',
  };

  return (
    <span className={cn(variants[variant], className)}>
      {children}
    </span>
  );
}
