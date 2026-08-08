'use client';

import { cn } from '@/lib/utils';

/**
 * Reusable skeleton loader — animated placeholder blocks that match the
 * dashboard's dark theme. Use these instead of "Loading…" text to give
 * users a visual sense of the content that's about to appear.
 *
 * Compose with <SkeletonLine>, <SkeletonCircle>, and <SkeletonCard> for
 * different shapes, or use the pre-built panel skeletons below.
 */

export function SkeletonLine({
  className,
  width,
  height = 'h-3',
}: {
  className?: string;
  width?: string;
  height?: string;
}) {
  return (
    <div
      className={cn(
        'rounded-md bg-mag-surface/60 animate-pulse',
        height,
        width,
        className
      )}
    />
  );
}

export function SkeletonCircle({
  className,
  size = 'w-8 h-8',
}: {
  className?: string;
  size?: string;
}) {
  return (
    <div
      className={cn(
        'rounded-full bg-mag-surface/60 animate-pulse',
        size,
        className
      )}
    />
  );
}

export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'rounded-xl border border-mag-border/20 bg-mag-surface/20 p-4 space-y-3',
        className
      )}
    >
      <SkeletonLine width="w-1/3" height="h-3" />
      <SkeletonLine width="w-full" height="h-3" />
      <SkeletonLine width="w-2/3" height="h-3" />
    </div>
  );
}

/** Sentinel panel skeleton — threat assessment + device info grid */
export function SentinelSkeleton() {
  return (
    <div className="p-4 space-y-4 animate-fade-in">
      {/* Threat assessment card */}
      <div className="bg-mag-surface/40 border border-mag-border/40 rounded-xl p-4 space-y-3">
        <SkeletonLine width="w-28" height="h-3" />
        <div className="flex items-center justify-between">
          <SkeletonLine width="w-16" height="h-7" />
          <SkeletonLine width="w-14" height="h-5" />
        </div>
        <SkeletonLine width="w-full" height="h-2" />
      </div>
      {/* Device info grid */}
      <div className="grid grid-cols-2 gap-3">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-mag-surface/30 border border-mag-border/30 rounded-lg p-3 space-y-1.5">
            <SkeletonLine width="w-12" height="h-2" />
            <SkeletonLine width="w-10" height="h-4" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Command panel skeleton — action buttons + history list */
export function CommandSkeleton() {
  return (
    <div className="p-4 space-y-4 animate-fade-in">
      <SkeletonLine width="w-24" height="h-3" />
      <div className="grid grid-cols-4 gap-2">
        {[...Array(8)].map((_, i) => (
          <div key={i} className="rounded-xl border border-mag-border/20 bg-mag-surface/20 p-3 flex flex-col items-center gap-2">
            <SkeletonCircle size="w-8 h-8" />
            <SkeletonLine width="w-10" height="h-2" />
          </div>
        ))}
      </div>
      <SkeletonLine width="w-28" height="h-3" />
      <div className="space-y-2">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="flex items-center gap-3 py-2 px-2 rounded-lg bg-mag-surface/20 border border-mag-border/20">
            <SkeletonCircle size="w-2 h-2" />
            <div className="flex-1 space-y-1">
              <SkeletonLine width="w-20" height="h-3" />
              <SkeletonLine width="w-14" height="h-2" />
            </div>
            <SkeletonLine width="w-12" height="h-4" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Media gallery skeleton — grid of media placeholders */
export function MediaSkeleton() {
  return (
    <div className="p-4 space-y-4 animate-fade-in">
      <div className="flex items-center gap-1.5">
        <SkeletonCircle size="w-3 h-3" />
        <SkeletonLine width="w-28" height="h-3" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="rounded-xl border border-mag-border/20 bg-mag-surface/20 p-3 space-y-2">
            <SkeletonLine width="w-full" height="h-16" className="rounded-lg" />
            <SkeletonLine width="w-16" height="h-3" />
            <SkeletonLine width="w-20" height="h-2" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Guardian panel skeleton */
export function GuardianSkeleton() {
  return (
    <div className="p-4 space-y-4 animate-fade-in">
      <SkeletonLine width="w-32" height="h-3" />
      <div className="bg-mag-surface/40 border border-mag-border/40 rounded-xl p-4 space-y-3">
        <SkeletonLine width="w-36" height="h-3" />
        <SkeletonLine width="w-full" height="h-8" />
      </div>
      <div className="bg-mag-surface/40 border border-mag-border/40 rounded-xl p-4 space-y-3">
        <SkeletonLine width="w-28" height="h-3" />
        <div className="flex items-center justify-between">
          <SkeletonLine width="w-48" height="h-3" />
          <SkeletonLine width="w-10" height="h-5" className="rounded-full" />
        </div>
      </div>
    </div>
  );
}

/** Evidence panel skeleton */
export function EvidenceSkeleton() {
  return (
    <div className="p-4 space-y-4 animate-fade-in">
      <SkeletonLine width="w-32" height="h-3" />
      <div className="bg-mag-surface/40 border border-mag-border/40 rounded-xl p-4 space-y-3">
        <div className="grid grid-cols-2 gap-2">
          <div className="space-y-1">
            <SkeletonLine width="w-14" height="h-2" />
            <SkeletonLine width="w-20" height="h-4" />
          </div>
          <div className="space-y-1">
            <SkeletonLine width="w-12" height="h-2" />
            <SkeletonLine width="w-16" height="h-4" />
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="bg-mag-bg/40 border border-mag-border/30 rounded-lg p-2 text-center space-y-1">
              <SkeletonLine width="w-8" height="h-5" className="mx-auto" />
              <SkeletonLine width="w-12" height="h-2" className="mx-auto" />
            </div>
          ))}
        </div>
      </div>
      <SkeletonLine width="w-full" height="h-10" className="rounded-xl" />
    </div>
  );
}

/** Error panel skeleton */
export function ErrorSkeleton() {
  return (
    <div className="p-4 space-y-4 animate-fade-in">
      <div className="flex items-center justify-between">
        <SkeletonLine width="w-24" height="h-4" />
        <SkeletonLine width="w-14" height="h-5" />
      </div>
      <SkeletonLine width="w-28" height="h-6" />
      <div className="space-y-2">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="border border-mag-border/20 bg-mag-surface/20 rounded-lg p-3 space-y-2">
            <div className="flex items-center gap-2">
              <SkeletonCircle size="w-3.5 h-3.5" />
              <SkeletonLine width="w-12" height="h-4" />
              <SkeletonLine width="w-32" height="h-3" />
            </div>
            <SkeletonLine width="w-full" height="h-3" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Sidebar device list skeleton — shown while initial data loads */
export function SidebarSkeleton() {
  return (
    <div className="space-y-0 animate-fade-in">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="px-4 py-2.5 border-b border-mag-border/15 space-y-1.5">
          <div className="flex items-center justify-between">
            <SkeletonLine width="w-28" height="h-3.5" />
            <SkeletonCircle size="w-2 h-2" />
          </div>
          <SkeletonLine width="w-20" height="h-2" />
          <div className="flex items-center gap-1.5">
            <SkeletonCircle size="w-1.5 h-1.5" />
            <SkeletonLine width="w-14" height="h-2" />
          </div>
          <div className="flex items-center gap-1.5">
            <SkeletonLine width="w-10" height="h-3" />
            <SkeletonLine width="w-8" height="h-2" />
            <SkeletonLine width="w-full" height="h-1" className="rounded-full" />
          </div>
        </div>
      ))}
    </div>
  );
}
