/**
 * The canvas a drawing is painted on, and the three things a person does to it:
 * drag to pan, wheel or pinch to zoom about the pointer, double-click to fit.
 *
 * The view lives in a REF, not in React state. A pan is a stream of pointer
 * moves and a zoom is a stream of wheel ticks; re-rendering a component tree per
 * event would make both stutter and would tell React about a number only the
 * canvas cares about. The component re-renders when something it actually shows
 * changes — whether a drag is in progress, so the cursor can say so — and never
 * per frame.
 *
 * Painting is on demand: one `requestAnimationFrame` is scheduled when
 * something changed, and an idle drawing draws nothing at all.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  clampScale,
  clearSurface,
  drawDrawing,
  fitTransform,
  panTransform,
  sameTransform,
  screenToModel,
  zoomLimits,
  zoomTransform
} from "@hardcore/core/lib/drawing2d/index.js";
import { IDLE_PIXEL_RATIO_CAP, getPixelRatioCap } from "../kit/viewport/pixelRatio.js";
import { readDrawingThemeColors } from "./themeColors.js";

/** Wheel notches to zoom factor. A notch is ~100 px of delta on most mice. */
const WHEEL_ZOOM_SPEED = 0.0015;
/** A trackpad pinch arrives as a ctrl-wheel with much smaller deltas. */
const PINCH_WHEEL_ZOOM_SPEED = 0.01;
const LINE_HEIGHT_PX = 16;
const PAGE_HEIGHT_PX = 400;
function wheelZoomFactor(event) {
  const unit = event.deltaMode === 1 ? LINE_HEIGHT_PX : event.deltaMode === 2 ? PAGE_HEIGHT_PX : 1;
  const speed = event.ctrlKey ? PINCH_WHEEL_ZOOM_SPEED : WHEEL_ZOOM_SPEED;
  return Math.exp(-event.deltaY * unit * speed);
}

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
  const containerRef = useRef(null);
  const canvasRef = useRef(null);
  const contextRef = useRef(null);
  const sizeRef = useRef({ width: 0, height: 0 });
  const transformRef = useRef(null);
  const fitScaleRef = useRef(0);
  // The person has framed this drawing themselves: a resize must not take it back,
  // and it is worth remembering. A restored view is already theirs.
  const movedRef = useRef(Boolean(restored));
  const restoredRef = useRef(restored);
  const drawingRef = useRef(drawing);
  drawingRef.current = drawing;
  const schemeRef = useRef(colorScheme);
  schemeRef.current = colorScheme;
  const onViewMovedRef = useRef(onViewMoved);
  onViewMovedRef.current = onViewMoved;
  const [dragging, setDragging] = useState(false);
  const frameRef = useRef(0);

  const paint = useCallback(() => {
    frameRef.current = 0;
    const canvas = canvasRef.current;
    const { width, height } = sizeRef.current;
    if (!canvas || width <= 0 || height <= 0) return;
    const ctx = contextRef.current || (contextRef.current = canvas.getContext("2d"));
    if (!ctx) return;
    const pixelRatio = getPixelRatioCap(IDLE_PIXEL_RATIO_CAP);
    const { background, foreground } = readDrawingThemeColors(containerRef.current, schemeRef.current);
    clearSurface(ctx, { width, height, pixelRatio, background });
    const drawable = drawingRef.current;
    if (drawable && transformRef.current) {
      drawDrawing(ctx, drawable, { transform: transformRef.current, foreground, pixelRatio });
    }
  }, []);

  const requestPaint = useCallback(() => {
    if (frameRef.current) return;
    frameRef.current = requestAnimationFrame(paint);
  }, [paint]);

  /** Recompute the fitted scale for the current pane, and adopt it unless the view is the person's. */
  const refit = useCallback((force) => {
    const drawable = drawingRef.current;
    const { width, height } = sizeRef.current;
    if (!drawable?.bounds || width <= 0 || height <= 0) return;
    const fitted = fitTransform(drawable.bounds, width, height);
    fitScaleRef.current = fitted.scale;
    if (force || !movedRef.current) {
      movedRef.current = false;
      transformRef.current = fitted;
      onViewMovedRef.current?.(null);
    } else if (!transformRef.current) {
      transformRef.current = restoredRef.current;
    }
    requestPaint();
  }, [requestPaint]);

  /** Record a view the person chose. */
  const moveTo = useCallback((next) => {
    if (!next || sameTransform(transformRef.current, next)) return;
    transformRef.current = next;
    movedRef.current = true;
    onViewMovedRef.current?.(next);
    requestPaint();
  }, [requestPaint]);

  const fit = useCallback(() => refit(true), [refit]);

  const zoomBy = useCallback((factor, anchor) => {
    const transform = transformRef.current;
    if (!transform || !fitScaleRef.current) return;
    const { width, height } = sizeRef.current;
    const point = anchor || { x: width / 2, y: height / 2 };
    moveTo(zoomTransform(transform, point, factor, zoomLimits(fitScaleRef.current)));
  }, [moveTo]);

  // ---- the pane's size -------------------------------------------------------
  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas || typeof ResizeObserver === "undefined") return undefined;
    const measure = () => {
      const rect = container.getBoundingClientRect();
      const width = Math.max(0, Math.round(rect.width));
      const height = Math.max(0, Math.round(rect.height));
      const previous = sizeRef.current;
      if (width === previous.width && height === previous.height) return;
      // What the pane held in its middle, and how far the view was from the fitted scale.
      // Both are read BEFORE the size changes: a view the person chose is carried across a
      // resize in those terms rather than in pixels (see below).
      const heldCentre = transformRef.current && previous.width > 0 && previous.height > 0
        ? screenToModel(transformRef.current, previous.width / 2, previous.height / 2)
        : null;
      const heldZoom = transformRef.current && fitScaleRef.current > 0
        ? transformRef.current.scale / fitScaleRef.current
        : 0;
      sizeRef.current = { width, height };
      const pixelRatio = getPixelRatioCap(IDLE_PIXEL_RATIO_CAP);
      canvas.width = Math.max(1, Math.round(width * pixelRatio));
      canvas.height = Math.max(1, Math.round(height * pixelRatio));
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      // A canvas resize wipes its backing store AND its context state, so the
      // cached context has to be re-read along with the picture.
      contextRef.current = canvas.getContext("2d");
      refit(false);
      // A view the person framed is not taken back by a resize — but it must not keep an
      // absolute pixel scale either, or a pane that narrows (the file tree opening, the
      // window resizing) simply crops the drawing where it stands. So it keeps what it
      // MEANT: the same zoom relative to the fit, still centred on what it was centred on.
      // That is how the 3D viewports behave when their pane changes size.
      if (heldCentre && heldZoom > 0 && movedRef.current && fitScaleRef.current > 0) {
        const scale = clampScale(heldZoom * fitScaleRef.current, zoomLimits(fitScaleRef.current));
        moveTo({
          scale,
          offsetX: width / 2 - heldCentre[0] * scale,
          offsetY: height / 2 + heldCentre[1] * scale
        });
      }
      requestPaint();
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    return () => observer.disconnect();
  }, [moveTo, refit, requestPaint]);

  // A new drawing frames itself, unless this file's view is already the person's.
  useEffect(() => {
    transformRef.current = drawing?.bounds ? transformRef.current : null;
    refit(false);
  }, [drawing, refit]);

  // The theme moved: same view, different ink.
  //
  // The host's `colorScheme` is one trigger, but not the only one — whatever
  // swaps the tokens does it by writing the class or the style on `<html>`, and
  // that write is not a React render here. So watch the element the tokens are
  // declared on, exactly as the 3D viewers' backdrop does.
  useEffect(() => {
    requestPaint();
    if (typeof document === "undefined" || typeof MutationObserver === "undefined") return undefined;
    const observer = new MutationObserver(requestPaint);
    observer.observe(document.documentElement, { attributeFilter: ["class", "style"] });
    return () => observer.disconnect();
  }, [colorScheme, requestPaint]);

  // The handle is cleared with the frame it names: React's development StrictMode runs this
  // cleanup and then the effects again on the SAME refs, and a stale non-zero handle would
  // make `requestPaint` believe a frame is still pending and never paint again.
  useEffect(() => () => {
    if (frameRef.current) cancelAnimationFrame(frameRef.current);
    frameRef.current = 0;
  }, []);

  // ---- pointer and wheel -----------------------------------------------------
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    /** @type {Map<number, {x: number, y: number}>} */
    const pointers = new Map();
    const local = (event) => {
      const rect = canvas.getBoundingClientRect();
      return { x: event.clientX - rect.left, y: event.clientY - rect.top };
    };
    const pinchState = { distance: 0, centre: { x: 0, y: 0 } };
    const measurePinch = () => {
      const [first, second] = [...pointers.values()];
      pinchState.distance = Math.hypot(first.x - second.x, first.y - second.y);
      pinchState.centre = { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 };
    };

    const onPointerDown = (event) => {
      // Primary press only: a secondary or middle press belongs to whatever the
      // host puts on them, not to panning.
      if (event.pointerType === "mouse" && event.button !== 0) return;
      canvas.setPointerCapture?.(event.pointerId);
      pointers.set(event.pointerId, local(event));
      if (pointers.size === 2) measurePinch();
      if (pointers.size === 1) setDragging(true);
      event.preventDefault();
    };
    const onPointerMove = (event) => {
      const previous = pointers.get(event.pointerId);
      if (!previous) return;
      const point = local(event);
      pointers.set(event.pointerId, point);
      const transform = transformRef.current;
      if (!transform) return;
      if (pointers.size === 1) {
        moveTo(panTransform(transform, point.x - previous.x, point.y - previous.y));
      } else if (pointers.size === 2 && fitScaleRef.current) {
        const before = { ...pinchState };
        measurePinch();
        if (before.distance > 0 && pinchState.distance > 0) {
          const zoomed = zoomTransform(transform, before.centre, pinchState.distance / before.distance,
            zoomLimits(fitScaleRef.current));
          moveTo(panTransform(zoomed, pinchState.centre.x - before.centre.x, pinchState.centre.y - before.centre.y));
        }
      }
    };
    const onPointerUp = (event) => {
      if (!pointers.delete(event.pointerId)) return;
      canvas.releasePointerCapture?.(event.pointerId);
      if (pointers.size === 2) measurePinch();
      if (pointers.size === 0) setDragging(false);
    };
    const onWheel = (event) => {
      if (!transformRef.current) return;
      // The page must not scroll under a drawing being zoomed, so this listener
      // is registered non-passive and always consumes the event.
      event.preventDefault();
      zoomBy(wheelZoomFactor(event), local(event));
    };
    const onDoubleClick = (event) => { event.preventDefault(); fit(); };

    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("pointercancel", onPointerUp);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("dblclick", onDoubleClick);
    return () => {
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("pointercancel", onPointerUp);
      canvas.removeEventListener("wheel", onWheel);
      canvas.removeEventListener("dblclick", onDoubleClick);
    };
  }, [fit, moveTo, zoomBy]);

  /** The framed picture as a PNG, background included: it is painted into the canvas. */
  const capture = useCallback(() => new Promise((resolve, reject) => {
    const canvas = canvasRef.current;
    if (!canvas) { reject(new Error("This drawing is not on screen yet.")); return; }
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error("The browser could not encode this drawing as a PNG."));
    }, "image/png");
  }), []);

  return { containerRef, canvasRef, dragging, fit, zoomBy, capture, transformRef };
}
