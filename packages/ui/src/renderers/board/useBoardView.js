/**
 * The canvas a board is painted on: every flat view's (`kit/viewport/useFlatCanvasView.js` —
 * wheel or pinch to zoom about the pointer, double-click to fit, a tap, a drag and the pointer
 * resting over it for the tool in hand, and a pan with the middle button or with Space held, as
 * KiCad's; a drag the tool does not take pans too), painting the board from the rasters kept of it
 * (`boardRasters.js`) on KiCad's canvas, then what the tools draw over it (`overlay`), in the same
 * frame, so a capture of the canvas holds it too.
 *
 * The whole pane is the board's background, KiCad's canvas colour, whatever the theme: KiCad draws
 * a board on its page on one dark canvas, and the drawing sheet's page reaches past the board.
 *
 * The pane says whether what it shows is final — drawn at the scale it is shown at — as
 * `data-board-settled` on its element, written as it paints (no render): a zoom is `false` until
 * the view has rested and been drawn again.
 */
import { useCallback, useEffect, useRef } from "react";
import { clearSurface } from "@cad/core/lib/drawing2d/index.js";
import { drawPlot, fitPlotTransform } from "@cad/core/lib/plot2d/index.js";
import { useFlatCanvasView } from "../kit/viewport/useFlatCanvasView.js";
import { createBoardRasters } from "./boardRasters.js";

/** KiCad's canvas around the board: the board's own background, before a board has loaded too. */
const KICAD_CANVAS = "#001023";
const surroundColor = (plot) => plot?.layout.sheets[0]?.background || KICAD_CANVAS;

/**
 * @param {object} options
 * @param {{ layout: object }|null} options.plot  A laid-out board, or null while it loads.
 * @param {{ scale: number, offsetX: number, offsetY: number }|null} options.restored
 * @param {"light"|"dark"} options.colorScheme
 * @param {(transform: object|null) => void} options.onViewMoved
 * @param {{ layers: string[], poured: boolean, side: "top"|"bottom" }|null} [options.drawView]  The board's Display
 *   (`plot2d/boardDisplay.js`'s `boardDrawView`), as `drawPlot`'s `view`; a new one draws the board afresh.
 * @param {(ctx: CanvasRenderingContext2D, frame: { transform: object, pixelRatio: number, width: number, height: number }) => void} [options.overlay]
 * @param {(point: { x: number, y: number }, event: PointerEvent) => void} [options.onTap]
 * @param {(point: { x: number, y: number } | null, event: PointerEvent | null) => void} [options.onHover]
 * @param {Parameters<typeof useFlatCanvasView>[0]["onDrag"]} [options.onDrag]  Select's box: a drag is the area it names,
 *   and the middle button, or Space held, pans.
 */
export function useBoardView({ plot, restored = null, colorScheme = "light", onViewMoved, drawView = null, overlay = null, onTap = null, onHover = null,
  onDrag = null }) {
  const plotRef = useRef(plot);
  plotRef.current = plot;
  const rastersRef = useRef(null);
  const drawViewRef = useRef(drawView);
  drawViewRef.current = drawView;
  const drawViewKey = JSON.stringify(drawView);
  const overlayRef = useRef(overlay);
  overlayRef.current = overlay;
  const paint = useCallback((ctx, { width, height, pixelRatio, transform, element }) => {
    clearSurface(ctx, { width, height, pixelRatio, background: surroundColor(plotRef.current) });
    const rasters = rastersRef.current;
    if (!rasters || !transform) return;
    const final = rasters.paint(ctx, { transform, width, height, pixelRatio });
    overlayRef.current?.(ctx, { transform, pixelRatio, width, height });
    if (element) element.dataset.boardSettled = final ? "true" : "false";
  }, []);
  const view = useFlatCanvasView({ content: plot, bounds: plot?.layout.modelBounds ?? null, restored, colorScheme, onViewMoved, paint, onTap, onHover,
    onDrag, middlePan: true, spacePan: true });
  const { containerRef, schemeRef, requestPaint, paintNow, encode } = view;

  // One raster cache per board and Display: a new revision or a new set of layers starts afresh.
  useEffect(() => {
    if (!plot) return undefined;
    const rasters = createBoardRasters({ layout: plot.layout, onChange: requestPaint, view: drawViewRef.current });
    rastersRef.current = rasters;
    requestPaint();
    return () => {
      if (rastersRef.current === rasters) rastersRef.current = null;
      rasters.dispose();
    };
  }, [plot, requestPaint, drawViewKey]);

  /** Paint the frame final now: the view drawn at its own scale, not a patch scaled while it rests. */
  const settle = useCallback(() => {
    paintNow();
    rastersRef.current?.flush();
    paintNow();
  }, [paintNow]);

  /** The framed view as a PNG, drawn at its own scale first: a capture never waits on a rest. */
  const capture = useCallback(() => { settle(); return encode("board"); }, [settle, encode]);

  /**
   * The board on its own, for a library card: fitted whole to `width` × `height`, drawn as a
   * snapshot draws it, on KiCad's canvas — the pane's view is left as it is.
   */
  const thumbnail = useCallback(({ width, height }) => new Promise((resolve, reject) => {
    const current = plotRef.current;
    if (!current) { reject(new Error("This board has nothing to picture yet.")); return; }
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width));
    canvas.height = Math.max(1, Math.round(height));
    const context = canvas.getContext("2d");
    if (!context) { reject(new Error("The browser cannot draw the board’s picture.")); return; }
    clearSurface(context, { width: canvas.width, height: canvas.height, background: surroundColor(current) });
    drawPlot(context, current.layout, { transform: fitPlotTransform(current.layout, canvas.width, canvas.height) });
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("The browser could not encode this board as a PNG."));
    }, "image/png");
  }), []);

  return { containerRef, canvasRef: view.canvasRef, dragging: view.dragging, panReady: view.panReady, fit: view.fit, capture, thumbnail,
    transformRef: view.transformRef, sizeRef: view.sizeRef, requestPaint };
}
