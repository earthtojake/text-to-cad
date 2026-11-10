/**
 * The canvas a drawing is painted on: every flat view's (`../kit/viewport/useFlatCanvasView.js` — a
 * mouse's wheel or a pinch to zoom about the pointer, a trackpad's two-finger scroll to pan, a drag to
 * pan where Select's box does not take it, the 3D views' pans too (the middle or the right button's drag, or a drag with Ctrl, Cmd or
 * Shift), double-click to fit, a tap and the pointer resting over it for the tool in hand), painting
 * the drawing on the theme's background in the theme's pen, without the layers hidden, then what the
 * tools draw over it (`overlay`, a highlight and ink) in the same frame, so a capture of the canvas
 * holds it too. The fit is every flat view's, a board's and a schematic's: their margin (`fitBoardBounds`,
 * 6% of the pane's shorter side, at least 16px), clear of the view's tool strip.
 */
import { useCallback, useEffect, useRef } from "react";
import { clearSurface, drawDrawing, fitTransform } from "@cad/core/lib/drawing2d/index.js";
import { fitBoardBounds } from "@cad/core/lib/plot2d/index.js";
import { useFlatCanvasView } from "../kit/viewport/useFlatCanvasView.js";
import { DRAWING_THEME_FALLBACK, readDrawingThemeColors } from "./themeColors.js";

const NO_LAYERS = new Set();

/**
 * @param {object} options
 * @param {object|null} options.drawing  A prepared drawing, or null while it loads.
 * @param {{ scale: number, offsetX: number, offsetY: number }|null} options.restored
 *   The view this file was left at, when it was left anywhere but the fit.
 * @param {"light"|"dark"} options.colorScheme
 * @param {(transform: object|null) => void} options.onViewMoved  Called after the person moves the
 *   view, with the transform to remember; with null when it is the fit again.
 * @param {ReadonlySet<string>} [options.hiddenLayers]  Layers not drawn.
 * @param {(ctx: CanvasRenderingContext2D, view: { transform: object, pixelRatio: number, width: number, height: number }) => void} [options.overlay]
 *   Painted over the drawing in each frame.
 * @param {(point: { x: number, y: number }, event: PointerEvent) => void} [options.onTap]
 * @param {(point: { x: number, y: number } | null, event: PointerEvent | null) => void} [options.onHover]
 *   A pointer resting over the canvas with nothing pressed (null: it left).
 */
export function useDrawingView({ drawing, restored = null, colorScheme = "light", onViewMoved, hiddenLayers = NO_LAYERS,
  overlay = null, onTap = null, onHover = null }) {
  const drawingRef = useRef(drawing);
  drawingRef.current = drawing;
  const hiddenRef = useRef(hiddenLayers);
  hiddenRef.current = hiddenLayers;
  const overlayRef = useRef(overlay);
  overlayRef.current = overlay;
  const paint = useCallback((ctx, { width, height, pixelRatio, transform, element, colorScheme: scheme }) => {
    const { background, foreground } = readDrawingThemeColors(element, scheme);
    clearSurface(ctx, { width, height, pixelRatio, background });
    const drawable = drawingRef.current;
    if (!drawable || !transform) return;
    drawDrawing(ctx, drawable, { transform, foreground, pixelRatio, hiddenLayers: hiddenRef.current });
    overlayRef.current?.(ctx, { transform, pixelRatio, width, height });
  }, []);
  const view = useFlatCanvasView({ content: drawing, bounds: drawing?.bounds ?? null, restored, colorScheme, onViewMoved, paint,
    onTap, onHover, fitBox: fitBoardBounds, clearStrip: true, middlePan: true, orbitPan: true });
  const { requestPaint, encode } = view;

  // A layer shown or hidden: the same view, without it.
  useEffect(() => { requestPaint(); }, [hiddenLayers, requestPaint]);

  /**
   * The drawing on its own, for a library card: fitted whole to `width` × `height`, painted on a
   * canvas of its own — the pane's view is left as it is. Like a 3D card's picture it has no
   * background (the card's picture area shows through), and its pen is the light theme's whatever
   * the theme it was taken in: one picture serves both themes, and a dark card inverts it
   * (`.cad-library-thumbnail[data-drawing]`).
   */
  const thumbnail = useCallback(({ width, height }) => new Promise((resolve, reject) => {
    const drawable = drawingRef.current;
    if (!drawable?.bounds) { reject(new Error("This drawing has nothing to picture.")); return; }
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(width));
    canvas.height = Math.max(1, Math.round(height));
    const context = canvas.getContext("2d");
    if (!context) { reject(new Error("The browser cannot draw the drawing's picture.")); return; }
    clearSurface(context, { width: canvas.width, height: canvas.height });
    drawDrawing(context, drawable, { transform: fitTransform(drawable.bounds, canvas.width, canvas.height),
      foreground: DRAWING_THEME_FALLBACK.light.foreground });
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("The browser could not encode this drawing as a PNG."));
    }, "image/png");
  }), []);

  /** The framed picture as a PNG, background included: it is painted into the canvas. */
  const capture = useCallback(() => encode("drawing"), [encode]);

  return { containerRef: view.containerRef, canvasRef: view.canvasRef, controls: view.controls, dragging: view.dragging, fit: view.fit, frame: view.frame,
    zoomBy: view.zoomBy, zoom: view.zoom, setView: view.setView, capture, thumbnail, transformRef: view.transformRef, sizeRef: view.sizeRef, requestPaint };
}
