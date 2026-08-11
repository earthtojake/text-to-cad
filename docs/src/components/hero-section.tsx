"use client";

import type { CSSProperties } from "react";
import { useLayoutEffect, useRef, useState } from "react";
import { HeroStepRender } from "@/components/hero-step-render";

const textToCadAscii = String.raw`████████╗███████╗██╗  ██╗████████╗   ████████╗ ██████╗     ██████╗ █████╗ ██████╗ 
╚══██╔══╝██╔════╝╚██╗██╔╝╚══██╔══╝   ╚══██╔══╝██╔═══██╗   ██╔════╝██╔══██╗██╔══██╗
   ██║   █████╗   ╚███╔╝    ██║         ██║   ██║   ██║   ██║     ███████║██║  ██║
   ██║   ██╔══╝   ██╔██╗    ██║         ██║   ██║   ██║   ██║     ██╔══██║██║  ██║
   ██║   ███████╗██╔╝ ██╗   ██║   ██╗   ██║   ╚██████╔╝██╗╚██████╗██║  ██║██████╔╝
   ╚═╝   ╚══════╝╚═╝  ╚═╝   ╚═╝   ╚═╝   ╚═╝    ╚═════╝ ╚═╝ ╚═════╝╚═╝  ╚═╝╚═════╝ `;

const ASCII_MEASURE_FONT_SIZE = 10;
// Floor low enough that the widest wordmark still FITS on the narrowest phones
// rather than being clipped by the frame's overflow-hidden. TEXT.TO.CAD is 82
// columns, which needs ~7px at 375px and ~6px at 320px — a higher floor silently
// cut the trailing glyphs off.
const ASCII_MIN_FONT_SIZE = 5;
const ASCII_MAX_FONT_SIZE = 18;
const ASCII_MAX_HEIGHT = 132;
const ASCII_WIDTH_FILL = 0.995;

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function AsciiWord({ ascii }: { ascii: string }) {
  const frameRef = useRef<HTMLDivElement>(null);
  const measureRef = useRef<HTMLPreElement>(null);
  const [fontSize, setFontSize] = useState(10.5);

  useLayoutEffect(() => {
    const frame = frameRef.current;
    const measure = measureRef.current;

    if (!frame || !measure) {
      return;
    }

    const updateFontSize = () => {
      const measuredWidth = measure.scrollWidth;
      const measuredHeight = measure.scrollHeight;
      const availableWidth = frame.clientWidth * ASCII_WIDTH_FILL;

      if (!measuredWidth || !measuredHeight || !availableWidth) {
        return;
      }

      const widthSize =
        (availableWidth / measuredWidth) * ASCII_MEASURE_FONT_SIZE;
      const heightSize =
        (ASCII_MAX_HEIGHT / measuredHeight) * ASCII_MEASURE_FONT_SIZE;
      const nextFontSize = clamp(
        Math.min(widthSize, heightSize),
        ASCII_MIN_FONT_SIZE,
        ASCII_MAX_FONT_SIZE
      );

      setFontSize((current) =>
        Math.abs(current - nextFontSize) > 0.05 ? nextFontSize : current
      );
    };

    updateFontSize();

    const resizeObserver = new ResizeObserver(updateFontSize);
    resizeObserver.observe(frame);

    void document.fonts?.ready.then(updateFontSize);

    return () => resizeObserver.disconnect();
  }, [ascii]);

  const visibleClassName =
    "inline-block select-none whitespace-pre font-mono leading-[108%]";
  const measureClassName =
    "pointer-events-none invisible absolute left-0 top-0 inline-block whitespace-pre font-mono text-[10px] leading-[108%]";
  const asciiStyle = { fontSize: `${fontSize}px` } as CSSProperties;

  return (
    <div
      ref={frameRef}
      className="relative max-h-[132px] w-full overflow-hidden"
    >
      <pre ref={measureRef} className={measureClassName} aria-hidden="true">
        {ascii}
      </pre>
      <pre
        className={`${visibleClassName} text-muted-foreground/55`}
        style={asciiStyle}
      >
        {ascii}
      </pre>
      <pre
        className={`ascii-terminal-reveal absolute left-0 top-0 ${visibleClassName} text-foreground`}
        style={asciiStyle}
      >
        {ascii}
      </pre>
    </div>
  );
}

function HeroAsciiHeading() {
  return (
    <div aria-hidden="true" className="w-full max-w-full overflow-hidden">
      <AsciiWord ascii={textToCadAscii} />
    </div>
  );
}

function HeroSubtitle({ className = "" }: { className?: string }) {
  return (
    <p
      className={`text-[15px] font-medium leading-6 text-foreground sm:text-[17px] sm:leading-7 lg:text-[19px] lg:leading-8 ${className}`}
    >
      A library of agent skills for CAD, CAE and CAM.{" "}
      <span className="text-primary">
        100% open source + free, runs locally
      </span>
    </p>
  );
}

export function HeroSection() {
  return (
    <section className="border border-border bg-card">
      {/* Wordmark takes 2/3 so the ASCII can scale up; byline takes the
          remaining 1/3. Below lg they stack full-width, as before. */}
      <div className="grid min-w-0 lg:grid-cols-3">
        <div className="flex min-w-0 items-center px-4 py-4 sm:px-5 lg:col-span-2 lg:min-h-[156px] lg:px-6 lg:py-5">
          <h1 className="sr-only">text.to.cad</h1>
          <HeroAsciiHeading />
        </div>

        <div className="flex min-w-0 items-center border-t border-border px-4 py-4 sm:px-5 lg:col-span-1 lg:min-h-[156px] lg:border-l lg:border-t-0 lg:px-6 lg:py-5">
          <HeroSubtitle className="w-full" />
        </div>
      </div>

      <div className="h-[260px] min-h-0 border-t border-border bg-background sm:h-[300px] lg:h-[340px]">
        <HeroStepRender />
      </div>
    </section>
  );
}
