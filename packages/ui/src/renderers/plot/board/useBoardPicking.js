import { useCallback, useEffect, useLayoutEffect, useMemo } from "react";
import { BOARD_OVERLAY_COLORS, SCHEMATIC_OVERLAY_COLORS, drawBoardOverlay } from "@text-to-cad/core/lib/board2d/boardOverlay.js";
import { screenToPage } from "@text-to-cad/core/lib/plot2d/index.js";
import { PLOT_TOOL } from "../tools.js";

// How far a pick may miss a small thing (a via, a thin track), and how far Measure reaches to snap.
const PICK_SLOP_PX = 4;
const SNAP_PX = 10;
const MEASURE_KINDS = Object.freeze({ all: null, pads: ["pads"], copper: ["copper"], outline: ["outline"] });

/**
 * The pointer on a board's or a schematic's plot, and what it draws over it: the layer the plot's
 * view takes (`usePlotView`'s `setLayer`), made from the view's handle. A press picks by Select's
 * mode (by the side looked at too, on a board) or snaps Measure's point; a double-click on something
 * selects it and copies its reference, as on a STEP face (on bare board, the view fits).
 *
 * The overlay is drawn in the plot's own frame: what is isolated first, everything else stepped back
 * (`useBoardIsolation.js`), then the hover, the selection (a net or a check in focus steps the rest
 * back), a check's markers and the measurements.
 *
 * @param {object} options
 * @param {{ transformRef: { current: object | null }, canvasRef: { current: HTMLCanvasElement | null },
 *   requestPaint: () => void, setLayer: (layer: object | null) => void }} options.view  The plot's view.
 * @param {object | null} options.index
 * @param {{ x: number, y: number, width: number } | null} options.sheet  The plot's first sheet: a board's.
 * @param {string} options.toolMode
 * @param {ReturnType<typeof import("./useBoardSelection.js").useBoardSelection>} options.selection
 * @param {ReturnType<typeof import("./useBoardMeasure.js").useBoardMeasure>} options.measure
 * @param {readonly object[]} options.isolated  What is isolated, resolved.
 * @param {"top"|"bottom"} [options.side]  The side the board is looked at from: bottom is mirrored.
 * @param {boolean} [options.placement]  A board's Placement display: the overlay draws its pads and airwires.
 * @param {(selectors: string[]) => void} options.onCopy  A double-click's copy of a reference.
 */
export function useBoardPicking({ view, index, sheet, toolMode, selection, measure, isolated, side = "top", placement = false, onCopy }) {
  const { transformRef, canvasRef, requestPaint, setLayer } = view;
  // Only a board is seen from below: mirrored about its sheet's middle.
  const mirrorX = index?.document === "board" && side === "bottom" && sheet ? sheet.x + sheet.width / 2 : null;

  // ---- what the canvas draws over the plot -------------------------------------
  // A new overlay is a new layer, which the view paints; the hover and Measure's draft are read
  // from their refs, so a pointer move repaints without a render.
  const { resolved, dim, markers, hoverRef } = selection;
  const { start, measurements, draftRef } = measure;
  const overlay = useCallback((ctx, frame) => {
    if (!index || !frame.transform) return;
    const base = { transform: frame.transform, pixelRatio: frame.pixelRatio, width: frame.width, height: frame.height, mirrorX };
    if (isolated.length) {
      const colors = index.document === "schematic" ? SCHEMATIC_OVERLAY_COLORS : BOARD_OVERLAY_COLORS;
      drawBoardOverlay(ctx, index, { ...base, dim: true, selection: isolated, colors: { ...colors, selection: colors.hover } });
    }
    drawBoardOverlay(ctx, index, {
      ...base, hover: hoverRef.current, selection: resolved, dim: dim && !isolated.length, markers,
      measure: start ? { points: [start.page], draft: draftRef.current?.page ?? null } : null, placement,
    });
    for (const measurement of measurements) drawBoardOverlay(ctx, index, { ...base, measure: { points: [measurement.a.page, measurement.b.page] } });
  }, [index, isolated, hoverRef, resolved, dim, markers, start, draftRef, measurements, mirrorX, placement]);

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
  const measureMode = measure.mode;
  const snapAt = useCallback((point) => {
    const page = index?.snap && toPage(point);
    if (!page) return null;
    const scale = transformRef.current?.scale || 1;
    const snapped = index.snap(page, { tolerance: SNAP_PX / scale, kinds: MEASURE_KINDS[measureMode] ?? null });
    if (snapped) return { page: snapped.at, label: snapped.label, selector: snapped.selector || index.pointSelector(snapped.at) };
    return { page, label: "", selector: index.pointSelector(page) };
  }, [index, toPage, transformRef, measureMode]);

  // ---- the pointer ------------------------------------------------------------
  const setCursor = useCallback((value) => { if (canvasRef.current) canvasRef.current.style.cursor = value; }, [canvasRef]);
  // A new tool starts with the canvas's own cursor, and without the last one's hover.
  useEffect(() => { setCursor(""); requestPaint(); }, [toolMode, setCursor, requestPaint]);
  const { hoverHit, select, clear } = selection;
  const { pick, draft } = measure;
  const picking = useMemo(() => ({
    onHover(point) {
      if (!index) return;
      if (toolMode === PLOT_TOOL.MEASURE) {
        setCursor("crosshair");
        if (draft(point ? snapAt(point) : null)) requestPaint();
        return;
      }
      const hit = point ? pickAt(point) : null;
      if (hoverHit(hit)) setCursor(hit ? "pointer" : "");
    },
    onTap(point, event) {
      if (!index) return;
      if (toolMode === PLOT_TOOL.MEASURE) { pick(snapAt(point)); return; }
      const hit = pickAt(point);
      const add = Boolean(event?.shiftKey || event?.metaKey || event?.ctrlKey);
      if (hit) select([hit.selector], { add });
      else if (!add) clear();
    },
    onDoubleTap(point) {
      if (!index || toolMode !== PLOT_TOOL.SELECT) return false;
      const hit = pickAt(point);
      if (!hit) return false;
      select([hit.selector]);
      onCopy([hit.selector]);
      return true;
    },
  }), [index, toolMode, pickAt, snapAt, pick, draft, hoverHit, select, clear, onCopy, setCursor, requestPaint]);

  const layer = useMemo(() => (index ? { overlay, picking } : null), [index, overlay, picking]);
  useLayoutEffect(() => { setLayer(layer); }, [setLayer, layer]);
  useLayoutEffect(() => () => setLayer(null), [setLayer]);
  return { mirrored: mirrorX != null };
}
