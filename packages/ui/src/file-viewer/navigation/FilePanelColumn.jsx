import { X } from "lucide-react";
import { Button } from "../../primitives/button.jsx";
import { Sheet, SheetContent, SheetTitle, SheetClose } from "../../primitives/sheet.jsx";
import { useRef } from "react";

/**
 * The file surface's panel column: the one frame every panel is drawn in.
 *
 * There is one of these beside a file and never two, because there is one
 * open panel (`panels.js`). Whatever is in it — the file tree, a file's own
 * panel or its Display — gets the same border, the same width and the
 * same handle, which is the point: they used to be two columns of two
 * designs, a file list on the left and the viewer's own aside on the right,
 * each with its own idea of how wide a panel is.
 *
 * No title bar of the column's own. Each panel's own top row is its header —
 * the tree's filter, a file panel's first section — and the nav row's toggle is
 * how it closes.
 *
 * A collapsed panel is not rendered at all, so the toggle for it exists in
 * the document exactly once: in the nav row.
 */

/**
 * The column's range, and the one place it is written down.
 *
 * Both apps clamp to these — the desktop when it stores the width, the
 * standalone when it drags — so a panel is never a different size in one of
 * them, and the `aria-valuemin`/`max` on the handle below are the real
 * numbers rather than a second opinion.
 */
// Fits a Position section's joint sliders and their typed values without scrolling sideways.
export const PANEL_MIN_WIDTH = 256;
export const PANEL_MAX_WIDTH = 480;
export const PANEL_DEFAULT_WIDTH = 280;

/** Whatever a caller has, clamped into the column's range. */
export function clampPanelWidth(width) {
  const numeric = Number(width);
  if (!Number.isFinite(numeric)) {
    return PANEL_DEFAULT_WIDTH;
  }
  return Math.round(Math.max(PANEL_MIN_WIDTH, Math.min(PANEL_MAX_WIDTH, numeric)));
}

/**
 * @param {object} props
 * @param {string} props.id The open panel's id, for tests and for styling hooks.
 * @param {string} props.label Names the column for the accessibility tree: the toggle's own label.
 * @param {boolean} [props.hidden] Temporarily suspend without losing panel state.
 * @param {boolean} [props.mobile]
 * @param {HTMLElement|null} [props.portalContainer]
 * @param {() => void} [props.onDismiss]
 * @param {number} props.width
 * @param {(width: number) => void} props.onWidthChange
 * @param {() => void} [props.onCollapse]
 * @param {import("react").ReactNode} props.children
 */
export function FilePanelColumn({ id, label, width, onWidthChange, onCollapse, children, hidden = false, mobile = false, portalContainer = null, onDismiss }) {
  const drag = useRef(null);
  const content = useRef(null);
  const resize = (nextWidth) => {
    if (nextWidth < PANEL_MIN_WIDTH && onCollapse) {
      drag.current = null;
      onCollapse();
    } else {
      onWidthChange(clampPanelWidth(nextWidth));
    }
  };
  /**
   * The handle drags the column's left border, so the width is measured from
   * the surface's RIGHT edge — the column is anchored there and the content
   * gives up the room. `parentElement` is the row this column sits in, which
   * is that edge; a fragment has no box of its own to measure.
   */
  const onPointerDown = (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    const surface = event.currentTarget.parentElement;
    drag.current = { right: surface.getBoundingClientRect().right, pointerId: event.pointerId };
    event.currentTarget.setPointerCapture(event.pointerId);
  };
  const stopDrag = (event) => {
    drag.current = null;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };

  // Keep the floating panel inside its viewer even while opening. A slide from
  // outside the right edge creates horizontal overflow on narrow pages.
  if (mobile) return <Sheet open={!hidden} onOpenChange={open => { if (!open) onDismiss?.(); }} modal={false}>
    <SheetContent ref={content} portalContainer={portalContainer} showCloseButton={false} aria-describedby={undefined}
      className="absolute inset-y-2 right-2 h-auto w-[min(280px,calc(100%-32px))] max-w-none gap-0 overflow-hidden rounded-lg border shadow-lg data-[state=open]:animate-none data-[state=closed]:animate-none"
      data-file-panel-container={id} data-mobile-panel="" onOpenAutoFocus={event => event.preventDefault()}
      onCloseAutoFocus={event => event.preventDefault()}
      onInteractOutside={event => {
        // Navbar toggles switch sheets directly; don't let the old sheet's dismissal close the new one.
        const target = event.detail.originalEvent.target;
        // Selects and color/menu popups portal outside the sheet. Their touches
        // still belong to it, and dismissing a child must not dismiss the panel.
        if (target?.closest?.('[data-file-panel], [data-slot=select-content], [data-slot=dropdown-menu-content], [data-slot=dropdown-menu-sub-content], [data-slot=popover-content]')
          || content.current?.querySelector('[aria-haspopup][aria-expanded="true"]')) event.preventDefault();
      }}>
      <SheetTitle className="sr-only">{label.replace(/^(Show|Hide) /, "")}</SheetTitle>
      <SheetClose asChild><Button className="absolute right-2 top-2 z-10 size-5" variant="ghost" size="icon-xs" aria-label="Close panel"><X className="size-3" /></Button></SheetClose>
      <div className="min-h-0 flex-1 overflow-hidden [&_[data-mobile-panel-top-row]]:pr-9">{children}</div>
    </SheetContent>
  </Sheet>;

  return (
    <>
      <div
        hidden={hidden}
        aria-label={`Resize ${label} panel`}
        aria-orientation="vertical"
        aria-valuemax={PANEL_MAX_WIDTH}
        aria-valuemin={PANEL_MIN_WIDTH}
        aria-valuenow={width}
        className="relative w-px shrink-0 touch-none cursor-col-resize bg-border transition-colors hover:bg-ring focus-visible:bg-ring focus-visible:outline-none before:absolute before:inset-y-0 before:-left-1 before:w-2"
        onPointerDown={onPointerDown}
        onPointerMove={(event) => { if (drag.current?.pointerId === event.pointerId) resize(drag.current.right - event.clientX); }}
        onPointerUp={stopDrag}
        onPointerCancel={stopDrag}
        onLostPointerCapture={() => { drag.current = null; }}
        onKeyDown={(event) => {
          const nextWidth = { ArrowLeft: width + 16, ArrowRight: width - 16, Home: PANEL_MIN_WIDTH, End: PANEL_MAX_WIDTH }[event.key];
          if (nextWidth === undefined) return;
          event.preventDefault();
          resize(nextWidth);
        }}
        role="separator"
        tabIndex={0}
      />
      <aside
        hidden={hidden}
        aria-label={label}
        className="shrink-0 overflow-hidden border-l bg-background"
        data-file-panel-container={id}
        style={{ width, minWidth: PANEL_MIN_WIDTH }}
      >
        {children}
      </aside>
    </>
  );
}
