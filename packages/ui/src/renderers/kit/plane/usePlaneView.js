/**
 * A flat picture on a canvas, and the three things a person does to it: drag to pan, wheel or
 * pinch to zoom about the pointer, double-click to fit.
 *
 * The renderer brings the picture: its `bounds` in the plane (`@text-to-cad/core`'s plane maths,
 * `lib/drawing2d/transform.js`: model space, y up) and `paint(ctx, frame)`, which draws one whole
 * frame — the surface around the picture included — at the frame's view. A frame is
 * `{ width, height, pixelRatio, transform, element, colorScheme }`: the pane in CSS pixels, the
 * backing store's ratio, the view (null until there is a picture to frame), the pane's element
 * (whose tokens say the theme) and the host's scheme. Everything else is this hook's.
 *
 * The view lives in a REF, not in React state. A pan is a stream of pointer moves and a zoom is
 * a stream of wheel ticks; re-rendering a component tree per event would make both stutter and
 * would tell React about a number only the canvas cares about. The component re-renders when
 * something it actually shows changes — whether a drag is in progress, so the cursor can say so —
 * and never per frame. A press that stays a tap is no drag: it re-renders nothing here, which on
 * a board whose panels hold thousands of rows is most of what a click costs.
 *
 * Painting is on demand: one `requestAnimationFrame` is scheduled when something changed, and an
 * idle picture paints nothing at all. A resize is the exception: resizing the canvas wipes it, so
 * the pane's observer paints at once.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  clampScale,
  fitTransform,
  panTransform,
  sameTransform,
  screenToModel,
  zoomLimits,
  zoomTransform
} from "@text-to-cad/core/lib/drawing2d/transform.js";
import { IDLE_PIXEL_RATIO_CAP, getPixelRatioCap } from "../viewport/pixelRatio.js";

/** How far a press may wander and still be a tap rather than a pan, in CSS pixels. */
export const TAP_SLOP_PX = 4;
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
 * @param {unknown} options.content  The picture, or null while it loads. A new one frames itself
 *   unless the view is already the person's.
 * @param {readonly [number, number, number, number]|null} options.bounds  What the fit frames.
 * @param {{ scale: number, offsetX: number, offsetY: number }|null} options.restored
 *   The view this file was left at, when it was left anywhere but the fit.
 * @param {"light"|"dark"} options.colorScheme
 * @param {(transform: object|null) => void} options.onViewMoved  Called after the person moves the
 *   view, with the transform to remember. Called with null for a fit.
 * @param {(ctx: CanvasRenderingContext2D, frame: object) => void} options.paint  One whole frame.
 * @param {string} [options.noun]  What the picture is called in an error ("drawing", "board").
 * @param {{ onTap?: (point: {x: number, y: number}, event: PointerEvent) => void,
 *   onHover?: (point: {x: number, y: number} | null, event: PointerEvent) => void,
 *   onDoubleTap?: (point: {x: number, y: number}, event: MouseEvent) => boolean }} [options.picking]
 *   For a picture whose parts can be pointed at (a KiCad board's): a press that did not move
 *   (`onTap`, within `TAP_SLOP_PX`, one finger or button), the pointer over the picture with no
 *   button down (`onHover`, null as it leaves), and a double-click, which fits the view unless
 *   `onDoubleTap` answers that it used it. Points are in the pane's CSS pixels.
 */
export function usePlaneView({ content, bounds, restored = null, colorScheme = "light", onViewMoved, paint: paintFrame, noun = "picture", picking = null }) {
  const containerRef = useRef(null);
  const canvasRef = useRef(null);
  const contextRef = useRef(null);
  const sizeRef = useRef({ width: 0, height: 0 });
  const transformRef = useRef(null);
  const fitScaleRef = useRef(0);
  // The person has framed this picture themselves: a resize must not take it back,
  // and it is worth remembering. A restored view is already theirs.
  const movedRef = useRef(Boolean(restored));
  const restoredRef = useRef(restored);
  const boundsRef = useRef(bounds);
  boundsRef.current = bounds;
  const schemeRef = useRef(colorScheme);
  schemeRef.current = colorScheme;
  const onViewMovedRef = useRef(onViewMoved);
  onViewMovedRef.current = onViewMoved;
  const paintFrameRef = useRef(paintFrame);
  paintFrameRef.current = paintFrame;
  const [dragging, setDragging] = useState(false);
  const frameRef = useRef(0);
  const pickingRef = useRef(picking);
  pickingRef.current = picking;

  const paint = useCallback(() => {
    frameRef.current = 0;
    const canvas = canvasRef.current;
    const { width, height } = sizeRef.current;
    if (!canvas || width <= 0 || height <= 0) return;
    const ctx = contextRef.current || (contextRef.current = canvas.getContext("2d"));
    if (!ctx) return;
    const pixelRatio = getPixelRatioCap(IDLE_PIXEL_RATIO_CAP);
    paintFrameRef.current?.(ctx, {
      width, height, pixelRatio, transform: transformRef.current,
      element: containerRef.current, colorScheme: schemeRef.current
    });
  }, []);

  const requestPaint = useCallback(() => {
    if (frameRef.current) return;
    frameRef.current = requestAnimationFrame(paint);
  }, [paint]);

  /** Paint in the caller's task, in place of any frame already asked for. */
  const paintNow = useCallback(() => {
    if (frameRef.current) cancelAnimationFrame(frameRef.current);
    paint();
  }, [paint]);

  /** Recompute the fitted scale for the current pane, and adopt it unless the view is the person's. */
  const refit = useCallback((force) => {
    const box = boundsRef.current;
    const { width, height } = sizeRef.current;
    if (!box || width <= 0 || height <= 0) return;
    const fitted = fitTransform(box, width, height);
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
      // absolute pixel scale either, or a pane that narrows (the window resizing) simply
      // crops the picture where it stands. So it keeps what it MEANT: the same zoom
      // relative to the fit, still centred on what it was centred on.
      // That is how the 3D viewports behave when their pane changes size.
      if (heldCentre && heldZoom > 0 && movedRef.current && fitScaleRef.current > 0) {
        const scale = clampScale(heldZoom * fitScaleRef.current, zoomLimits(fitScaleRef.current));
        moveTo({
          scale,
          offsetX: width / 2 - heldCentre[0] * scale,
          offsetY: height / 2 + heldCentre[1] * scale
        });
      }
      // Resizing the canvas above wiped it. The observer runs after layout and before
      // paint, but after this frame's animation callbacks, so a frame asked for now would
      // only be painted in the NEXT frame and the pane would show empty for one. Paint the
      // picture at its new size here, so the frame the pane changed in already shows it.
      paintNow();
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    return () => observer.disconnect();
  }, [moveTo, paintNow, refit]);

  // A new picture frames itself, unless this file's view is already the person's.
  useEffect(() => {
    transformRef.current = boundsRef.current ? transformRef.current : null;
    refit(false);
  }, [content, refit]);

  // The theme moved: same view, different surround.
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

    // A press is a tap until it moves past the slop or a second pointer joins it.
    let press = null;
    const onPointerDown = (event) => {
      // Primary press only: a secondary or middle press belongs to whatever the
      // host puts on them, not to panning.
      if (event.pointerType === "mouse" && event.button !== 0) return;
      canvas.setPointerCapture?.(event.pointerId);
      const point = local(event);
      pointers.set(event.pointerId, point);
      press = pointers.size === 1 ? { id: event.pointerId, x: point.x, y: point.y } : null;
      if (pointers.size === 2) measurePinch();
      event.preventDefault();
    };
    const onPointerMove = (event) => {
      const previous = pointers.get(event.pointerId);
      if (!previous) {
        if (!pointers.size) pickingRef.current?.onHover?.(local(event), event);
        return;
      }
      const point = local(event);
      if (press && Math.hypot(point.x - press.x, point.y - press.y) > TAP_SLOP_PX) press = null;
      // No longer a tap: a drag, or a pinch, and the cursor says so.
      if (!press) setDragging(true);
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
      const tapped = press && press.id === event.pointerId && event.type === "pointerup";
      press = null;
      if (tapped) pickingRef.current?.onTap?.(local(event), event);
    };
    const onPointerLeave = (event) => { if (!pointers.size) pickingRef.current?.onHover?.(null, event); };
    const onWheel = (event) => {
      if (!transformRef.current) return;
      // The page must not scroll under a picture being zoomed, so this listener
      // is registered non-passive and always consumes the event.
      event.preventDefault();
      zoomBy(wheelZoomFactor(event), local(event));
    };
    const onDoubleClick = (event) => {
      event.preventDefault();
      if (!pickingRef.current?.onDoubleTap?.(local(event), event)) fit();
    };

    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("pointercancel", onPointerUp);
    canvas.addEventListener("pointerleave", onPointerLeave);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    canvas.addEventListener("dblclick", onDoubleClick);
    return () => {
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("pointercancel", onPointerUp);
      canvas.removeEventListener("pointerleave", onPointerLeave);
      canvas.removeEventListener("wheel", onWheel);
      canvas.removeEventListener("dblclick", onDoubleClick);
    };
  }, [fit, moveTo, zoomBy]);

  /** The framed picture as a PNG, the surface included: it is painted into the canvas. */
  const nounRef = useRef(noun);
  nounRef.current = noun;
  const capture = useCallback(() => new Promise((resolve, reject) => {
    const canvas = canvasRef.current;
    if (!canvas) { reject(new Error(`This ${nounRef.current} is not on screen yet.`)); return; }
    canvas.toBlob((blob) => {
      if (blob) resolve(blob);
      else reject(new Error(`The browser could not encode this ${nounRef.current} as a PNG.`));
    }, "image/png");
  }), []);

  return { containerRef, canvasRef, dragging, fit, setView: moveTo, capture, requestPaint, paintNow, transformRef, schemeRef };
}
