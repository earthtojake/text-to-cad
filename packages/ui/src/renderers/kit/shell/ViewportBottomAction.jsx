import { useViewerMobile } from "../../../file-viewer/responsive.js";
import { VIEWPORT_BOTTOM_CENTER } from "./viewportLayout.js";
import { useLayoutEffect, useRef, useState } from "react";
import { Button } from "@hardcore/ui/primitives/button";
import { cn } from "@hardcore/ui/utils";

const ACTION_CLASS = "pointer-events-auto border border-primary/20 bg-primary/85 text-primary-foreground shadow-lg shadow-black/20 hover:bg-primary/75 focus-visible:ring-primary/35";
const METRICS_CLASS = "h-11 w-fit min-w-0 max-w-full shrink overflow-hidden px-5 text-sm";

/**
 * The viewport's bottom action: the one button the active tool offers, centred
 * over the shared bottom inset.
 *
 * `shortLabel` is what the button says when `label` does not FIT — a label cut off
 * mid-token reads like a broken name rather than a long one, so a long one is
 * replaced outright ("Copy 3 references"). Whether it fits depends on the
 * viewport, not on the string, so it is measured rather than guessed from a
 * length: a hidden ruler carries the full label under the button's own width
 * constraints. The ruler is deliberately independent of what the button is
 * currently showing — measuring the visible label would latch, because swapping in
 * the shorter one makes the long one fit again. The accessible text follows the visible action.
 *
 * `render` replaces the button itself for an action that is not a plain press (a
 * host's prompt action, which opens its own destination): it is given the classes,
 * the disabled state and the label node.
 */
export default function ViewportBottomAction({
  label, shortLabel = "", disabled = false, onInvoke, render = null, children = null, shortcut = ""
}) {
  const mobile = useViewerMobile();
  const rulerRef = useRef(null);
  const [fits, setFits] = useState(true);
  useLayoutEffect(() => {
    const ruler = rulerRef.current;
    if (!ruler) return undefined;
    // +1 so sub-pixel rounding does not read as an overflow.
    const measure = () => setFits(ruler.scrollWidth <= ruler.clientWidth + 1);
    measure();
    // Belt and braces: ResizeObserver is the precise signal but is not always
    // delivered promptly while the document is not being painted, and a window
    // resize is the case that actually changes the answer.
    window.addEventListener("resize", measure);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(ruler);
    return () => { window.removeEventListener("resize", measure); observer?.disconnect(); };
  }, [label, shortLabel]);

  const metrics = cn(METRICS_CLASS, mobile && "h-10 px-4");
  const shown = shortLabel && !fits ? shortLabel : label;
  const content = <><span className="block min-w-0 max-w-full truncate">{shown}</span>{shortcut && !mobile ? <kbd className="ml-3 shrink-0 font-sans text-xs opacity-65">{shortcut}</kbd> : null}</>;
  const className = cn(ACTION_CLASS, metrics);
  return (
    <div style={{ bottom: VIEWPORT_BOTTOM_CENTER }} className="pointer-events-none absolute inset-x-4 z-20 translate-y-1/2 flex min-w-0 justify-center">
      {shortLabel ? (
        <span aria-hidden="true" className={cn("pointer-events-none invisible absolute left-0 top-0", metrics)}>
          <span ref={rulerRef} className="block min-w-0 max-w-full truncate">{label}</span>
        </span>
      ) : null}
      {render
        ? render({ className, disabled, children: content })
        : <Button type="button" variant="default" size="sm" className={className}
            disabled={disabled} onClick={() => void onInvoke?.()} >{content}</Button>}
      {children ? <div className="pointer-events-auto ml-2">{children}</div> : null}
    </div>
  );
}

/** Draw's bottom action: the view with its ink, to the clipboard. */
export function drawingCaptureAction({ disabled = false, onInvoke }) {
  return {
    label: "Copy Drawing",
    disabled, onInvoke
  };
}
