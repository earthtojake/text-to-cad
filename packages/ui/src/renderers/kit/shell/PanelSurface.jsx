import { useRef, useState } from "react";
import { ScrollArea } from "@cad/ui/primitives/scroll-area";
import { cn } from "@cad/ui/utils";
import { capturePointer, releasePointer } from "../../../lib/pointerCapture.js";

// The surface the view's one panel is (`FlatPanel.jsx`, at the view's left): the chrome's colour, the navbar's (a step
// off the canvas, so the frame reads apart from the picture), its 1px rule on its right side, its type scope
// (`data-panel-surface`: every step of the type scale is the panel's 12/16 inside it, `styles/globals.css`, and a
// phone's page its finger sizes), the head's row, ONE scroller for its body, and the grip on its right edge.
//
// Its lines: ONE horizontal line, `--panel-inset` (16px, `styles/globals.css`), where everything read in it starts
// and ends: a tab's name, the search icon, a row's one glyph (a branch's chevron or a leaf's icon, 10px further a
// level, its name after it: `primitives/tree-row.jsx`), a section's controls (a dropdown, a field, a switch, a
// slider's track), every line of text that follows no icon (a heading, a label, a status line), and at the right a
// row's last action's glyph and every right-hand value. The body pads by it; a box drawn round what is read (a tab's
// pill, a row's fill, the search box) hangs out past the line by its own padding: a row's by half the inset
// (`--tree-row-hang`), the head's tabs and icon buttons by theirs (`headInsets`).
// Vertically the panel is on one 8px step: 8px over the head's row (32px: the tabs, or the search box, and the 28px
// buttons), 8px under it to its rule. A head that is one title (`headCompact`) is a list row's height instead (28px),
// 8px over it and nothing under it, so its list starts the body's 4px under it.
export const PANEL_SURFACE_PX = 8;
const HALF_INSET = "calc(var(--panel-inset) / 2)";
// A row's fill hangs half the inset out past the line and its glyph stands half the inset into it; its last action's
// glyph ends the inset from the panel's right (half the inset, less that button's own 2px).
const PANEL_ROW_VARIABLES = Object.freeze({ "--tree-row-pad": HALF_INSET, "--tree-row-hang": HALF_INSET,
  "--tree-row-actions-pad": "calc(var(--panel-inset) / 2 - 2px)" });
const NO_HEAD_INSETS = Object.freeze({ start: 0, end: 0 });
const KEY_NUDGE_PX = 16;

/**
 * The panel's width from its grip: the person's, dragged on its right edge (rightward, wider) or nudged by the arrow
 * keys, written once as the drag lets go. The width drawn is `width` as it is (the
 * default, or what the person last chose): nothing else, the view's width included, changes it. `minWidth` and
 * `maxWidth` bound the grip alone, as it moves; a `maxWidth` not known yet (the view not measured: `Infinity`) holds it
 * at the width it has, so no key or drag ever makes a width that is not a number of pixels (End's `Infinity`).
 * @param {{ width: number, minWidth: number, maxWidth: number, onWidthChange(width: number): void }} options
 */
export function usePanelWidth({ width, minWidth, maxWidth, onWidthChange }) {
  const widest = Math.max(minWidth, Number.isFinite(maxWidth) ? maxWidth : width);
  const [draft, setDraft] = useState(null);
  const drawnWidth = draft ?? width;
  const drag = useRef(null);
  const clamp = value => Math.round(Math.max(minWidth, Math.min(widest, value)));
  const grip = {
    "aria-valuenow": drawnWidth, "aria-valuemin": minWidth, "aria-valuemax": widest, dragging: draft !== null,
    onPointerDown(event) {
      if (event.button !== 0) return;
      event.preventDefault();
      drag.current = { pointerId: event.pointerId, x: event.clientX, from: drawnWidth, next: null };
      capturePointer(event.currentTarget, event.pointerId);
    },
    onPointerMove(event) {
      const current = drag.current;
      if (current?.pointerId !== event.pointerId) return;
      current.next = clamp(current.from + event.clientX - current.x);
      setDraft(current.next);
    },
    onPointerUp: stop,
    onPointerCancel: stop,
    onKeyDown(event) {
      const next = { ArrowLeft: drawnWidth - KEY_NUDGE_PX, ArrowRight: drawnWidth + KEY_NUDGE_PX, Home: 0, End: Infinity }[event.key];
      if (next === undefined) return;
      event.preventDefault();
      onWidthChange(clamp(next));
    }
  };
  function stop(event) {
    const current = drag.current;
    if (!current || current.pointerId !== event.pointerId) return;
    drag.current = null;
    releasePointer(event.currentTarget, event.pointerId);
    setDraft(null);
    if (current.next !== null && current.next !== width) onWidthChange(current.next);
  }
  return { drawnWidth, grip };
}

/**
 * The panel itself: `<aside>` on the panel surface, its head (`head`, the row's contents, pinned; its rule under it unless
 * `headStack`: a head of two rows, one over the other (the view's panel's search over its tabs).
 * `headRule` is false: a head that is its body's own title, which flows straight into it; `headCompact`, that title a
 * list row's height with nothing under it; `null`, no pinned row), ONE scroller round `children`, and its grip (none on
 * a phone's page).
 * @param {{ mode: "push" | "page", label: string, open: boolean, hidden?: boolean,
 *   width: number, grip: ReturnType<typeof usePanelWidth>["grip"] | null, gripLabel: string, head: import("react").ReactNode, headRule?: boolean, headCompact?: boolean,
 *   headRef?: import("react").Ref<HTMLDivElement>, headProps?: object, headInsets?: { start: number, end: number },
 *   scrollerRef?: import("react").Ref<HTMLElement>, scrollerProps?: object, onKeyDown?: (event: KeyboardEvent) => void,
 *   children?: import("react").ReactNode }} props
 *   `headInsets`: how far the head's first and last boxes hang out past the inset (their own padding: a tab's pill's,
 *   an icon button's), so what they hold stands on it. Other props (`data-*`) go on the `<aside>`.
 */
export function PanelSurface({ mode, label, open, hidden = false, width, grip, gripLabel, head, headRule = true, headCompact = false, headStack = false, headRef, headProps = {},
  headInsets = NO_HEAD_INSETS, scrollerRef, scrollerProps = {}, onKeyDown, children, ...props }) {
  const page = mode === "page";
  return <aside aria-label={label} data-panel-surface={page ? "page" : "docked"} data-open={open ? "" : undefined} hidden={!open || hidden}
    onKeyDown={onKeyDown} {...props}
    className={cn("flex min-h-0 flex-col bg-sidebar text-ui text-foreground",
      mode === "push" && "relative h-full shrink-0 border-r border-border",
      page && "absolute inset-0 z-50")}
    style={page ? PANEL_ROW_VARIABLES : { ...PANEL_ROW_VARIABLES, width }}>
    {head === null ? null : <div ref={headRef} className={cn("box-content flex shrink-0 gap-1 border-b", headStack ? "flex-col items-stretch" : "items-center", headStack ? null : headCompact ? "h-7" : "h-8", headRule ? "border-border" : "border-transparent")}
      style={{ paddingTop: PANEL_SURFACE_PX, paddingBottom: headCompact ? 0 : PANEL_SURFACE_PX,
        paddingLeft: `calc(var(--panel-inset) - ${headInsets.start}px)`, paddingRight: `calc(var(--panel-inset) - ${headInsets.end}px)` }} data-panel-head="" data-rule={headRule ? "" : undefined}
      data-compact={headCompact ? "" : undefined} {...headProps}>{head}</div>}
    <ScrollArea className="min-h-0 flex-1" viewportRef={scrollerRef} viewportProps={{ "data-panel-scroller": "", ...scrollerProps }}>
      {children}
    </ScrollArea>
    {page || !grip ? null : <div role="separator" aria-orientation="vertical" aria-label={gripLabel} tabIndex={0}
      aria-valuenow={grip["aria-valuenow"]} aria-valuemin={grip["aria-valuemin"]} aria-valuemax={grip["aria-valuemax"]}
      className={cn("absolute inset-y-0 -right-1 z-10 w-2 cursor-col-resize touch-none focus-visible:outline-none",
        "after:absolute after:inset-y-0 after:left-1/2 after:w-px after:-translate-x-1/2 after:transition-colors hover:after:bg-ring focus-visible:after:bg-ring",
        grip.dragging && "after:bg-ring")}
      onPointerDown={grip.onPointerDown} onPointerMove={grip.onPointerMove} onPointerUp={grip.onPointerUp} onPointerCancel={grip.onPointerCancel}
      onKeyDown={grip.onKeyDown} data-panel-grip="" data-flat-panel-grip="" />}
  </aside>;
}
