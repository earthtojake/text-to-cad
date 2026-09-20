import { useRef } from "react";

/**
 * The file surface's panel column: the one frame every panel is drawn in.
 *
 * There is one of these beside a file and never two, because there is one
 * open panel (`panels.js`). Whatever is in it — the file tree or the CAD
 * Inspector — gets the same border, the same width and the
 * same handle, which is the point: they used to be two columns of two
 * designs, a file list on the left and the viewer's own aside on the right,
 * each with its own idea of how wide a panel is.
 *
 * No title bar. Each panel's own top row is its header — the tree's filter,
 * the Inspector's tabs — and the nav row's toggle is how it closes. A
 * title above a tab bar would be a second name for the same thing.
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
// Fits Features / Motion / View and the zoom readout without scrolling.
export const PANEL_MIN_WIDTH = 256;
export const PANEL_MAX_WIDTH = 480;
export const PANEL_DEFAULT_WIDTH = 320;

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
 * @param {number} props.width
 * @param {(width: number) => void} props.onWidthChange
 * @param {() => void} [props.onCollapse]
 * @param {import("react").ReactNode} props.children
 */
export function FilePanelColumn({ id, label, width, onWidthChange, onCollapse, children }) {
  const drag = useRef(null);
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

  return (
    <>
      <div
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
