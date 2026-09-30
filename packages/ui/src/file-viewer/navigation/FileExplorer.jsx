import { X } from "lucide-react";
import { useRef } from "react";

import { Button } from "../../primitives/button.jsx";
import { Sheet, SheetClose, SheetContent, SheetTitle } from "../../primitives/sheet.jsx";
import { CHROME_INSET_PX } from "../../lib/chromeInset.js";
import { hasOpenPopup } from "../../lib/popups.js";
import { PANEL_MAX_WIDTH, PANEL_MIN_WIDTH, clampPanelWidth } from "./panelWidth.js";

// A phone's explorer is a sheet over the view with room for a few levels of nesting.
const MOBILE_WIDTH = 280;
// A drag has to go well below the minimum — past half of it — before the explorer closes: one that
// merely overshoots stops at the minimum.
const COLLAPSE_WIDTH = PANEL_MIN_WIDTH / 2;

/**
 * The file explorer: a panel that floats over the LEFT of the view, never beside it.
 *
 * It overlays what it opens over — a model, its tools, a host's home — and never resizes or
 * moves any of it: the viewport keeps its size and its framing, the tool strip keeps its corner.
 * It is inset from the view's edges exactly as the tool strip is (`CHROME_INSET_PX`), on a solid
 * background, above the tools. It stays up while a person walks the tree file by file; its toggle
 * in the navbar is how it closes.
 *
 * Its right edge is its one handle: dragged, it sizes the explorer between the tab's bounds
 * (`panelWidth.js`), and only a drag well below the minimum — past half of it — closes it; the
 * keyboard never does. Below the viewer breakpoint it is a sheet over the view instead, dismissed
 * by a press outside, Escape or its X, and by a pick.
 *
 * @param {object} props
 * @param {string} props.label Names the panel for the accessibility tree.
 * @param {number} props.width
 * @param {(width: number) => void} props.onWidthChange
 * @param {() => void} [props.onCollapse]
 * @param {boolean} [props.mobile]
 * @param {HTMLElement|null} [props.portalContainer] Where the mobile sheet mounts: the view's body.
 * @param {() => void} [props.onDismiss]
 * @param {import("react").ReactNode} props.children
 */
export function FileExplorer({ label, width, onWidthChange, onCollapse, mobile = false, portalContainer = null, onDismiss, children }) {
  const drag = useRef(null);
  const content = useRef(null);
  if (mobile) return <Sheet open onOpenChange={open => { if (!open) onDismiss?.(); }} modal={false}>
    <SheetContent ref={content} side="left" portalContainer={portalContainer} showCloseButton={false} aria-describedby={undefined}
      className="absolute inset-y-2 left-2 h-auto w-[min(var(--file-explorer-sheet-width),calc(100%-16px))] max-w-none gap-0 overflow-hidden rounded-lg border bg-background shadow-lg data-[state=open]:animate-none data-[state=closed]:animate-none"
      style={{ "--file-explorer-sheet-width": `${MOBILE_WIDTH}px` }}
      data-file-panel-container="tree" data-file-explorer="" data-mobile-panel="" onOpenAutoFocus={event => event.preventDefault()}
      onCloseAutoFocus={event => event.preventDefault()}
      // A press outside, Escape or the X dismisses the sheet; focus moving elsewhere does not. The
      // sheet never takes focus, so a host handing focus back to the control that opened this
      // view (a closing "New tab" menu) must not close the tree an empty tab opens on.
      onFocusOutside={event => event.preventDefault()}
      onInteractOutside={event => {
        // The navbar's toggle closes it itself; a popup it opened (a Select, a menu) portals outside
        // it, and dismissing that child must not dismiss the explorer.
        const target = event.detail.originalEvent.target;
        if (target?.closest?.('[data-file-panel], [data-slot=select-content], [data-slot=dropdown-menu-content], [data-slot=dropdown-menu-sub-content], [data-slot=popover-content], [data-slot=context-menu-content]')
          || hasOpenPopup(content.current)) event.preventDefault();
      }}>
      <SheetTitle className="sr-only">{label}</SheetTitle>
      <SheetClose asChild><Button className="absolute right-2 top-2 z-10 size-5" variant="ghost" size="icon-xs" aria-label="Close files"><X className="size-3" /></Button></SheetClose>
      <div className="min-h-0 flex-1 overflow-hidden [&_[data-mobile-panel-top-row]]:pr-9">{children}</div>
    </SheetContent>
  </Sheet>;

  const resize = (nextWidth, { dragging = false } = {}) => {
    if (dragging && nextWidth < COLLAPSE_WIDTH && onCollapse) {
      drag.current = null;
      onCollapse();
    } else {
      onWidthChange(clampPanelWidth(nextWidth));
    }
  };
  // The handle drags the explorer's right edge, so its width is measured from its own LEFT edge:
  // the explorer is anchored there, at the view's inset.
  const onPointerDown = (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    drag.current = { left: event.currentTarget.parentElement.getBoundingClientRect().left, pointerId: event.pointerId };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const stopDrag = (event) => {
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };
  return (
    <aside aria-label={label} data-file-panel-container="tree" data-file-explorer=""
      className="absolute z-40 flex overflow-hidden rounded-lg border bg-background shadow-lg"
      style={{ top: CHROME_INSET_PX, left: CHROME_INSET_PX, bottom: CHROME_INSET_PX, width, maxWidth: `calc(100% - ${CHROME_INSET_PX * 2}px)` }}>
      <div className="min-h-0 min-w-0 flex-1 overflow-hidden">{children}</div>
      <div
        aria-label={`Resize ${label.toLowerCase()} panel`}
        aria-orientation="vertical"
        aria-valuemax={PANEL_MAX_WIDTH}
        aria-valuemin={PANEL_MIN_WIDTH}
        aria-valuenow={width}
        className="absolute inset-y-0 right-0 w-1.5 cursor-col-resize touch-none transition-colors hover:bg-ring/40 focus-visible:bg-ring/40 focus-visible:outline-none"
        onPointerDown={onPointerDown}
        onPointerMove={(event) => { if (drag.current?.pointerId === event.pointerId) resize(event.clientX - drag.current.left, { dragging: true }); }}
        onPointerUp={stopDrag}
        onPointerCancel={stopDrag}
        onLostPointerCapture={() => { drag.current = null; }}
        onKeyDown={(event) => {
          const nextWidth = { ArrowRight: width + 16, ArrowLeft: width - 16, Home: PANEL_MIN_WIDTH, End: PANEL_MAX_WIDTH }[event.key];
          if (nextWidth === undefined) return;
          event.preventDefault();
          resize(nextWidth);
        }}
        role="separator"
        tabIndex={0}
      />
    </aside>
  );
}
