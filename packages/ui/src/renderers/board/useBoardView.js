/**
 * The canvas a board is painted on: every flat view's (`kit/viewport/useFlatCanvasView.js` —
 * wheel, a trackpad's two-finger scroll or a pinch to zoom about the pointer, double-click to fit,
 * a tap, a drag and the pointer resting over it for the tool in hand, and the 3D views' pans: the
 * middle or the right button's drag, or a drag with Ctrl, Cmd or Shift; a drag the tool does not
 * take pans too), painting the board from the rasters kept of it
 * (`boardRasters.js`) on its theme's canvas, then what the tools draw over it (`overlay`), in the same
 * frame, so a capture of the canvas holds it too.
 *
 * The whole pane is the board's canvas in the view's theme (`plot2d/theme.js`'s `boardPalette`: the
 * app's light or dark `--background`), which reaches past the board as KiCad's does, and the board
 * is drawn in that theme's palette. A switch of theme draws the rasters again from the payload
 * already held: nothing is asked of the server.
 *
 * The pane says whether what it shows is final — drawn at the scale it is shown at — as
 * `data-board-settled` on its element, written as it paints (no render): a zoom is `false` until
 * the view has rested and been drawn again.
 */
import { useCallback, useEffect, useRef } from "react";
import { clearSurface } from "@cad/core/lib/drawing2d/index.js";
import { boardPalette, drawPlot, fitBoardBounds, fitPlotTransform } from "@cad/core/lib/plot2d/index.js";
import { useFlatCanvasView } from "../kit/viewport/useFlatCanvasView.js";
import { createBoardRasters } from "./boardRasters.js";

/** The canvas around the board, before a board has loaded too: the theme's (`plot2d/theme.js`). */
const surroundColor = (scheme) => boardPalette(scheme).background;

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
 *   and the middle or right button, or a modified drag, pans.
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
    clearSurface(ctx, { width, height, pixelRatio, background: surroundColor(schemeRef.current) });
    const rasters = rastersRef.current;
    if (!rasters || !transform) return;
    const final = rasters.paint(ctx, { transform, width, height, pixelRatio });
    overlayRef.current?.(ctx, { transform, pixelRatio, width, height });
    if (element) element.dataset.boardSettled = final ? "true" : "false";
  }, []);
  // The fit, as its first view and a double-click take it: a board's margin, clear of the tool strip.
  const view = useFlatCanvasView({ content: plot, bounds: plot?.layout.modelBounds ?? null, restored, colorScheme, onViewMoved, paint, onTap, onHover,
    fitBox: fitBoardBounds, clearStrip: true,
    onDrag, middlePan: true, orbitPan: true });
  const { containerRef, schemeRef, requestPaint, paintNow, encode } = view;

  // One raster cache per board, Display and theme: a new revision, a new set of layers or a switch of
  // theme starts afresh, drawn here from the payload already held.
  useEffect(() => {
    if (!plot) return undefined;
    const rasters = createBoardRasters({ layout: plot.layout, onChange: requestPaint, view: drawViewRef.current, theme: colorScheme });
    rastersRef.current = rasters;
    requestPaint();
    return () => {
      if (rastersRef.current === rasters) rastersRef.current = null;
      rasters.dispose();
    };
  }, [plot, requestPaint, drawViewKey, colorScheme]);

  /** Paint the frame final now: the view drawn at its own scale, not a patch scaled while it rests. */
  const settle = useCallback(() => {
    paintNow();
    rastersRef.current?.flush();
    paintNow();
  }, [paintNow]);

  /** The framed view as a PNG, drawn at its own scale first: a capture never waits on a rest. */
  const capture = useCallback(() => { settle(); return encode("board"); }, [settle, encode]);

  /**
   * The board on its own, for a library card: fitted whole to `width` × `height` with the view's
   * margin, drawn as a snapshot draws it but on nothing round it — the board's area in the theme's
   * canvas, the rest clear, so the card's own backdrop is all there is behind the board's shape. It is
   * drawn in both themes from the payload held: the light picture, carrying the dark one as `dark`,
   * which the library keeps beside it and shows in the dark theme (no card turns a board's colours
   * round). The pane's view is left as it is.
   */
  const thumbnail = useCallback(async ({ width, height }) => {
    const current = plotRef.current;
    if (!current) throw new Error("This board has nothing to picture yet.");
    const picture = (theme) => new Promise((resolve, reject) => {
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(width));
      canvas.height = Math.max(1, Math.round(height));
      const context = canvas.getContext("2d");
      if (!context) { reject(new Error("The browser cannot draw the board’s picture.")); return; }
      clearSurface(context, { width: canvas.width, height: canvas.height });
      drawPlot(context, current.layout, { transform: fitPlotTransform(current.layout, canvas.width, canvas.height), backdrop: "board", theme });
      canvas.toBlob((blob) => {
        if (blob) resolve(blob);
        else reject(new Error("The browser could not encode this board as a PNG."));
      }, "image/png");
    });
    const [light, dark] = await Promise.all([picture("light"), picture("dark")]);
    return Object.assign(light, { dark });
  }, []);

  return { containerRef, canvasRef: view.canvasRef, dragging: view.dragging, fit: view.fit, frame: view.frame, capture, thumbnail,
    transformRef: view.transformRef, sizeRef: view.sizeRef, requestPaint };
}
