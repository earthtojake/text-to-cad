/**
 * The canvas a plot is painted on: the kit's flat-picture view (`kit/plane/usePlaneView.js` —
 * drag to pan, wheel or pinch to zoom about the pointer, double-click to fit), painting the
 * plot's sheets from the rasters kept of them (`plotRasters.js`) on the theme's background.
 *
 * Each sheet is drawn on its own background, the one its tool draws it on; only the surround is
 * the theme's, so a theme flip repaints the surround and redraws nothing.
 *
 * The pane says whether what it shows is final — drawn at the scale it is shown at — as
 * `data-plot-settled` on its element, written as it paints (no render): a zoom is `false` until
 * the view has rested and been drawn again.
 */
import { useCallback, useEffect, useMemo, useRef } from "react";
import { clearSurface } from "@text-to-cad/core/lib/drawing2d/index.js";
import { drawPlot, fitPlotTransform, sheetImages } from "@text-to-cad/core/lib/plot2d/index.js";
import { usePlaneView } from "../kit/plane/usePlaneView.js";
import { readThemeColors } from "../kit/plane/themeColors.js";
import { createPlotRasters } from "./plotRasters.js";

/**
 * @param {object} options
 * @param {{ layout: object, images: readonly CanvasImageSource[] }|null} options.plot  A laid-out plot
 *   with its sheets decoded, or null while it loads.
 * @param {{ scale: number, offsetX: number, offsetY: number }|null} options.restored
 *   The view this file was left at, when it was left anywhere but the fit.
 * @param {"light"|"dark"} options.colorScheme
 * @param {(transform: object|null) => void} options.onViewMoved  The view to remember, or null for the fit.
 * @param {string} options.noun  What the plot is called ("board", "schematic").
 * @param {{ layers: string[]|null, poured: boolean, side: "top"|"bottom" }|null} [options.drawView]  A
 *   board's Display, as `drawPlot`'s `view`; a new one draws the plot afresh.
 */
export function usePlotView({ plot, restored = null, colorScheme = "light", onViewMoved, noun, drawView = null }) {
  const plotRef = useRef(plot);
  plotRef.current = plot;
  const rastersRef = useRef(null);
  // A board's Display (side, layers, pours): a new one is a new raster cache.
  const drawViewRef = useRef(drawView);
  drawViewRef.current = drawView;
  const drawViewKey = JSON.stringify(drawView);
  // What a person points at, over the plot (`setLayer`): made after the view, from its handle.
  const layerRef = useRef(null);
  const paint = useCallback((ctx, frame) => {
    const { width, height, pixelRatio, transform, element, colorScheme: scheme } = frame;
    clearSurface(ctx, { width, height, pixelRatio, background: readThemeColors(element, scheme).background });
    const rasters = rastersRef.current;
    if (!rasters || !transform) return;
    const final = rasters.paint(ctx, { transform, width, height, pixelRatio });
    layerRef.current?.overlay?.(ctx, frame);
    if (element) element.dataset.plotSettled = final ? "true" : "false";
  }, []);
  // The plane view's pointing, handed on to the layer of the moment (none: a press only pans).
  const picking = useMemo(() => ({
    onHover: (point, event) => layerRef.current?.picking?.onHover?.(point, event),
    onTap: (point, event) => layerRef.current?.picking?.onTap?.(point, event),
    onDoubleTap: (point, event) => Boolean(layerRef.current?.picking?.onDoubleTap?.(point, event)),
  }), []);
  const view = usePlaneView({
    content: plot, bounds: plot?.layout.modelBounds ?? null, restored, colorScheme, onViewMoved, paint, noun, picking
  });
  const { containerRef, paintNow, requestPaint, schemeRef } = view;

  // One raster cache per plot: a new revision starts afresh, and the old one's canvases go with it.
  useEffect(() => {
    if (!plot) return undefined;
    const rasters = createPlotRasters({ layout: plot.layout, images: plot.images, onChange: requestPaint, view: drawViewRef.current });
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
  const capture = useCallback(() => {
    settle();
    return view.capture();
  }, [settle, view.capture]);

  /**
   * The plot on its own, for a library card: fitted whole to `width` × `height`, each sheet's SVG
   * drawn as a snapshot draws it, on the theme's background — the pane's view is left as it is.
   */
  const thumbnail = useCallback(({ width, height }) => new Promise((resolve, reject) => {
    const current = plotRef.current;
    if (!current) { reject(new Error(`This ${noun} has nothing to picture yet.`)); return; }
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width));
    canvas.height = Math.max(1, Math.round(height));
    const context = canvas.getContext("2d");
    if (!context) { reject(new Error(`The browser cannot draw the ${noun}’s picture.`)); return; }
    clearSurface(context, { width: canvas.width, height: canvas.height,
      background: readThemeColors(containerRef.current, schemeRef.current).background });
    drawPlot(context, current.layout, {
      transform: fitPlotTransform(current.layout, canvas.width, canvas.height),
      images: sheetImages(current.layout, current.images)
    });
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error(`The browser could not encode this ${noun} as a PNG.`));
    }, "image/png");
  }), [containerRef, schemeRef, noun]);

  /**
   * The layer over the plot, or null: `overlay(ctx, frame)` is drawn in the plot's own frame, at its
   * view (so a capture shows it), and `picking` takes the pane's taps, hover and double-taps.
   */
  const setLayer = useCallback((layer) => { layerRef.current = layer; requestPaint(); }, [requestPaint]);

  return {
    containerRef, canvasRef: view.canvasRef, dragging: view.dragging, fit: view.fit, capture, thumbnail,
    transformRef: view.transformRef, requestPaint, paintNow, settle, setView: view.setView, setLayer
  };
}
