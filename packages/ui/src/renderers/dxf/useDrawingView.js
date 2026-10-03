/**
 * The canvas a drawing is painted on: the kit's flat-picture view (`kit/plane/usePlaneView.js`
 * — drag to pan, wheel or pinch to zoom about the pointer, double-click to fit), painting a
 * prepared drawing in the theme's pens on the theme's background.
 *
 * A drawing's default pen (ACI 7, `color: null`) is the theme's `--foreground` and its
 * background the theme's `--background`, both read at DRAW time off the pane: one payload
 * serves both themes, and a theme flip is a repaint.
 */
import { useCallback, useRef } from "react";
import { clearSurface, drawDrawing, fitTransform } from "@text-to-cad/core/lib/drawing2d/index.js";
import { usePlaneView } from "../kit/plane/usePlaneView.js";
import { readThemeColors } from "../kit/plane/themeColors.js";

/**
 * @param {object} options
 * @param {object|null} options.drawing  A prepared drawing, or null while it loads.
 * @param {{ scale: number, offsetX: number, offsetY: number }|null} options.restored
 *   The view this file was left at, when it was left anywhere but the fit.
 * @param {"light"|"dark"} options.colorScheme
 * @param {(transform: object|null) => void} options.onViewMoved  Called after the person moves the
 *   view, with the transform to remember. Never called for a fit.
 */
export function useDrawingView({ drawing, restored = null, colorScheme = "light", onViewMoved }) {
  const drawingRef = useRef(drawing);
  drawingRef.current = drawing;
  const paint = useCallback((ctx, { width, height, pixelRatio, transform, element, colorScheme: scheme }) => {
    const { background, foreground } = readThemeColors(element, scheme);
    clearSurface(ctx, { width, height, pixelRatio, background });
    const drawable = drawingRef.current;
    if (drawable && transform) {
      drawDrawing(ctx, drawable, { transform, foreground, pixelRatio });
    }
  }, []);
  const view = usePlaneView({
    content: drawing, bounds: drawing?.bounds ?? null, restored, colorScheme, onViewMoved, paint, noun: "drawing"
  });
  const { containerRef, schemeRef } = view;

  /**
   * The drawing on its own, for a library card: fitted whole to `width` × `height`, in the theme's
   * pens on its background, painted on a canvas of its own — the pane's view is left as it is.
   */
  const thumbnail = useCallback(({ width, height }) => new Promise((resolve, reject) => {
    const drawable = drawingRef.current;
    if (!drawable?.bounds) { reject(new Error("This drawing has nothing to picture.")); return; }
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width));
    canvas.height = Math.max(1, Math.round(height));
    const context = canvas.getContext("2d");
    if (!context) { reject(new Error("The browser cannot draw the drawing's picture.")); return; }
    const { background, foreground } = readThemeColors(containerRef.current, schemeRef.current);
    clearSurface(context, { width: canvas.width, height: canvas.height, background });
    drawDrawing(context, drawable, { transform: fitTransform(drawable.bounds, canvas.width, canvas.height), foreground });
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("The browser could not encode this drawing as a PNG."));
    }, "image/png");
  }), [containerRef, schemeRef]);

  return {
    containerRef, canvasRef: view.canvasRef, dragging: view.dragging, fit: view.fit, zoomBy: view.zoomBy,
    capture: view.capture, thumbnail, transformRef: view.transformRef
  };
}
