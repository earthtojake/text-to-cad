import { useCallback, useEffect, useRef } from "react";
import * as THREE from "three";
import { cancelCameraTransition } from "../../camera/runtimeCamera.js";
import { clearKeyboardOrbitState } from "../../camera/viewportCameraKit.js";
import { applyDrawingViewLock, captureDrawingViewLock } from "./drawingViewLock.js";

/**
 * DRAW MODE: the view direction is locked and the drawing editor owns pan and
 * zoom; the camera follows it so ink and model stay one picture. Orbit input
 * never reaches the controls (the editor covers the viewport), and everything
 * else that could turn or reframe the camera is switched off for the duration.
 *
 * @param {{ active: boolean, drawing: import("../../../../drawing/session.js").DrawingSession | null | undefined,
 *   runtimeRef: { current: any }, mountRef: { current: HTMLElement | null }, viewerReadyTick: number }} options
 *   `active` is the overlay being mounted over a viewport that has content.
 * @returns the editor's controller (for a composite capture) and the overlay's two callbacks.
 */
export function useDrawingViewLock({ active: drawingOverlayActive, drawing, runtimeRef, mountRef, viewerReadyTick }) {
  const drawingControllerRef = useRef(null);
  const drawingViewRef = useRef(null);
  const drawingViewportRef = useRef({ scrollX: 0, scrollY: 0, zoom: 1 });
  const drawingHasInkRef = useRef(false);
  const followDrawingViewport = useCallback((viewport, { lock = false } = {}) => {
    const view = drawingViewRef.current, runtime = runtimeRef.current, host = mountRef.current;
    if (!view || !runtime?.camera || !runtime?.controls || !host) return;
    const frame = { camera: runtime.camera, controls: runtime.controls, width: host.clientWidth, height: host.clientHeight };
    // The lock is taken when there is first something to keep aligned — ink, or a
    // pan — against the viewport the camera is still showing. Until then the
    // camera is nobody's but the viewer's: a resize or a restored view stands.
    if (viewport || lock) view.lock ??= captureDrawingViewLock(THREE, frame, view.viewport);
    if (viewport) view.viewport = drawingViewportRef.current = viewport;
    if (!view.lock) return;
    if (!applyDrawingViewLock(THREE, view.lock, frame, view.viewport)) return;
    runtime.userMovedCamera = true;
    runtime.controls.dispatchEvent?.({ type: "change" });
    runtime.requestRender?.();
  }, []);
  useEffect(() => {
    const runtime = runtimeRef.current, controls = runtime?.controls, host = mountRef.current;
    if (!drawingOverlayActive || !controls || !host) return undefined;
    cancelCameraTransition(runtime);
    clearKeyboardOrbitState(runtime.keyboardOrbitState);
    const previous = { enabled: controls.enabled, enableDamping: controls.enableDamping };
    controls.enabled = false;
    // Residual orbit inertia would keep turning the model under the first stroke.
    controls.enableDamping = false;
    controls.update?.();
    // A runtime replaced mid-sketch re-locks against the viewport the editor is still showing.
    drawingViewRef.current = { lock: null, viewport: drawingViewportRef.current };
    if (drawingHasInkRef.current) followDrawingViewport(null, { lock: true });
    // The runtime refits its projection to a resized viewport first; then the ink's mapping is restored.
    let frame = 0;
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => {
      clearTimeout(frame);
      frame = setTimeout(() => followDrawingViewport(), 0);
    });
    observer?.observe(host);
    return () => {
      observer?.disconnect();
      clearTimeout(frame);
      drawingViewRef.current = null;
      const active = runtimeRef.current?.controls;
      if (active) { active.enabled = previous.enabled; active.enableDamping = previous.enableDamping; active.update?.(); }
      runtimeRef.current?.requestRender?.();
    };
  }, [drawingOverlayActive, followDrawingViewport, viewerReadyTick]);
  // A new sketch starts from the editor's own origin; only a runtime swap inherits a viewport.
  useEffect(() => { if (!drawingOverlayActive) { drawingViewportRef.current = { scrollX: 0, scrollY: 0, zoom: 1 }; drawingHasInkRef.current = false; } }, [drawingOverlayActive]);
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
