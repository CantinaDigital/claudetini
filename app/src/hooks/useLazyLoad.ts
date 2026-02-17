/**
 * Lazy loading hook using Intersection Observer
 * Phase 3: Load sections as they scroll into view
 */

import { useEffect, useRef, useState } from 'react';

interface UseLazyLoadOptions {
  rootMargin?: string;
  threshold?: number;
}

export function useLazyLoad(options: UseLazyLoadOptions = {}) {
  const [isVisible, setIsVisible] = useState(false);
  const elementRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = elementRef.current;
    if (!element) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
          // Once visible, stop observing (one-time trigger)
          observer.disconnect();
        }
      },
      {
        rootMargin: options.rootMargin || '100px', // Start loading 100px before visible
        threshold: options.threshold || 0.1,
      }
    );

    observer.observe(element);

    return () => {
      observer.disconnect();
    };
  }, [options.rootMargin, options.threshold]);

  return { isVisible, elementRef };
}
