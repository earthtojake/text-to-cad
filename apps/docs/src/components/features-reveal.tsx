"use client";

import { useEffect, useRef, type ReactNode } from "react";

/**
 * The Features grid, whose drawings draw themselves in once, each as its tile first scrolls into
 * view: a tile still below the fold is set `data-draw="pending"` (its strokes hidden) and, entering,
 * `"run"` (app/globals.css animates them back). The server's page has them drawn, so without
 * scripts, for reduced motion, or for a tile already on screen (a link to `#features`) nothing moves.
 */
export function FeaturesReveal({ className, children }: { className?: string; children: ReactNode }) {
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    const list = listRef.current;
    if (!list || !("IntersectionObserver" in window)) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const tiles = Array.from(list.querySelectorAll<HTMLElement>("[data-feature]")).filter(
      (tile) => tile.getBoundingClientRect().top > window.innerHeight,
    );
    if (!tiles.length) return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          (entry.target as HTMLElement).dataset.draw = "run";
          observer.unobserve(entry.target);
        }
      },
      { rootMargin: "0px 0px -15% 0px" },
    );
    for (const tile of tiles) {
      tile.dataset.draw = "pending";
      observer.observe(tile);
    }
    return () => observer.disconnect();
  }, []);

  return (
    <ul ref={listRef} className={className}>
      {children}
    </ul>
  );
}
