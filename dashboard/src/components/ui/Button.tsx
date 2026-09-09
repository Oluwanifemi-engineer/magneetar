'use client';

import { cn } from '@/lib/utils';
import { ReactNode, ButtonHTMLAttributes } from 'react';
import { Loader2 } from 'lucide-react';

/**
 * Button Component
 *
 * Design pattern: Polymorphic Component
 * - Variants for different actions
 * - Loading state with spinner
 * - Icons support
 * - Sizes for different contexts
 *
 * Usage:
 * ```
 * <Button variant="primary" size="lg" loading={isLoading}>
 *   Save Changes
 * </Button>
 * ```
 */

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'link';
  size?: 'sm' | 'md' | 'lg';
  loading?: boolean;
  icon?: ReactNode;
  iconPosition?: 'left' | 'right';
  fullWidth?: boolean;
}

function Button({
  children,
  variant = 'primary',
  size = 'md',
  loading = false,
  icon,
  iconPosition = 'left',
  fullWidth = false,
  className,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        // Base styles
        'inline-flex items-center justify-center font-medium rounded-lg transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-gray-900',
        // Variants
        {
          'bg-blue-600 text-white hover:bg-blue-700 focus:ring-blue-500 shadow-lg shadow-blue-500/25': variant === 'primary',
          'bg-gray-700 text-gray-200 hover:bg-gray-600 focus:ring-gray-500': variant === 'secondary',
          'bg-red-600 text-white hover:bg-red-700 focus:ring-red-500 shadow-lg shadow-red-500/25': variant === 'danger',
          'bg-transparent text-mag-text-muted hover:bg-mag-surface-raised focus:ring-mag-border transition-colors': variant === 'ghost',
          'bg-transparent text-blue-400 hover:text-blue-300 underline': variant === 'link',
        },
        // Sizes
        {
          'text-xs px-3 py-1.5 gap-1.5': size === 'sm',
          'text-sm px-4 py-2 gap-2': size === 'md',
          'text-base px-6 py-3 gap-2.5': size === 'lg',
        },
        // States
        {
          'opacity-50 cursor-not-allowed': disabled || loading,
          'w-full': fullWidth,
        },
        className
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <Loader2 className="w-4 h-4 animate-spin" />}
      {!loading && icon && iconPosition === 'left' && icon}
      {children}
      {!loading && icon && iconPosition === 'right' && icon}
    </button>
  );
}

export { Button };
