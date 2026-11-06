"use client";

import { useEffect, useRef, useState } from "react";
import type { GearInk, HeroGear as HeroGearDrawing } from "@/components/hero-gear-renderer";

// The drawing's ink in each theme: a cool slate a little off the page's background, the outlines a
// shade stronger than the folds, so the gear reads as a faint technical drawing behind the text.
const INK: Record<"light" | "dark", GearInk> = {
  light: { fold: "#d3dae2", outline: "#c2ccd7" },
  dark: { fold: "#3e444b", outline: "#4a525b" },
};
// The backdrop is decoration: its drawing buffer stops at 1.5 device pixels per CSS pixel.
const MAX_PIXEL_RATIO = 1.5;

function currentInk() {
  return INK[document.documentElement.classList.contains("dark") ? "dark" : "light"];
}

/**
 * The hero's backdrop: the planetary gear, large, faint and slowly turning behind the hero's text
 * (`hero-gear-renderer.ts` draws it, and places it), fading out above the agents and toward the text
 * (`.hero-backdrop` in globals.css). Decoration only: hidden from assistive technology, never under
 * the pointer or in the tab order. It loads once the page has loaded and the browser is idle, so the
 * hero's text paints first, and not at all for a visitor saving data; it fades in once drawn, turns
 * only while on screen in a visible tab, and holds still for anyone who asks for less motion.
 */
export function HeroGear() {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [drawn, setDrawn] = useState(false);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    if (!host || !canvas) return;
    const connection = (navigator as Navigator & { connection?: { saveData?: boolean } }).connection;
    if (connection?.saveData) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
    let disposed = false;
    let gear: HeroGearDrawing | null = null;
    let onScreen = false;
    let frame = 0;
    let last = 0;

    const tick = (now: number) => {
      frame = requestAnimationFrame(tick);
      const seconds = last ? Math.min(now - last, 100) / 1000 : 0;
      last = now;
      gear?.advance(seconds);
      gear?.render();
    };
    // It turns only while it can be seen: on screen, in a visible tab, and for anyone who has not
    // asked for less motion. Otherwise it holds its last frame.
    const sync = () => {
      const run = Boolean(gear) && onScreen && document.visibilityState === "visible" && !reduced.matches;
      if (run && !frame) {
        last = 0;
        frame = requestAnimationFrame(tick);
      } else if (!run && frame) {
        cancelAnimationFrame(frame);
        frame = 0;
      }
    };
    const seen = new IntersectionObserver(([entry]) => {
      onScreen = Boolean(entry?.isIntersecting);
      sync();
    });
    seen.observe(host);
    document.addEventListener("visibilitychange", sync);
    reduced.addEventListener("change", sync);
    // The site follows the system's theme (layout.tsx sets `.dark`): redraw in that theme's ink.
    const theme = new MutationObserver(() => {
      gear?.setInk(currentInk());
      if (!frame) gear?.render();
    });
    theme.observe(document.documentElement, { attributeFilter: ["class"], attributes: true });

    const load = async () => {
      const { createHeroGear } = await import("@/components/hero-gear-renderer");
      if (disposed) return;
      const created = await createHeroGear({ canvas, host, ink: currentInk(), maxPixelRatio: MAX_PIXEL_RATIO });
      if (disposed) {
        created.dispose();
        return;
      }
      gear = created;
      gear.render();
      setDrawn(true);
      sync();
    };
    // After the page has loaded and the browser is idle, so the hero's text paints first. Without
    // WebGL, or should the model not load, the hero simply has no backdrop.
    const idleCallbacks = typeof window.requestIdleCallback === "function";
    let idle = 0;
    const whenIdle = () => {
      const start = () => void load().catch(() => {});
      idle = idleCallbacks ? window.requestIdleCallback(start, { timeout: 2000 }) : window.setTimeout(start, 200);
    };
    if (document.readyState === "complete") whenIdle();
    else window.addEventListener("load", whenIdle, { once: true });

    return () => {
      disposed = true;
      window.removeEventListener("load", whenIdle);
      if (idleCallbacks) window.cancelIdleCallback(idle);
      else window.clearTimeout(idle);
      cancelAnimationFrame(frame);
      seen.disconnect();
      theme.disconnect();
      document.removeEventListener("visibilitychange", sync);
      reduced.removeEventListener("change", sync);
      gear?.dispose();
    };
  }, []);

  return (
    <div
      ref={hostRef}
      aria-hidden="true"
      className="hero-backdrop pointer-events-none absolute inset-0 -z-10 select-none overflow-hidden"
    >
      <canvas
        ref={canvasRef}
        className={`absolute inset-0 size-full transition-opacity duration-[1600ms] ease-out motion-reduce:transition-none ${drawn ? "opacity-100" : "opacity-0"}`}
      />
    </div>
  );
}
