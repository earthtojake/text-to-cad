import { useCallback, useEffect, useLayoutEffect, useRef } from "react";
import { applyPerspectiveSnapshot, cancelCameraTransition, captureRuntimeViewportFitScale, readPerspectiveSnapshot, readRuntimeZoomPercent, readScopedPerspectiveSnapshot, recenterRuntimeTarget, setRuntimeZoomPercent, syncRuntimeViewportFraming, transitionCameraToViewPreset, zoomRuntimeToBounds } from "./runtimeCamera.js";
import { runtimeModelKeyMatches } from "@hardcore/core/lib/viewer/modelRuntime.js";
import { perspectiveSnapshotEqual, perspectiveSnapshotMatchesScene, resolvePerspectiveSnapshot } from "@hardcore/core/lib/perspective.js";
import { DEFAULT_VIEW_DIRECTION, VIEW_PLANE_DEFAULT_PRESET, VIEW_PLANE_FACE_BY_ID, WORLD_UP, cameraMatchesViewPreset, clearKeyboardOrbitState, readViewPlaneOrientation, runtimeFramingBounds, viewPlaneOrientationEqual } from "./viewportCameraKit.js";

/**
 * The camera of a mounted viewport, as React sees it: the live zoom percent, the
 * perspective a session stores (emitted when it really changed, never while a
 * presentation camera is showing), the initial/stored view, the fullscreen
 * camera swap and its exact restore, zoom/reset commands, and the view cube's
 * face presets. The refs and setters are the mounting component's; this hook
 * owns the behaviour between them and the runtime (`runtimeCamera.js`).
 *
 * `modelBounds` is the authored `{ min, max }` a reset frames; `coordinateSystemFor`
 * names the coordinate system a stored camera belongs to, for a scale mode;
 * `cameraMovedRef.current()` is told when a presentation camera moved.
 */
export function useViewportCamera({
  coordinateSystemFor,
  activeViewPlaneFaceRef,
  cameraZoomPercent,
  defaultPerspectiveResettingRef,
  fullscreenCameraRef,
  lastEmittedPerspectiveRef,
  cameraMovedRef,
  modelBounds,
  modelKey,
  modelKeyRef,
  modelTransformRef,
  onCameraZoomPercentChange,
  perspectiveChangeRef,
  perspectivePropRef,
  perspectiveRef,
  previewMode,
  previewModeRef,
  previewOrbitSpeed,
  runWithoutPerspectiveEvents,
  runtimeRef,
  sceneScaleModeRef,
  setActiveViewPlaneFace,
  setCameraZoomPercent,
  setDefaultPerspectiveDetached,
  setViewPlaneOrientation,
  suppressPerspectiveEventsRef,
  viewerReadyTick
}) {
const syncCameraZoomPercent = useCallback((runtime = runtimeRef.current) => {
    if (!runtime?.camera) {
      setCameraZoomPercent((current) => (current === 100 ? current : 100));
      return;
    }
    const nextZoomPercent = Math.round(readRuntimeZoomPercent(runtime));
    setCameraZoomPercent((current) => (
      Math.abs(current - nextZoomPercent) < 0.5 ? current : nextZoomPercent
    ));
  }, []);
  // The zoom pill lives in the workspace's top-right toolbar row now, so the live percent
  // has to travel up — the viewer keeps the camera math, the toolbar keeps the control.
  const onCameraZoomPercentChangeRef = useRef(onCameraZoomPercentChange);
  onCameraZoomPercentChangeRef.current = onCameraZoomPercentChange;
  useEffect(() => {
    onCameraZoomPercentChangeRef.current?.(cameraZoomPercent);
  }, [cameraZoomPercent]);
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
    syncCameraZoomPercent(runtime);
    if (previewModeRef.current || fullscreenCameraRef.current) {
      // LOD still follows the presentation camera, but session persistence does not.
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
  const syncDefaultPerspectiveState = (runtime = runtimeRef.current) => {
    if (defaultPerspectiveResettingRef.current) {
      if (runtime?.cameraTransition) {
        setDefaultPerspectiveDetached(false);
        return;
      }
      defaultPerspectiveResettingRef.current = false;
    }
    const nextDetached = runtime?.THREE
      ? !cameraMatchesViewPreset(runtime, VIEW_PLANE_DEFAULT_PRESET)
      : false;
    setDefaultPerspectiveDetached((current) => (
      current === nextDetached ? current : nextDetached
    ));
  };
  const syncViewPlaneOrientation = (runtime = runtimeRef.current) => {
    const nextOrientation = readViewPlaneOrientation(runtime);
    if (!nextOrientation) {
      return;
    }
    setViewPlaneOrientation((current) => (
      viewPlaneOrientationEqual(current, nextOrientation) ? current : nextOrientation
    ));
    syncDefaultPerspectiveState(runtime);
  };
  const applyInitialPerspective = useCallback((runtime = runtimeRef.current) => {
    if (previewModeRef.current) return false;
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
  const syncFullscreenCamera = (runtime = runtimeRef.current) => {
    if (!runtimeModelKeyMatches(runtime, modelKeyRef.current) || !runtimeFramingBounds(runtime)) return;
    let saved = fullscreenCameraRef.current;
    if (saved && saved.modelKey !== modelKeyRef.current) {
      fullscreenCameraRef.current = null;
      saved = null;
    }
    const entering = previewModeRef.current;
    if (entering ? saved?.runtime === runtime : !saved) return;
    const controls = runtime.controls;
    // Drain pending OrbitControls damping before either snapshot is installed;
    // otherwise the next frame applies the outgoing camera's remaining drag.
    runWithoutPerspectiveEvents(() => {
      cancelCameraTransition(runtime, { scheduleIdle: false });
      clearKeyboardOrbitState(runtime.keyboardOrbitState);
      controls.autoRotate = false;
      controls.enableDamping = false;
      if (entering && !saved) {
        saved = { modelKey: modelKeyRef.current, runtime,
          camera: readPerspectiveSnapshot(runtime),
          interactiveFraming: runtime.interactiveFraming,
          viewportFitScale: runtime.viewportFitScale,
          userMovedCamera: runtime.userMovedCamera };
        fullscreenCameraRef.current = saved;
      }
      controls.update();
      if (entering) {
        saved.runtime = runtime;
        runtime.userMovedCamera = false;
        zoomRuntimeToBounds(runtime, runtimeFramingBounds(runtime), sceneScaleModeRef.current, {
          animate: false, modelOffset: modelTransformRef.current.offset,
          viewDirection: DEFAULT_VIEW_DIRECTION, viewUp: WORLD_UP,
        });
      } else {
        applyPerspectiveSnapshot(runtime, saved.camera, { scheduleIdle: false });
        runtime.interactiveFraming = saved.interactiveFraming;
        runtime.viewportFitScale = saved.viewportFitScale;
        runtime.userMovedCamera = saved.userMovedCamera;
        syncRuntimeViewportFraming(runtime);
        fullscreenCameraRef.current = null;
      }
      controls.enableDamping = true;
      controls.autoRotate = entering && previewOrbitSpeed > 0;
      captureRuntimeViewportFitScale(runtime);
      syncCameraZoomPercent(runtime);
      syncViewPlaneOrientation(runtime);
      runtime.requestRender?.();
    });
  };
  useLayoutEffect(() => {
    previewModeRef.current = previewMode;
    syncFullscreenCamera();
    // Entry/exit must precede ResizeObserver and the next presented frame.
  }, [previewMode, modelKey, viewerReadyTick]);
  const applyZoomPercent = useCallback((nextZoomPercent) => {
    const runtime = runtimeRef.current;
    if (!setRuntimeZoomPercent(runtime, nextZoomPercent)) {
      return;
    }
    syncCameraZoomPercent(runtime);
    emitPerspectiveChange(runtime);
    syncViewPlaneOrientation(runtime);
  }, [
    syncCameraZoomPercent,
    syncViewPlaneOrientation
  ]);
  const resetZoomAndPan = useCallback(({ animate = true } = {}) => {
    const runtime = runtimeRef.current;
    const reset = zoomRuntimeToBounds(
      runtime,
      runtimeFramingBounds(runtime, modelBounds),
      sceneScaleModeRef.current,
      {
        animate,
        modelOffset: modelTransformRef.current.offset,
        resetZoomBaseline: true
      }
    );
    if (reset && !animate) {
      syncCameraZoomPercent(runtime);
      emitPerspectiveChange(runtime);
      syncViewPlaneOrientation(runtime);
    }
    if (reset) {
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
    syncCameraZoomPercent(runtime);
    emitPerspectiveChange(runtime);
    syncViewPlaneOrientation(runtime);
    return true;
  }, [
    modelBounds,
    syncCameraZoomPercent,
    syncViewPlaneOrientation
  ]);
  // Stable, and built only from refs and setters: the view cube is memoized, so a viewer
  // render that changed nothing of the cube's (every animation frame) does not redraw it.
  const activateViewPlaneFace = useCallback((faceId) => {
    const runtime = runtimeRef.current;
    const face = VIEW_PLANE_FACE_BY_ID[faceId];
    if (!runtime || !face) {
      return false;
    }
    activeViewPlaneFaceRef.current = face.id;
    setActiveViewPlaneFace(face.id);
    const transitioned = transitionCameraToViewPreset(runtime, face);
    if (transitioned) {
      defaultPerspectiveResettingRef.current = false;
      setDefaultPerspectiveDetached(true);
    }
    return transitioned;
  }, []);
  const activateDefaultViewPlane = useCallback(() => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return false;
    }
    activeViewPlaneFaceRef.current = "";
    setActiveViewPlaneFace("");
    const transitioned = transitionCameraToViewPreset(runtime, VIEW_PLANE_DEFAULT_PRESET);
    if (transitioned) {
      defaultPerspectiveResettingRef.current = true;
      setDefaultPerspectiveDetached(false);
    }
    return transitioned;
  }, []);
  return {
    activateDefaultViewPlane,
    activateViewPlaneFace,
    applyInitialPerspective,
    applyZoomPercent,
    emitPerspectiveChange,
    resetZoomAndPan,
    syncCameraZoomPercent,
    syncFullscreenCamera,
    syncViewPlaneOrientation
  };
}
