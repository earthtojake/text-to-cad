import { useEffect, useState } from "react";

/** How long the pointer rests on a thing before its name shows: long enough that passing over things shows nothing. */
export const HOVER_TIP_DELAY_MS = 450;

/**
 * The name of what the pointer rests on, in a small tip beside it (a flat view's: "C17.1 · +5V"), shown once
 * the pointer has rested on the same thing a moment (`HOVER_TIP_DELAY_MS`) and gone the moment it leaves it.
 * It is the picture's own label, like a native tooltip: it takes no pointer and moves nothing. `tip` is
 * `{ key, text, x, y }` in the pane's pixels, or null; a new `key` starts the wait again.
 *
 * @param {{ tip: { key: string, text: string, x: number, y: number } | null }} props
 */
export default function HoverTip({ tip }) {
  const [shown, setShown] = useState(null);
  useEffect(() => {
    setShown(null);
    if (!tip) return undefined;
    const timer = window.setTimeout(() => setShown(tip), HOVER_TIP_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [tip?.key]);
  if (!shown || !tip || shown.key !== tip.key) return null;
  return <div role="tooltip" className="pointer-events-none absolute z-30 max-w-64 truncate rounded-md border border-border bg-popover px-2 py-1 text-tiny text-popover-foreground shadow-md"
    style={{ left: shown.x + 12, top: shown.y + 16 }} data-hover-tip="">{shown.text}</div>;
}
