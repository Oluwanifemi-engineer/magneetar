'use client';

import { useState, useRef, useCallback, useEffect } from 'react';
import { cn } from '@/lib/utils';

/**
 * BottomSheet — Apple Find My / Google Maps pattern.
 *
 * Three detents:
 *   peek  — device name + status (120px)
 *   half  — device details + quick actions (~45%)
 *   full  — complete panel (~92%)
 *
 * User drags the handle up/down. Snap points with spring physics.
 * Map stays visible behind the sheet at peek/half.
 */

const DETENTS = {
  peek: 120,   // px — just device name + status
  half: 0.45,  // fraction of viewport
  full: 0.92,  // fraction of viewport
} as const;

interface BottomSheetProps {
  children: React.ReactNode;
  peekContent?: React.ReactNode;
  onStateChange?: (state: 'peek' | 'half' | 'full' | 'hidden') => void;
  className?: string;
  initial?: 'peek' | 'half' | 'full' | 'hidden';
}

export function BottomSheet({
  children,
  peekContent,
  onStateChange,
  className,
  initial = 'peek',
}: BottomSheetProps) {
  const [state, setState] = useState<'peek' | 'half' | 'full' | 'hidden'>(initial);
  const [dragY, setDragY] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const startY = useRef(0);
  const startState = useRef(state);
  const sheetRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  const getDetentHeight = useCallback((s: string) => {
    if (typeof window === 'undefined') return 120;
    if (s === 'hidden') return 0;
    if (s === 'peek') return DETENTS.peek;
    if (s === 'half') return window.innerHeight * DETENTS.half;
    if (s === 'full') return window.innerHeight * DETENTS.full;
    return DETENTS.peek;
  }, []);

  const height = getDetentHeight(state);

  const snapToNearest = useCallback((currentY: number, velocity: number) => {
    const vh = typeof window !== 'undefined' ? window.innerHeight : 800;
    const positions = [
      { state: 'hidden' as const, y: 0 },
      { state: 'peek' as const, y: DETENTS.peek },
      { state: 'half' as const, y: vh * DETENTS.half },
      { state: 'full' as const, y: vh * DETENTS.full },
    ];

    // If flicking fast, snap to next/prev
    if (Math.abs(velocity) > 500) {
      const direction = velocity > 0 ? -1 : 1; // negative velocity = flicking up = bigger detent
      const currentIdx = positions.findIndex(p => p.state === startState.current);
      const nextIdx = Math.max(0, Math.min(positions.length - 1, currentIdx + direction));
      setState(positions[nextIdx].state);
      onStateChange?.(positions[nextIdx].state);
      return;
    }

    // Otherwise snap to nearest
    let closest = positions[0];
    let minDist = Infinity;
    for (const pos of positions) {
      const dist = Math.abs(currentY - pos.y);
      if (dist < minDist) {
        minDist = dist;
        closest = pos;
      }
    }
    setState(closest.state);
    onStateChange?.(closest.state);
  }, [onStateChange]);

  // Touch handlers
  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    startY.current = e.touches[0].clientY;
    startState.current = state;
    setIsDragging(true);
    setDragY(0);
  }, [state]);

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (!isDragging) return;
    const delta = startY.current - e.touches[0].clientY;
    const baseHeight = getDetentHeight(startState.current);
    const newHeight = Math.max(0, Math.min(
      typeof window !== 'undefined' ? window.innerHeight * 0.95 : 700,
      baseHeight + delta
    ));
    setDragY(newHeight - baseHeight);
  }, [isDragging, getDetentHeight]);

  const handleTouchEnd = useCallback((e: React.TouchEvent) => {
    if (!isDragging) return;
    setIsDragging(false);

    const baseHeight = getDetentHeight(startState.current);
    const finalHeight = baseHeight + dragY;

    // Calculate velocity from last touch
    const touch = e.changedTouches[0];
    const velocity = 0; // simplified — snap based on position

    snapToNearest(finalHeight, velocity);
    setDragY(0);
  }, [isDragging, dragY, getDetentHeight, snapToNearest]);

  // Mouse handlers for desktop testing
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    startY.current = e.clientY;
    startState.current = state;
    setIsDragging(true);
    setDragY(0);
  }, [state]);

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      const delta = startY.current - e.clientY;
      const baseHeight = getDetentHeight(startState.current);
      const newHeight = Math.max(0, Math.min(
        window.innerHeight * 0.95,
        baseHeight + delta
      ));
      setDragY(newHeight - baseHeight);
    };

    const handleMouseUp = (e: MouseEvent) => {
      setIsDragging(false);
      const baseHeight = getDetentHeight(startState.current);
      const finalHeight = baseHeight + dragY;
      snapToNearest(finalHeight, 0);
      setDragY(0);
    };

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, dragY, getDetentHeight, snapToNearest]);

  const currentHeight = height + (isDragging ? dragY : 0);

  // Handle bar indicator dots
  const indicatorForState = state === 'peek' ? 0 : state === 'half' ? 1 : 2;

  return (
    <div
      ref={sheetRef}
      className={cn(
        'fixed left-0 right-0 z-[2000] transition-none',
        'md:hidden', // Mobile only — desktop uses side panels
        isDragging ? '' : 'transition-[height] duration-300 ease-out',
        className,
      )}
      style={{
        bottom: 0,
        height: state === 'hidden' ? 0 : currentHeight,
        overflow: 'hidden',
      }}
    >
      {/* Backdrop blur area */}
      <div className="absolute inset-0 bg-mag-bg/95 backdrop-blur-xl rounded-t-3xl" />

      {/* Content */}
      <div ref={contentRef} className="relative h-full flex flex-col">
        {/* Drag handle + peek content */}
        <div
          className="relative shrink-0 cursor-grab active:cursor-grabbing"
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
          onMouseDown={handleMouseDown}
        >
          {/* Handle bar */}
          <div className="flex justify-center pt-2.5 pb-1">
            <div className="w-10 h-1 rounded-full bg-mag-border" />
          </div>

          {/* Detent indicator dots */}
          <div className="flex justify-center gap-1.5 pb-2">
            {[0, 1, 2].map(i => (
              <div
                key={i}
                className={cn(
                  'w-1 h-1 rounded-full transition-all duration-200',
                  i <= indicatorForState ? 'bg-emerald-500' : 'bg-mag-border'
                )}
              />
            ))}
          </div>

          {/* Peek content */}
          {peekContent && state === 'peek' && (
            <div className="px-5 pb-3">
              {peekContent}
            </div>
          )}

          {/* Tap to expand indicator */}
          {state === 'peek' && (
            <button
              onClick={() => { setState('half'); onStateChange?.('half'); }}
              className="absolute bottom-1 left-1/2 -translate-x-1/2 text-[8px] font-mono text-mag-text-muted uppercase tracking-widest"
            >
              ↑ Swipe up for more
            </button>
          )}
        </div>

        {/* Scrollable content area (half/full states) */}
        {(state === 'half' || state === 'full') && (
          <div className="flex-1 overflow-y-auto overscroll-contain px-5 pb-safe">
            {state === 'half' && (
              <button
                onClick={() => { setState('peek'); onStateChange?.('peek'); }}
                className="w-full text-center py-2 text-[8px] font-mono text-mag-text-muted uppercase tracking-widest"
              >
                ↓ Collapse
              </button>
            )}
            {children}
          </div>
        )}
      </div>
    </div>
  );
}
