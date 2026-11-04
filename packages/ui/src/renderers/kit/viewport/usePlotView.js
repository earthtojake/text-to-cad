/**
 * The canvas a plot is painted on — a board, a schematic's sheet (`@cad/core`'s `plot2d`): every flat
 * view's (`useFlatCanvasView.js` — wheel, a trackpad's two-finger scroll or a pinch to zoom about the
 * pointer, double-click to fit, a tap, a drag and the pointer resting over it for the tool in hand, and
 * the 3D views' pans: the middle or the right button's drag, or a drag with Ctrl, Cmd or Shift; a drag
 * the tool does not take pans too), painting the plot from the rasters kept of it (`plotRasters.js`) on
 * the pane's surround, then what the tools draw over it (`overlay`), in the same frame, so a capture of
 * the canvas holds it too.
 *
 * The surround is the renderer's (`surround(colorScheme)`): a board's is its own dark canvas whatever
 * the theme; a schematic's sheet lies on the app's neutral background, its paper drawn by the plot.
 *
 * The pane says whether what it shows is final — drawn at the scale it is shown at — as
 * `data-board-settled` on its element, written as it paints (no render): a zoom is `false` until
 * the view has rested and been drawn again.
 */
import { useCallback, useEffect, useRef } from "react";
import { clearSurface } from "@cad/core/lib/drawing2d/index.js";
import { drawPlot, fitBoardBounds, fitPlotTransform } from "@cad/core/lib/plot2d/index.js";
import { useFlatCanvasView } from "./useFlatCanvasView.js";
import { createPlotRasters } from "./plotRasters.js";

/**
 * @param {object} options
 * @param {{ layout: object }|null} options.plot  A laid-out plot, or null while it loads.
 * @param {{ scale: number, offsetX: number, offsetY: number }|null} options.restored
 * @param {"light"|"dark"} options.colorScheme
 * @param {(colorScheme: "light"|"dark", plot: object|null) => string} options.surround  The pane round the plot.
 * @param {string} options.noun  What a capture's or a card's error names ("board").
 * @param {(transform: object|null) => void} options.onViewMoved
 * @param {object|null} [options.drawView]  `drawPlot`'s `view`; a new one draws the plot afresh.
 * @param {(ctx: CanvasRenderingContext2D, frame: { transform: object, pixelRatio: number, width: number, height: number }) => void} [options.overlay]
 * @param {(point: { x: number, y: number }, event: PointerEvent) => void} [options.onTap]
 * @param {(point: { x: number, y: number } | null, event: PointerEvent | null) => void} [options.onHover]
 * @param {Parameters<typeof useFlatCanvasView>[0]["onDrag"]} [options.onDrag]  Select's box.
 * @param {Parameters<typeof useFlatCanvasView>[0]["onDoubleTap"]} [options.onDoubleTap]  A double-click the tool takes (a sheet entered), else the fit.
 */
export function usePlotView({ plot, restored = null, colorScheme = "light", surround, noun = "board", onViewMoved, drawView = null, overlay = null,
  onTap = null, onHover = null, onDrag = null, onDoubleTap = null }) {
  const plotRef = useRef(plot);
  plotRef.current = plot;
  const surroundRef = useRef(surround);
  surroundRef.current = surround;
  const rastersRef = useRef(null);
  const drawViewRef = useRef(drawView);
  drawViewRef.current = drawView;
  const drawViewKey = JSON.stringify(drawView);
  const overlayRef = useRef(overlay);
  overlayRef.current = overlay;
  const paint = useCallback((ctx, { width, height, pixelRatio, transform, element, colorScheme: scheme }) => {
    clearSurface(ctx, { width, height, pixelRatio, background: surroundRef.current(scheme, plotRef.current) });
    const rasters = rastersRef.current;
    if (!rasters || !transform) return;
    const final = rasters.paint(ctx, { transform, width, height, pixelRatio });
    overlayRef.current?.(ctx, { transform, pixelRatio, width, height });
    if (element) element.dataset.boardSettled = final ? "true" : "false";
  }, []);
  // The fit, as its first view and a double-click take it: a board's margin, clear of the tool strip.
  const view = useFlatCanvasView({ content: plot, bounds: plot?.layout.modelBounds ?? null, restored, colorScheme, onViewMoved, paint, onTap, onHover,
    fitBox: fitBoardBounds, clearStrip: true, onDrag, onDoubleTap, middlePan: true, orbitPan: true });
  const { requestPaint, paintNow, encode } = view;

  // One raster cache per plot and view: a new revision or a new set of layers starts afresh.
  useEffect(() => {
    if (!plot) return undefined;
    const rasters = createPlotRasters({ layout: plot.layout, onChange: requestPaint, view: drawViewRef.current });
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
  const capture = useCallback(() => { settle(); return encode(noun); }, [settle, encode, noun]);

  /**
   * The plot on its own, for a library card: fitted whole to `width` × `height` with the view's
   * margin, drawn as a snapshot draws it but on nothing round it — a board's area in its canvas
   * colour, a sheet's paper, the rest clear, so the card's own backdrop is all there is behind it, in
   * either theme, as a STEP's or a drawing's card picture is. The pane's view is left as it is.
   */
  const thumbnail = useCallback(({ width, height }) => new Promise((resolve, reject) => {
    const current = plotRef.current;
    if (!current) { reject(new Error(`This ${noun} has nothing to picture yet.`)); return; }
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width));
    canvas.height = Math.max(1, Math.round(height));
    const context = canvas.getContext("2d");
    if (!context) { reject(new Error(`The browser cannot draw the ${noun}’s picture.`)); return; }
    clearSurface(context, { width: canvas.width, height: canvas.height });
    drawPlot(context, current.layout, { transform: fitPlotTransform(current.layout, canvas.width, canvas.height), backdrop: "board" });
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error(`The browser could not encode this ${noun} as a PNG.`));
    }, "image/png");
  }), [noun]);

  return { containerRef: view.containerRef, canvasRef: view.canvasRef, dragging: view.dragging, fit: view.fit, frame: view.frame, capture, thumbnail,
    transformRef: view.transformRef, sizeRef: view.sizeRef, requestPaint };
}
