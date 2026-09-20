import { useEffect } from "react";
import * as THREE from "three";

/**
 * PLAN MODE: a generic top-down camera lock, reusable by any model.
 *
 * Rotation is what makes a view 3D. Disabling it (and moving the left button onto pan) is
 * the whole mode: the camera keeps looking straight down, dragging slides the model, and
 * wheel-zoom still works. Everything else that reads as three-dimensional -- the view cube,
 * the vertical origin axis -- is hidden by the caller through `planMode`, so the viewport
 * stops advertising an axis you cannot turn towards.
 */
export function usePlanMode({ planMode, runtimeRef, viewerReadyTick }) {
  useEffect(() => {
    const runtime = runtimeRef.current;
    const controls = runtime?.controls;
    if (!controls) {
      return undefined;
    }
    const previousRotate = controls.enableRotate;
    const previousButtons = controls.mouseButtons ? { ...controls.mouseButtons } : null;
    if (planMode) {
      controls.enableRotate = false;
      if (controls.mouseButtons) {
        // Left-drag pans instead of orbiting; a locked view whose primary drag does nothing
        // reads as broken rather than as locked.
        controls.mouseButtons = { ...controls.mouseButtons, LEFT: THREE.MOUSE.PAN };
      }
    }
    const axis = runtime.originAxis;
    const previousAxisVisible = axis ? axis.visible : null;
    if (axis && planMode) {
      axis.visible = false;
    }
    controls.update?.();
    runtime.requestRender?.();
    return () => {
      const activeControls = runtimeRef.current?.controls;
      if (!activeControls) {
        return;
      }
      activeControls.enableRotate = previousRotate;
      if (previousButtons) {
        activeControls.mouseButtons = previousButtons;
      }
      const activeAxis = runtimeRef.current?.originAxis;
      if (activeAxis && previousAxisVisible !== null) {
        activeAxis.visible = previousAxisVisible;
      }
      activeControls.update?.();
      runtimeRef.current?.requestRender?.();
    };
  }, [planMode, viewerReadyTick]);
}
