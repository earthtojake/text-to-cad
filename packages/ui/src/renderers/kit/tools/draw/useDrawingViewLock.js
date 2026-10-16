import { useCallback, useEffect, useRef } from "react";

/**
 * DRAW MODE: the drawing editor owns pan and zoom, and the view under it follows, so ink and
 * picture stay one picture. What follows is the TARGET's: a 3D camera (`cameraDrawingTarget.js`)
 * or a flat picture's transform (`planeViewLock.js`). This hook decides WHEN: the lock is taken
 * when there is first something to keep aligned — ink, or a pan — against the viewport the target
 * is still showing; every later editor viewport is answered from that one lock, never from the
 * previous frame, so a long pan cannot drift; and when the pane changes size, the target is put back
 * under the ink from the same lock.
 *
 * @param {{ active: boolean, sketch?: number, drawing: import("../../../../drawing/session.js").DrawingSession | null | undefined,
 *   target: DrawingViewTarget, ready?: unknown }} options
 *   `active` is the overlay being mounted over a view that has content; `sketch` is the session's
 *   sketch (`drawing.sketch`), whose editor is a new one each time it changes; `ready` changes when
 *   the target is replaced under the sketch (a new runtime), which locks again against the viewport
 *   the editor is still showing.
 * @returns the editor's controller (for a composite capture) and the overlay's three callbacks.
 *
 * @typedef {object} DrawingViewTarget
 * @property {{ current: Element | null }} host  The element whose size is the view's.
 * @property {(viewport: object) => object | null} capture  The lock: the target as it is now, shown
 *   under `viewport`. Null while it cannot be measured.
 * @property {(lock: object, viewport: object, detail: { resized: boolean }) => void} apply  Move the
 *   target to answer `viewport`, from `lock`; `resized` when the pane changed size under the sketch.
 * @property {() => (() => void) | void} [begin]  Taken while Draw is up: what must not move the target
 *   meanwhile is switched off, and the cleanup it returns switches it back.
 * @property {boolean} [deferResize]  The target refits itself to a new size first (a camera's
 *   projection), so the lock is applied after it, not in the resize's own callback.
 */
export function useDrawingViewLock({ active, sketch = 0, drawing, target, ready = 0 }) {
  const drawingControllerRef = useRef(null);
  const drawingViewRef = useRef(null);
  const drawingViewportRef = useRef({ scrollX: 0, scrollY: 0, zoom: 1 });
  const drawingHasInkRef = useRef(false);
  const targetRef = useRef(target);
  targetRef.current = target;
  const followDrawingViewport = useCallback((viewport, { lock = false, resized = false } = {}) => {
    const view = drawingViewRef.current, current = targetRef.current;
    if (!view) return;
    // Until there is something to keep aligned the target is nobody's but the view's: a resize or
    // a restored view stands.
    if (viewport || lock) view.lock ??= current.capture(view.viewport);
    if (viewport) view.viewport = drawingViewportRef.current = viewport;
    if (view.lock) current.apply(view.lock, view.viewport, { resized });
  }, []);
  // A new sketch starts from the editor's own origin, with nothing on it to keep aligned: when
  // Draw is taken up, and when a sketch is discarded under a Draw that stays (its new editor opens
  // at the origin, and the target stays where the last one left it). Only a target swap inherits a
  // viewport. Declared before the lock below, which runs again for the same changes and must find
  // these already reset.
  useEffect(() => {
    drawingViewportRef.current = { scrollX: 0, scrollY: 0, zoom: 1 };
    drawingHasInkRef.current = false;
  }, [active, sketch]);
  useEffect(() => {
    const host = targetRef.current.host.current;
    if (!active || !host) return undefined;
    const end = targetRef.current.begin?.();
    // A target replaced mid-sketch re-locks against the viewport the editor is still showing.
    drawingViewRef.current = { lock: null, viewport: drawingViewportRef.current };
    if (drawingHasInkRef.current) followDrawingViewport(null, { lock: true });
    let frame = 0;
    const resized = () => followDrawingViewport(null, { resized: true });
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => {
      if (!targetRef.current.deferResize) { resized(); return; }
      clearTimeout(frame);
      frame = setTimeout(resized, 0);
    });
    observer?.observe(host);
    return () => {
      observer?.disconnect();
      clearTimeout(frame);
      drawingViewRef.current = null;
      end?.();
    };
  }, [active, sketch, followDrawingViewport, ready]);
  const handleDrawingContent = useCallback((hasContent) => {
    const hadInk = drawingHasInkRef.current;
    drawingHasInkRef.current = hasContent;
    if (hasContent && !hadInk) followDrawingViewport(null, { lock: true });
    drawing?.onContentChange(hasContent);
  }, [drawing?.onContentChange, followDrawingViewport]);
  const handleDrawingReady = useCallback((controller) => {
    drawingControllerRef.current = controller;
    drawing?.onReady(controller);
  }, [drawing?.onReady]);
  return { drawingControllerRef, handleDrawingContent, handleDrawingReady, followDrawingViewport };
}
