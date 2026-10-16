import { useCallback, useEffect, useLayoutEffect, useMemo } from "react";
import { BOARD_OVERLAY_COLORS, drawBoardOverlay } from "@text-to-cad/core/lib/board2d/boardOverlay.js";
import { screenToPage } from "@text-to-cad/core/lib/plot2d/index.js";

// How far a pick may miss a small thing (a via, a thin track).
const PICK_SLOP_PX = 4;

/**
 * The pointer on a board's plot, and what it draws over it: the layer the plot's view takes
 * (`usePlotView`'s `setLayer`), made from the view's handle. A press picks by Select's mode (by
 * the side looked at too); a double-click on something selects it and copies its reference, as on
 * a STEP face (on bare board, the view fits).
 *
 * The overlay is drawn in the plot's own frame: what is isolated first, everything else stepped back
 * (`useBoardIsolation.js`), then the hover and the selection (a net in focus steps the rest back).
 *
 * @param {object} options
 * @param {{ transformRef: { current: object | null }, canvasRef: { current: HTMLCanvasElement | null },
 *   requestPaint: () => void, setLayer: (layer: object | null) => void }} options.view  The plot's view.
 * @param {object | null} options.index
 * @param {{ x: number, y: number, width: number } | null} options.sheet  The plot's sheet.
 * @param {ReturnType<typeof import("./useBoardSelection.js").useBoardSelection>} options.selection
 * @param {readonly object[]} options.isolated  What is isolated, resolved.
 * @param {"top"|"bottom"} [options.side]  The side the board is looked at from: bottom is mirrored.
 * @param {boolean} [options.placement]  A board's Placement display: the overlay draws its pads and airwires.
 * @param {(selectors: string[]) => void} options.onCopy  A double-click's copy of a reference.
 */
export function useBoardPicking({ view, index, sheet, selection, isolated, side = "top", placement = false, onCopy }) {
  const { transformRef, canvasRef, requestPaint, setLayer } = view;
  // Seen from below, the board is mirrored about its sheet's middle.
  const mirrorX = side === "bottom" && sheet ? sheet.x + sheet.width / 2 : null;

  // ---- what the canvas draws over the plot -------------------------------------
  // A new overlay is a new layer, which the view paints; the hover is read from its ref, so a
  // pointer move repaints without a render.
  const { resolved, dim, hoverRef } = selection;
  const overlay = useCallback((ctx, frame) => {
    if (!index || !frame.transform) return;
    const base = { transform: frame.transform, pixelRatio: frame.pixelRatio, width: frame.width, height: frame.height, mirrorX };
    if (isolated.length) {
      drawBoardOverlay(ctx, index, { ...base, dim: true, selection: isolated, colors: { ...BOARD_OVERLAY_COLORS, selection: BOARD_OVERLAY_COLORS.hover } });
    }
    drawBoardOverlay(ctx, index, { ...base, hover: hoverRef.current, selection: resolved, dim: dim && !isolated.length, placement });
  }, [index, isolated, hoverRef, resolved, dim, mirrorX, placement]);

  // ---- from the pane to the board ---------------------------------------------
  const toPage = useCallback(({ x, y }) => {
    const transform = transformRef.current;
    if (!transform) return null;
    const [px, py] = screenToPage(transform, x, y);
    return [mirrorX == null ? px : 2 * mirrorX - px, py];
  }, [transformRef, mirrorX]);
  const { selectMode } = selection;
  const pickAt = useCallback((point) => {
    const page = index && toPage(point);
    const scale = transformRef.current?.scale || 1;
    return page ? index.pick(page, { mode: selectMode, view: mirrorX == null ? "top" : "bottom", tolerance: PICK_SLOP_PX / scale }) : null;
  }, [index, toPage, transformRef, selectMode, mirrorX]);

  // ---- the pointer ------------------------------------------------------------
  const setCursor = useCallback((value) => { if (canvasRef.current) canvasRef.current.style.cursor = value; }, [canvasRef]);
  // A new document starts with the canvas's own cursor, and without the last one's hover.
  useEffect(() => { setCursor(""); requestPaint(); }, [index, setCursor, requestPaint]);
  const { hoverHit, select, clear } = selection;
  const picking = useMemo(() => ({
    onHover(point) {
      if (!index) return;
      const hit = point ? pickAt(point) : null;
      if (hoverHit(hit)) setCursor(hit ? "pointer" : "");
    },
    onTap(point, event) {
      if (!index) return;
      const hit = pickAt(point);
      const add = Boolean(event?.shiftKey || event?.metaKey || event?.ctrlKey);
      if (hit) select([hit.selector], { add });
      else if (!add) clear();
    },
    onDoubleTap(point) {
      if (!index) return false;
      const hit = pickAt(point);
      if (!hit) return false;
      select([hit.selector]);
      onCopy([hit.selector]);
      return true;
    },
  }), [index, pickAt, hoverHit, select, clear, onCopy, setCursor]);

  const layer = useMemo(() => (index ? { overlay, picking } : null), [index, overlay, picking]);
  useLayoutEffect(() => { setLayer(layer); }, [setLayer, layer]);
  useLayoutEffect(() => () => setLayer(null), [setLayer]);
  return { mirrored: mirrorX != null };
}
