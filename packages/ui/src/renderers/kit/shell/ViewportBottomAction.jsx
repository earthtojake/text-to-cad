import { useLayoutEffect, useRef, useState } from "react";
import { Button } from "@hardcore/ui/primitives/button";
import { cn } from "@hardcore/ui/utils";

const ACTION_CLASS = "pointer-events-auto border border-primary/20 bg-primary/85 text-primary-foreground shadow-lg shadow-black/20 hover:bg-primary/75 focus-visible:ring-primary/35";
const METRICS_CLASS = "h-9 w-fit min-w-0 max-w-full sm:max-w-[min(28rem,calc(100%-16rem))] shrink overflow-hidden px-4 text-xs max-sm:w-full max-sm:pr-32";
const COMPOSER_METRICS_CLASS = "h-9 w-fit min-w-0 max-w-full shrink overflow-hidden px-4 text-xs";

/**
 * The viewport's bottom action: the one button the active tool offers, centred
 * over the bottom edge. `composer` is a host that has a prompt composer docked
 * under the viewport, which the button clears.
 *
 * `shortLabel` is what the button says when `label` does not FIT — a label cut off
 * mid-token reads like a broken name rather than a long one, so a long one is
 * replaced outright ("Copy 3 references"). Whether it fits depends on the
 * viewport, not on the string, so it is measured rather than guessed from a
 * length: a hidden ruler carries the full label under the button's own width
 * constraints. The ruler is deliberately independent of what the button is
 * currently showing — measuring the visible label would latch, because swapping in
 * the shorter one makes the long one fit again. The title is always the full label.
 *
 * `render` replaces the button itself for an action that is not a plain press (a
 * host's prompt action, which opens its own destination): it is given the classes,
 * the disabled state, the title and the label node, and must render all four.
 */
export default function ViewportBottomAction({
  label, shortLabel = "", title = label, disabled = false, onInvoke, composer = false, render = null, children = null
}) {
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
  }, [label, shortLabel, composer]);

  const metrics = composer ? COMPOSER_METRICS_CLASS : METRICS_CLASS;
  const shown = shortLabel && !fits ? shortLabel : label;
  const content = <span className="block min-w-0 max-w-full truncate">{shown}</span>;
  const className = cn(ACTION_CLASS, metrics);
  return (
    <div className={cn("pointer-events-none absolute inset-x-4 z-20 flex min-w-0 justify-center", composer ? "bottom-36" : "bottom-4")}>
      {shortLabel ? (
        <span aria-hidden="true" className={cn("pointer-events-none invisible absolute left-0 top-0", metrics)}>
          <span ref={rulerRef} className="block min-w-0 max-w-full truncate">{label}</span>
        </span>
      ) : null}
      {render
        ? render({ className, disabled, title, children: content })
        : <Button type="button" variant="default" size="sm" className={className}
            disabled={disabled} onClick={() => void onInvoke?.()} title={title}>{content}</Button>}
      {children ? <div className="pointer-events-auto ml-2">{children}</div> : null}
    </div>
  );
}

/** Draw's bottom action: the view with its ink, to the prompt or the clipboard. */
export function drawingCaptureAction({ composer = false, disabled = false, onInvoke }) {
  return {
    label: composer ? "Add to Prompt" : "Copy Drawing",
    title: composer ? "Add the view and its drawing to the prompt" : "Copy the view and its drawing to the clipboard",
    disabled, onInvoke
  };
}
