import * as THREE from "three";
import { cancelCameraTransition } from "../../camera/runtimeCamera.js";
import { clearKeyboardOrbitState } from "../../camera/viewportCameraKit.js";
import { applyDrawingViewLock, captureDrawingViewLock } from "./drawingViewLock.js";

/**
 * Draw mode's target in a 3D viewport (`useDrawingViewLock.js`): the camera. The view direction is
 * locked and the camera follows the editor's pan and zoom (`drawingViewLock.js`). Orbit input never
 * reaches the controls (the editor covers the viewport), and everything else that could turn or
 * reframe the camera is switched off for the duration.
 *
 * @param {{ current: any }} runtimeRef  The viewport's runtime: its camera, controls and frame.
 * @param {{ current: HTMLElement | null }} mountRef  The element the canvas is mounted in.
 * @returns {import("./useDrawingViewLock.js").DrawingViewTarget}
 */
export function cameraDrawingTarget(runtimeRef, mountRef) {
  const frameOf = () => {
    const runtime = runtimeRef.current, host = mountRef.current;
    if (!runtime?.camera || !runtime?.controls || !host) return null;
    return { camera: runtime.camera, controls: runtime.controls, width: host.clientWidth, height: host.clientHeight };
  };
  return {
    host: mountRef,
    // The runtime refits its projection to a resized viewport first; then the ink's mapping is restored.
    deferResize: true,
    capture(viewport) {
      const frame = frameOf();
      return frame ? captureDrawingViewLock(THREE, frame, viewport) : null;
    },
    apply(lock, viewport) {
      const runtime = runtimeRef.current, frame = frameOf();
      if (!frame || !applyDrawingViewLock(THREE, lock, frame, viewport)) return;
      runtime.userMovedCamera = true;
      runtime.controls.dispatchEvent?.({ type: "change" });
      runtime.requestRender?.();
    },
    begin() {
      const runtime = runtimeRef.current, controls = runtime?.controls;
      if (!controls) return undefined;
      cancelCameraTransition(runtime);
      clearKeyboardOrbitState(runtime.keyboardOrbitState);
      const previous = { enabled: controls.enabled, enableDamping: controls.enableDamping };
      controls.enabled = false;
      // Residual orbit inertia would keep turning the model under the first stroke.
      controls.enableDamping = false;
      controls.update?.();
      return () => {
        const active = runtimeRef.current?.controls;
        if (active) { active.enabled = previous.enabled; active.enableDamping = previous.enableDamping; active.update?.(); }
        runtimeRef.current?.requestRender?.();
      };
    }
  };
}
