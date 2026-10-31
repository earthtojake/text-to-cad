import { useCallback, useRef } from "react";
import { applyPerspectiveSnapshot, cancelCameraTransition, readScopedPerspectiveSnapshot, recenterRuntimeTarget, setRuntimeZoomPercent, transitionCameraToViewPreset, zoomRuntimeToBounds } from "./runtimeCamera.js";
import { runtimeModelKeyMatches } from "@text-to-cad/core/lib/viewer/modelRuntime.js";
import { requestSceneFrame } from "../viewport/sceneFrames.js";
import { CAMERA_TOUCH, fitCamera, touchCamera } from "./cameraTouch.js";
import { perspectiveSnapshotEqual, perspectiveSnapshotMatchesScene, resolvePerspectiveSnapshot } from "@text-to-cad/core/lib/perspective.js";
import { VIEW_CUBE_DRAG_RAD_PER_PX, VIEW_PLANE_FACE_BY_ID, applyOrbitDelta, readViewPlaneOrientation, runtimeFramingBounds } from "./viewportCameraKit.js";

/**
 * The camera of a mounted viewport, as React sees it: the perspective a session
 * stores (emitted when it really changed; a viewport that keeps no camera, Preview's,
 * only says it moved), the initial/stored view, the reset, and the view cube's face presets. The refs and setters are
 * the mounting component's; this hook owns the behaviour between them and the
 * runtime (`runtimeCamera.js`).
 *
 * `modelBounds` is the authored `{ min, max }` a reset frames; `coordinateSystemFor`
 * names the coordinate system a stored camera belongs to, for a scale mode;
 * `cameraMovedRef.current()` is told when the camera of a viewport that keeps none moved.
 */
export function useViewportCamera({
  coordinateSystemFor,
  activeViewPlaneFaceRef,
  lastEmittedPerspectiveRef,
  cameraMovedRef,
  modelBounds,
  modelKeyRef,
  modelTransformRef,
  perspectiveChangeRef,
  perspectivePropRef,
  perspectiveRef,
  runWithoutPerspectiveEvents,
  runtimeRef,
  sceneScaleModeRef,
  setActiveViewPlaneFace,
  setViewPlaneOrientation,
  suppressPerspectiveEventsRef
}) {
  const emitPerspectiveChange = (runtime = runtimeRef.current) => {
    const currentModelKey = modelKeyRef.current;
    if (!runtimeModelKeyMatches(runtime, currentModelKey)) {
      return;
    }
    const nextPerspective = readScopedPerspectiveSnapshot(runtime, {
      modelKey: currentModelKey,
      sceneScaleMode: sceneScaleModeRef.current,
      coordinateSystem: coordinateSystemFor(sceneScaleModeRef.current)
    });
    if (!nextPerspective) {
      return;
    }
    if (!perspectiveChangeRef.current) {
      // A view that keeps no camera (Preview's): only what samples the camera hears it moved.
      cameraMovedRef.current?.();
      return;
    }
    if (suppressPerspectiveEventsRef.current > 0) {
      lastEmittedPerspectiveRef.current = nextPerspective;
      return;
    }
    if (perspectiveSnapshotEqual(lastEmittedPerspectiveRef.current, nextPerspective)) {
      return;
    }
    lastEmittedPerspectiveRef.current = nextPerspective;
    perspectiveChangeRef.current?.(nextPerspective);
  };
  // `setViewPlaneOrientation` is the cube's orientation store's `set`, which ignores an equal orientation.
  const syncViewPlaneOrientation = (runtime = runtimeRef.current) => {
    const nextOrientation = readViewPlaneOrientation(runtime);
    if (nextOrientation) setViewPlaneOrientation(nextOrientation);
  };
  const applyInitialPerspective = useCallback((runtime = runtimeRef.current) => {
    const nextPerspective = resolvePerspectiveSnapshot(
      perspectiveRef ? perspectiveRef.current : undefined,
      perspectivePropRef.current
    );
    if (!perspectiveSnapshotMatchesScene(nextPerspective, {
      modelKey: modelKeyRef.current,
      sceneScaleMode: sceneScaleModeRef.current,
      coordinateSystem: coordinateSystemFor(sceneScaleModeRef.current),
      requireModelKey: true,
      requireSceneScaleMode: true,
      requireCoordinateSystem: true
    })) {
      return false;
    }
    return runWithoutPerspectiveEvents(() => applyPerspectiveSnapshot(runtime, nextPerspective, { scheduleIdle: false }));
  }, [perspectiveRef]);
  // The authored bounds a reset frames, read at the moment of the reset: it is a
  // fresh object every render, but the imperative reset callback must stay stable.
  const modelBoundsRef = useRef(modelBounds);
  modelBoundsRef.current = modelBounds;
  const resetZoomAndPan = useCallback(({ animate = true } = {}) => {
    const runtime = runtimeRef.current;
    const reset = zoomRuntimeToBounds(
      runtime,
      runtimeFramingBounds(runtime, modelBoundsRef.current),
      sceneScaleModeRef.current,
      {
        animate,
        modelOffset: modelTransformRef.current.offset,
        resetZoomBaseline: true
      }
    );
    if (reset && !animate) {
      emitPerspectiveChange(runtime);
      syncViewPlaneOrientation(runtime);
    }
    if (reset) {
      // Asking for the fit hands the camera back to it (`cameraTouch.js`): a model still arriving
      // is framed again, whole, when it has, and a rebuild whose box changed is fitted again.
      fitCamera(runtime);
      return true;
    }
    // Fallback for when the refit bails — no usable bounds yet, so there is
    // nothing to frame. It still has to undo the pan: resetting only the zoom
    // leaves the controls aimed wherever the user dragged to, and the caller's
    // orientation tween carries that target through, so the view snaps back in
    // zoom and angle while staying panned off-centre.
    recenterRuntimeTarget(runtime);
    if (!setRuntimeZoomPercent(runtime, 100)) {
      return false;
    }
    emitPerspectiveChange(runtime);
    syncViewPlaneOrientation(runtime);
    return true;
  }, []);
  // Stable, and built only from refs and setters: the view cube is memoized, so a viewer
  // render that changed nothing of the cube's (every animation frame) does not redraw it.
  // A face the cube turns to, or a drag across it, makes the view the user's, as a drag on the
  // model does: the completion fit of a model still arriving leaves it alone.
  const activateViewPlaneFace = useCallback((faceId) => {
    const runtime = runtimeRef.current;
    const face = VIEW_PLANE_FACE_BY_ID[faceId];
    if (!runtime || !face) {
      return false;
    }
    activeViewPlaneFaceRef.current = face.id;
    setActiveViewPlaneFace(face.id);
    const turned = transitionCameraToViewPreset(runtime, face);
    if (turned) touchCamera(runtime, CAMERA_TOUCH.VIEW_CUBE);
    return turned;
  }, []);
  // Dragging the view cube orbits the camera, as dragging Fusion's does: the cube turns with
  // the pointer, so the camera turns the other way. Same orbit as the arrow keys.
  const orbitFromViewCube = useCallback((dxPx, dyPx) => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return false;
    }
    cancelCameraTransition(runtime);
    // Interaction quality while the drag lasts, full quality once it rests: as the arrow keys.
    runtime.beginInteraction?.();
    const orbited = applyOrbitDelta(runtime, -dxPx * VIEW_CUBE_DRAG_RAD_PER_PX, -dyPx * VIEW_CUBE_DRAG_RAD_PER_PX);
    runtime.scheduleIdleQuality?.();
    if (!orbited) {
      return false;
    }
    touchCamera(runtime, CAMERA_TOUCH.VIEW_CUBE_DRAG);
    activeViewPlaneFaceRef.current = "";
    setActiveViewPlaneFace("");
    emitPerspectiveChange(runtime);
    syncViewPlaneOrientation(runtime);
    // An orbit by the cube is a camera move, as a drag on the model is: the shadow maps are kept.
    requestSceneFrame(runtime, false);
    return true;
  }, []);
  return {
    activateViewPlaneFace,
    orbitFromViewCube,
    applyInitialPerspective,
    emitPerspectiveChange,
    resetZoomAndPan,
    syncViewPlaneOrientation
  };
}
