"use client";

import { useEffect, useRef, useState } from "react";
import type { ModelEmbedView } from "@/components/docs/model-embed-renderer";

export type ModelEmbedProps = {
  /** The GLB, a file of `public/`. */
  src: string;
  /** What the picture shows, for a reader who cannot see it. */
  label: string;
  caption: string;
  clip?: string;
  clipSpeed?: number;
};

/**
 * A model on a page, live: a GLB `cad` exported, drawn with its parts' colours and its motion playing,
 * and turned by dragging. It loads when it scrolls into view (the renderer and three.js with it, so a
 * page that shows none loads neither), plays only while on screen in a visible tab, and holds still
 * for reduced motion. Where WebGL or the file fails, the caption stands alone.
 */
export function ModelEmbed({ src, label, caption, clip, clipSpeed }: ModelEmbedProps) {
  const host = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [state, setState] = useState<"waiting" | "ready" | "failed">("waiting");

  useEffect(() => {
    const hostElement = host.current;
    const canvasElement = canvas.current;
    if (!hostElement || !canvasElement) return;
    let view: ModelEmbedView | null = null;
    let disposed = false;
    let onScreen = false;
    let frame = 0;
    let last = 0;
    const still = window.matchMedia("(prefers-reduced-motion: reduce)");

    const tick = (now: number) => {
      frame = 0;
      if (!view || !onScreen || document.hidden) return;
      view.advance(Math.min((now - last) / 1000, 0.1));
      last = now;
      view.render();
      if (!still.matches) frame = requestAnimationFrame(tick);
    };
    const play = () => {
      if (frame || !view) return;
      last = performance.now();
      frame = requestAnimationFrame(tick);
    };

    const load = async () => {
      try {
        const { createModelEmbed } = await import("@/components/docs/model-embed-renderer");
        const created = await createModelEmbed({ canvas: canvasElement, host: hostElement, url: src, clipName: clip, clipSpeed });
        if (disposed) {
          created.dispose();
          return;
        }
        view = created;
        view.render();
        setState("ready");
        play();
      } catch {
        if (!disposed) setState("failed");
      }
    };

    let started = false;
    const seen = new IntersectionObserver(([entry]) => {
      onScreen = entry.isIntersecting;
      if (onScreen && !started) {
        started = true;
        void load();
      } else if (onScreen) {
        play();
      }
    }, { rootMargin: "200px" });
    seen.observe(hostElement);
    document.addEventListener("visibilitychange", play);
    still.addEventListener("change", play);

    return () => {
      disposed = true;
      seen.disconnect();
      document.removeEventListener("visibilitychange", play);
      still.removeEventListener("change", play);
      if (frame) cancelAnimationFrame(frame);
      view?.dispose();
    };
  }, [src, clip, clipSpeed]);

  return (
    <figure className="mt-6 overflow-hidden rounded-xl border border-border bg-card">
      <div
        ref={host}
        className="relative aspect-[16/9] w-full bg-[radial-gradient(color-mix(in_oklch,var(--muted-foreground)_22%,transparent)_1px,transparent_1px)] [background-size:14px_14px] [background-position:7px_7px]"
      >
        <canvas
          ref={canvas}
          role="img"
          aria-label={label}
          className={`absolute inset-0 size-full cursor-grab touch-pan-y transition-opacity duration-500 active:cursor-grabbing ${state === "ready" ? "opacity-100" : "opacity-0"}`}
        />
        {state === "ready" ? (
          <p className="pointer-events-none absolute right-3 bottom-2 text-label text-muted-foreground">Drag to turn</p>
        ) : null}
      </div>
      <figcaption className="border-t border-border px-3 py-2 text-xs leading-5 text-muted-foreground">{caption}</figcaption>
    </figure>
  );
}
