/**
 * The canvas a board is painted on: every flat view's (`kit/viewport/useFlatCanvasView.js` —
 * drag to pan, wheel or pinch to zoom about the pointer, double-click to fit, a tap and the
 * pointer resting over it for the tool in hand), painting the board from the rasters kept of it
 * (`boardRasters.js`) on the theme's background, then what the tools draw over it (`overlay`), in
 * the same frame, so a capture of the canvas holds it too.
 *
 * The sheet is drawn on its own background, KiCad's board colour; only the surround is the
 * theme's, so a theme flip repaints the surround and redraws nothing.
 *
 * The pane says whether what it shows is final — drawn at the scale it is shown at — as
 * `data-board-settled` on its element, written as it paints (no render): a zoom is `false` until
 * the view has rested and been drawn again.
 */
import { useCallback, useEffect, useRef } from "react";
import { APP_THEME_COLORS } from "@text-to-cad/core/lib/appTheme.js";
import { clearSurface } from "@text-to-cad/core/lib/drawing2d/index.js";
import { drawPlot, fitPlotTransform } from "@text-to-cad/core/lib/plot2d/index.js";
import { cssColorToHex } from "../kit/look/chromeBackdrop.js";
import { useFlatCanvasView } from "../kit/viewport/useFlatCanvasView.js";
import { createBoardRasters } from "./boardRasters.js";

/** The theme's background around the board, read at draw time off the pane's own element. */
function surroundColor(element, colorScheme) {
  const fallback = (colorScheme === "dark" ? APP_THEME_COLORS.dark : APP_THEME_COLORS.light).background;
  try {
    const value = element?.ownerDocument?.defaultView?.getComputedStyle(element).getPropertyValue("--background").trim();
    return cssColorToHex(value || "") || fallback;
  } catch {
    return fallback;
  }
}

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
 */
export function useBoardView({ plot, restored = null, colorScheme = "light", onViewMoved, drawView = null, overlay = null, onTap = null, onHover = null }) {
  const plotRef = useRef(plot);
  plotRef.current = plot;
  const rastersRef = useRef(null);
  const drawViewRef = useRef(drawView);
  drawViewRef.current = drawView;
  const drawViewKey = JSON.stringify(drawView);
  const overlayRef = useRef(overlay);
  overlayRef.current = overlay;
  const paint = useCallback((ctx, { width, height, pixelRatio, transform, element, colorScheme: scheme }) => {
    clearSurface(ctx, { width, height, pixelRatio, background: surroundColor(element, scheme) });
    const rasters = rastersRef.current;
    if (!rasters || !transform) return;
    const final = rasters.paint(ctx, { transform, width, height, pixelRatio });
    overlayRef.current?.(ctx, { transform, pixelRatio, width, height });
    if (element) element.dataset.boardSettled = final ? "true" : "false";
  }, []);
  const view = useFlatCanvasView({ content: plot, bounds: plot?.layout.modelBounds ?? null, restored, colorScheme, onViewMoved, paint, onTap, onHover });
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
   * snapshot draws it, on the theme's background — the pane's view is left as it is.
   */
  const thumbnail = useCallback(({ width, height }) => new Promise((resolve, reject) => {
    const current = plotRef.current;
    if (!current) { reject(new Error("This board has nothing to picture yet.")); return; }
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width));
    canvas.height = Math.max(1, Math.round(height));
    const context = canvas.getContext("2d");
    if (!context) { reject(new Error("The browser cannot draw the board’s picture.")); return; }
    clearSurface(context, { width: canvas.width, height: canvas.height, background: surroundColor(containerRef.current, schemeRef.current) });
    drawPlot(context, current.layout, { transform: fitPlotTransform(current.layout, canvas.width, canvas.height) });
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("The browser could not encode this board as a PNG."));
    }, "image/png");
  }), [containerRef, schemeRef]);

  return { containerRef, canvasRef: view.canvasRef, dragging: view.dragging, fit: view.fit, capture, thumbnail,
    transformRef: view.transformRef, sizeRef: view.sizeRef, requestPaint };
}
