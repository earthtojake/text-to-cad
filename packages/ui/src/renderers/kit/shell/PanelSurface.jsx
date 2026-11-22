import { useRef, useState } from "react";
import { ScrollArea } from "@cad/ui/primitives/scroll-area";
import { cn } from "@cad/ui/utils";
import { capturePointer, releasePointer } from "../../../lib/pointerCapture.js";
// The surface's metrics, shared with the file viewer's stand-in drawn before the view is up (`file-viewer/FileViewer.tsx`).
import { PANEL_HEAD_ROW, PANEL_HEAD_ROW_PX, PANEL_ROW_VARIABLES, PANEL_SURFACE_PX } from "../../../file-viewer/panelToggles.js";
import { PANEL_PEEK_ASIDE_CLASS, PANEL_PEEK_CARD_CLASS, PANEL_PEEK_CARD_STYLE, PANEL_PEEK_CONTENT_STYLE, PANEL_PEEK_ELEVATION_CLASS, PANEL_PEEK_GAP_PX,
  PANEL_PEEK_IN_LEFT_CLASS, PANEL_PEEK_OUT_LEFT_CLASS, panelPeekMotionClass } from "../../../file-viewer/panelPeek.js";

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
// Vertically the panel is on one 8px step: 8px over the head's row (`PANEL_HEAD_ROW_PX`, 32px: the tabs, a lone title
// or the search box, and the 28px buttons), 8px under it to its rule, whatever the row holds.
export { PANEL_HEAD_ROW_PX, PANEL_SURFACE_PX };
// A peek's card, its gap, its look and its slide: the file viewer's (`file-viewer/panelPeek.js`), the ONE source, shared
// with the stand-in it draws before the view is up and with any card that mirrors the peek.
export { PANEL_PEEK_ELEVATION_CLASS, PANEL_PEEK_GAP_PX, PANEL_PEEK_IN_LEFT_CLASS as PEEK_IN_CLASS, PANEL_PEEK_OUT_LEFT_CLASS as PEEK_OUT_CLASS };
const NO_HEAD_INSETS = Object.freeze({ start: 0, end: 0 });
// A head inset, in px or as a CSS length (one the scale sizes).
const inset = value => (typeof value === "number" ? `${value}px` : value);
const KEY_NUDGE_PX = 16;

/**
 * The panel's width from its grip: the person's, dragged on its right edge (rightward, wider) or nudged by the arrow
 * keys, written once as the drag lets go. The width drawn is `width` as it is (the
 * default, or what the person last chose): nothing else, the view's width included, changes it. `minWidth` and
 * `maxWidth` bound the grip alone, as it moves (fixed bounds, `sidebars.js`).
 * @param {{ width: number, minWidth: number, maxWidth: number, onWidthChange(width: number): void }} options
 */
export function usePanelWidth({ width, minWidth, maxWidth, onWidthChange }) {
  const widest = Math.max(minWidth, maxWidth);
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
 * The panel itself: `<aside>` on the panel surface, its head (`head`, the row's contents, pinned, the one block; its rule
 * under it unless `headRule` is false; `null`, no pinned row), ONE scroller round `children`, and its grip (none on a
 * phone's page or a peek).
 * @param {{ mode: "push" | "page", label: string, open: boolean, hidden?: boolean,
 *   width: number, grip: ReturnType<typeof usePanelWidth>["grip"] | null, gripLabel: string, head: import("react").ReactNode, headRule?: boolean,
 *   headRef?: import("react").Ref<HTMLDivElement>, headProps?: object, headInsets?: { start: number | string, end: number | string },
 *   scrollerRef?: import("react").Ref<HTMLElement>, scrollerProps?: object, onKeyDown?: (event: KeyboardEvent) => void,
 *   children?: import("react").ReactNode, peek?: boolean, asideRef?: import("react").Ref<HTMLElement> }} props
 *   `headInsets`: how far the head's first and last boxes hang out past the inset (their own padding: a tab's pill's,
 *   an icon button's), so what they hold stands on it. `peek`: a collapsed panel shown over the view, at its docked
 *   place and width, taking no room (`data-panel-peek`): a card inside that box (`PANEL_PEEK_GAP_PX`), its content where
 *   the docked panel's is, sliding in (unless `peekEntered`: it already stands, taken over from the file viewer's
 *   stand-in); `peekLeaving`, that peek sliding out (`data-panel-peek-leaving`), and `onPeekExited` once it is out. Other props (`data-*`, handlers) go on the `<aside>`.
 */
export function PanelSurface({ mode, label, open, hidden = false, width, grip, gripLabel, head, headRule = true, headRef, headProps = {},
  headInsets = NO_HEAD_INSETS, scrollerRef, scrollerProps = {}, onKeyDown, peek = false, peekLeaving = false, peekEntered = false, onPeekExited, asideRef, children, ...props }) {
  const page = mode === "page";
  const peeking = mode === "push" && peek;
  // With its rule (tabs), the head is its row and 8px either side, the rule under; with none (a lone tab's title, and
  // the search that stands in its place), the row alone over the body: nothing to separate, no gap kept for a rule.
  const headNode = head === null ? null : <div ref={headRef} className={cn("box-content flex shrink-0 items-center gap-1", headRule && "border-b border-border")}
      style={{ paddingTop: PANEL_SURFACE_PX, paddingBottom: headRule ? PANEL_SURFACE_PX : 0, height: PANEL_HEAD_ROW,
        paddingLeft: `calc(var(--panel-inset) - ${inset(headInsets.start)})`, paddingRight: `calc(var(--panel-inset) - ${inset(headInsets.end)})` }} data-panel-head="" data-rule={headRule ? "" : undefined}
      {...headProps}>{head}</div>;
  const scroll = <ScrollArea className="min-h-0 flex-1" viewportRef={scrollerRef} viewportProps={{ "data-panel-scroller": "", ...scrollerProps }}>
      {children}
    </ScrollArea>;
  return <aside ref={asideRef} aria-label={label} data-panel-surface={page ? "page" : "docked"} data-open={open ? "" : undefined} hidden={!open || hidden}
    data-panel-peek={peek && open && !hidden ? "" : undefined} data-panel-peek-leaving={peeking && peekLeaving ? "" : undefined} onKeyDown={onKeyDown} {...props}
    onAnimationEnd={peeking && peekLeaving ? event => { if (event.target === event.currentTarget) onPeekExited?.(); } : undefined}
    className={cn("flex min-h-0 flex-col text-ui text-foreground", !peeking && "bg-sidebar",
      mode === "push" && !peek && "relative h-full shrink-0 border-r border-border",
      peeking && PANEL_PEEK_ASIDE_CLASS, peeking && panelPeekMotionClass({ leaving: peekLeaving, entered: peekEntered }),
      page && "absolute inset-0 z-50")}
    style={page ? PANEL_ROW_VARIABLES : { ...PANEL_ROW_VARIABLES, width }}>
    {peeking ? <>
      <div aria-hidden="true" className={PANEL_PEEK_CARD_CLASS} style={PANEL_PEEK_CARD_STYLE}
        data-panel-peek-card="" />
      <div className="relative flex min-h-0 flex-1 flex-col" style={PANEL_PEEK_CONTENT_STYLE}>{headNode}{scroll}</div>
    </> : <>{headNode}{scroll}</>}
    {/* No grip on a phone's page, nor on a peek: a peek is passing, so its width is not the person's to set there. */}
    {page || peeking || !grip ? null : <div role="separator" aria-orientation="vertical" aria-label={gripLabel} tabIndex={0}
      aria-valuenow={grip["aria-valuenow"]} aria-valuemin={grip["aria-valuemin"]} aria-valuemax={grip["aria-valuemax"]}
      className={cn("absolute inset-y-0 -right-1 z-10 w-2 cursor-col-resize touch-none focus-visible:outline-none",
        "after:absolute after:inset-y-0 after:left-1/2 after:w-px after:-translate-x-1/2 after:transition-colors hover:after:bg-ring focus-visible:after:bg-ring",
        grip.dragging && "after:bg-ring")}
      onPointerDown={grip.onPointerDown} onPointerMove={grip.onPointerMove} onPointerUp={grip.onPointerUp} onPointerCancel={grip.onPointerCancel}
      onKeyDown={grip.onKeyDown} data-panel-grip="" data-flat-panel-grip="" />}
  </aside>;
}
