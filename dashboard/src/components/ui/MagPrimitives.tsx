'use client';

import { cn } from '@/lib/utils';
import { ReactNode, ButtonHTMLAttributes, InputHTMLAttributes, SelectHTMLAttributes, forwardRef } from 'react';
import { Loader2 } from 'lucide-react';

/**
 * MagButton — the single premium button primitive for the dashboard.
 *
 * Design language: emerald-first (mag.primary), quiet chrome, honest states.
 * Replaces ad-hoc buttons and aligns the legacy Button.tsx to the mag system.
 *
 * States: idle / hover / active / disabled / loading / success / error.
 */
type MagButtonVariant = 'primary' | 'ghost' | 'danger' | 'subtle';
type MagButtonSize = 'sm' | 'md' | 'lg';

interface MagButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: MagButtonVariant;
  size?: MagButtonSize;
  loading?: boolean;
  success?: boolean;
  error?: boolean;
  icon?: ReactNode;
  iconPosition?: 'left' | 'right';
  startIcon?: ReactNode;
  endIcon?: ReactNode;
  fullWidth?: boolean;
}

export const MagButton = forwardRef<HTMLButtonElement, MagButtonProps>(
  (
    {
      children,
      variant = 'primary',
      size = 'md',
      loading = false,
      success = false,
      error = false,
      icon,
      iconPosition = 'left',
      startIcon,
      endIcon,
      fullWidth = false,
      className,
      disabled,
      ...props
    },
    ref,
  ) => {
    const base =
      'inline-flex items-center justify-center font-medium rounded-lg transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-mag-bg';

    const variants: Record<MagButtonVariant, string> = {
      primary:
        'bg-emerald-500 text-white shadow-glow-md hover:bg-emerald-400 hover:shadow-glow-lg hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed',
      ghost:
        'bg-transparent text-mag-text-dim border border-mag-border hover:bg-surface-hover hover:border-mag-border/50 hover:text-mag-text active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed',
      danger:
        'bg-red-500 text-white shadow-glow-md hover:bg-red-400 hover:shadow-glow-lg hover:-translate-y-0.5 active:translate-y-0 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed',
      subtle:
        'bg-emerald-500/15 text-emerald-400 border border-emerald-500/20 hover:bg-emerald-500/25 hover:text-emerald-300 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed',
    };

    const sizes: Record<MagButtonSize, string> = {
      sm: 'text-[10px] px-3 py-1.5 gap-1.5 font-bold uppercase tracking-wider',
      md: 'text-[11px] px-4 py-2 gap-2 font-bold uppercase tracking-wider',
      lg: 'text-[12px] px-5 py-2.5 gap-2.5 font-bold uppercase tracking-wider',
    };

    const state = cn(
      loading && 'opacity-70 cursor-wait',
      success && 'bg-emerald-500/20 text-emerald-400 border-emerald-500/20',
      error && 'bg-red-500/20 text-red-400 border-red-500/20',
    );

    const leftIcon = startIcon ?? (icon && iconPosition === 'left' && icon);
    const rightIcon = endIcon ?? (icon && iconPosition === 'right' && icon);

    return (
      <button
        ref={ref}
        className={cn(base, variants[variant], sizes[size], state, fullWidth && 'w-full', className)}
        disabled={disabled || loading}
        {...props}
      >
        {loading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
        {!loading && leftIcon}
        {children}
        {!loading && rightIcon}
      </button>
    );
  },
);

MagButton.displayName = 'MagButton';

/**
 * MagInput — consistent dashboard input chrome.
 *
 * Uses .mag-field (+ focused variant) so every dashboard form shares one surface.
 * Carries idle / focus / disabled / error states.
 */
interface MagInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  /** Red styling + inline message. Pass a string to show a specific message. */
  error?: boolean | string;
  hint?: string;
  variant?: 'default' | 'danger';
}

export const MagInput = forwardRef<HTMLInputElement, MagInputProps>(
  ({ label, error, hint, variant, className, id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');
    return (
      <div className="space-y-1.5">
        {label && (
          <label htmlFor={inputId} className="mag-field-label">
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            'mag-field',
            variant === 'danger' && !error && 'border-red-500/40 bg-red-500/5 focus:border-red-500/60',
            error && 'border-red-500/60 bg-red-500/10 focus:border-red-500/80',
            className,
          )}
          {...props}
        />
        {hint && !error && (
          <p className="text-[9px] font-mono text-mag-text-muted/60 leading-relaxed">{hint}</p>
        )}
        {error && typeof error === 'string' && (
          <p className="text-[9px] font-mono text-red-400/80 leading-relaxed">{error}</p>
        )}
      </div>
    );
  },
);

MagInput.displayName = 'MagInput';

/**
 * MagSelect — consistent dashboard select chrome.
 */
interface MagSelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: boolean;
  options: Array<{ value: string; label: string; disabled?: boolean }>;
}

export const MagSelect = forwardRef<HTMLSelectElement, MagSelectProps>(
  ({ label, error, options, className, id, ...props }, ref) => {
    const selectId = id || label?.toLowerCase().replace(/\s+/g, '-');
    return (
      <div className="space-y-1.5">
        {label && (
          <label htmlFor={selectId} className="mag-field-label">
            {label}
          </label>
        )}
        <select
          ref={ref}
          id={selectId}
          className={cn(
            'mag-field appearance-none cursor-pointer',
            'bg-[url("data:image/svg+xml,%3Csvg xmlns=\\"http://www.w3.org/2000/svg\\" viewBox=\\"0 0 20 20\\" fill=\\"currentColor\\"\\>%3Cpath fill-rule=\\"evenodd\\" d=\\"M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z\\" clip-rule=\\"evenodd\\"/%3E%3C/svg%3E")] bg-[length:16px] bg-[right_6px_center] bg-no-repeat',
            error && 'border-red-500/40 bg-red-500/5',
            className,
          )}
          {...props}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value} disabled={opt.disabled}>
              {opt.label}
            </option>
          ))}
        </select>
        {error && <p className="text-[9px] font-mono text-red-400/80 leading-relaxed">{error}</p>}
      </div>
    );
  },
);

MagSelect.displayName = 'MagSelect';

/**
 * MagStatusPill — a small status badge consistent with mag-badge.
 *
 * Used for Secure / Elevated / High Risk / Stolen, Safe / Restricted,
 * Online / Offline, etc. Color = state only.
 */
type MagStatusVariant = 'secure' | 'elevated' | 'danger' | 'muted';

interface MagStatusPillProps {
  variant: MagStatusVariant;
  children?: ReactNode;
  label?: ReactNode;
  className?: string;
  title?: string;
  onClick?: React.MouseEventHandler<HTMLSpanElement>;
  disabled?: boolean;
  /**
   * Optional accessible label for toggle-style pills.
   * When set, the pill renders as a <button> with aria-pressed so it can be
   * targeted by getByLabelText in tests and used with a screen reader.
   */
  ariaLabel?: string;
  ariaPressed?: boolean;
}

export function MagStatusPill({
  variant,
  children,
  label,
  className,
  title,
  onClick,
  disabled = false,
  ariaLabel,
  ariaPressed,
}: MagStatusPillProps) {
  const variants = {
    secure: 'mag-badge-secure',
    elevated: 'mag-badge-elevated',
    danger: 'mag-badge-danger',
    muted: 'mag-badge-muted',
  };
  const content = children ?? label ?? null;

  // Toggle pills should be real buttons for accessibility + testability.
  if (ariaLabel) {
    return (
      <button
        type="button"
        className={cn(
          'mag-badge inline-flex items-center',
          variants[variant],
          disabled && 'opacity-50 cursor-not-allowed',
          !disabled && onClick && 'cursor-pointer',
          className,
        )}
        disabled={disabled}
        onClick={disabled ? undefined : onClick}
        aria-label={ariaLabel}
        aria-pressed={ariaPressed != null ? ariaPressed : undefined}
        title={title}
      >
        {content}
      </button>
    );
  }

  return (
    <span
      className={cn(
        'mag-badge',
        variants[variant],
        disabled && 'opacity-50 cursor-not-allowed',
        onClick && !disabled && 'cursor-pointer',
        className,
      )}
      title={title}
      onClick={disabled ? undefined : onClick}
    >
      {content}
    </span>
  );
}

/**
 * MagPanel — consistent dashboard panel chrome.
 *
 * Single source of truth for the bordered, glassy card surface used across
 * panels, settings, and device-detail sections.
 */
export const MagPanel = function MagPanel({
  children,
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('mag-panel', className)} {...props}>
      {children}
    </div>
  );
};

/**
 * MagRow — consistent row chrome with alignment.
 */
export const MagRow = function MagRow({
  align = 'left',
  children,
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { align?: 'left' | 'between' | 'center' }) {
  const alignClass = align === 'between' ? 'justify-between' : align === 'center' ? 'justify-center' : 'justify-start';
  return (
    <div className={cn('mag-row', alignClass, className)} {...props}>
      {children}
    </div>
  );
};

/**
 * MagEmpty — consistent empty-state chrome.
 */
export const MagEmpty = function MagEmpty({
  children,
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('mag-empty', className)} {...props}>
      {children}
    </div>
  );
};
