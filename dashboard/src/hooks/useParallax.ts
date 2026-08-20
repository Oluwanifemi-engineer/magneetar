'use client';

import { useEffect, useState } from 'react';

/**
 * Returns a parallax Y offset based on scroll position.
 * speed: 0 = no movement, 1 = full scroll speed, negative = reverse direction
 */
export function useParallax(speed: number = 0.3) {
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    let raf: number;
    let ticking = false;

    const onScroll = () => {
      if (!ticking) {
        raf = requestAnimationFrame(() => {
          setOffset(window.scrollY * speed);
          ticking = false;
        });
        ticking = true;
      }
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      window.removeEventListener('scroll', onScroll);
      cancelAnimationFrame(raf);
    };
  }, [speed]);

  return offset;
}
