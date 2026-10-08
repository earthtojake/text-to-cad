"use client";

import { useState } from "react";

type LogoBuildProps = {
  /** A mark in `public/brand/`: `logo-c`, `logo-cad` or `logo-texttocad`. */
  name: string;
  alt: string;
  width: number;
  height: number;
  id?: string;
  className?: string;
  priority?: boolean;
  /** Show a Replay control under the mark. */
  replayable?: boolean;
};

/** A brand mark that builds itself in, as a CAD model is made (`scripts/brand/animate-logos.mjs`):
 * sketched on a grid, extruded, its counters cut and its corners chamfered. The animation is
 * the SVG's own SMIL, so it plays once without script; readers who prefer reduced motion get
 * the static mark until they ask for a replay. */
export function LogoBuild({ name, alt, width, height, id, className, priority = false, replayable = false }: LogoBuildProps) {
  // Each replay is a fresh URL, which restarts the SVG's clock from the first sketch stroke.
  const [run, setRun] = useState(0);
  const image = (
    <picture>
      {run === 0 ? <source media="(prefers-reduced-motion: reduce)" srcSet={`/brand/${name}.svg`} /> : null}
      <img
        id={id}
        src={`/brand/${name}-animated.svg${run ? `?run=${run}` : ""}`}
        alt={alt}
        width={width}
        height={height}
        className={className}
        decoding="async"
        loading={priority ? "eager" : "lazy"}
        fetchPriority={priority ? "high" : undefined}
      />
    </picture>
  );
  if (!replayable) return image;
  return (
    <>
      {image}
      <button
        type="button"
        onClick={() => setRun(value => value + 1)}
        className="mt-6 mr-6 inline-block text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground"
      >
        Replay
      </button>
    </>
  );
}
