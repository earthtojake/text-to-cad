import { useEffect, useMemo, useRef, useState } from "react";
import { hoverTipText } from "../inspector/inspect.js";

/** How long the pointer rests on a thing before its name shows: long enough that passing over things shows nothing. */
export const HOVER_TIP_DELAY_MS = 450;

/**
 * The name of what the pointer rests on, in a small tip beside it ("C17.1 · +5V"), shown once
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

/**
 * The frame's hover tip (`ViewFrame.jsx`), every view's that picks: the name of what a press would pick
 * (`hovered`, the view's) as the view describes it, short (`inspect.js`'s `hoverTipText`), beside where the
 * pointer came onto it. Only while the pointer is on the canvas and no button is held (a drag, a pan), and
 * only while `enabled` (Select in hand). `handlers` go on the box the canvas is drawn in, whose pixels the
 * tip is placed in.
 * @param {{ hovered: string, describe: ((id: string) => import("../inspector/inspect.js").DetailItem | null) | null, enabled: boolean }} options
 */
export function useFrameHoverTip({ hovered, describe, enabled }) {
  const pointer = useRef(null);
  const [over, setOver] = useState(false);
  const [held, setHeld] = useState(false);
  const handlers = useMemo(() => ({
    onPointerMoveCapture: (event) => {
      const box = event.currentTarget.getBoundingClientRect();
      const onCanvas = event.target instanceof Element && Boolean(event.target.closest("canvas"));
      pointer.current = onCanvas ? { x: event.clientX - box.left, y: event.clientY - box.top } : null;
      setOver(onCanvas);
      setHeld(event.buttons !== 0);
    },
    onPointerUpCapture: () => setHeld(false),
    onPointerLeave: () => { pointer.current = null; setOver(false); setHeld(false); },
  }), []);
  // Where the pointer was as it came onto what it rests on: the tip stays there while it rests.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const at = useMemo(() => pointer.current, [hovered, over]);
  const text = useMemo(() => (hovered && describe ? hoverTipText(describe(hovered)) : ""), [hovered, describe]);
  const tip = enabled && over && !held && hovered && text && at ? { key: hovered, text, x: at.x, y: at.y } : null;
  return { handlers, tip };
}
