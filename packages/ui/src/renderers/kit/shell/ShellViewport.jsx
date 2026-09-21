import { forwardRef, useCallback, useEffect, useImperativeHandle, useLayoutEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { createInspectEnvironmentResource, INSPECT_ENVIRONMENT_ID } from "@hardcore/core/common/inspectEnvironment.js";
import { PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS } from "@hardcore/core/common/photographicStudioRig.js";
import { resolveCadGridSettings } from "@hardcore/core/common/cadInk.js";
import { resolveDisplayMaterialSettings } from "@hardcore/core/common/sceneSettings.js";
import {
  CAMERA_PROJECTION, normalizeCameraProjection, perspectiveSnapshotMatchesScene, resolvePerspectiveSnapshot
} from "@hardcore/core/lib/perspective.js";
import { mergeBoundsList } from "@hardcore/core/lib/viewer/autoZoom.js";
import { applyRuntimeModelBounds, resolveRuntimeModelFloorZ, sceneRadiusForBounds } from "@hardcore/core/lib/viewer/modelRuntime.js";
import { defaultSceneGridRadius, getSceneScaleSettings, normalizeSceneScaleMode, VIEWER_SCENE_SCALE } from "@hardcore/core/lib/viewer/sceneScale.js";
import { buildCompositeScreenshotBlob, resolveElementBackgroundColor } from "@hardcore/core/lib/viewer/screenshotCapture.js";
import {
  applySceneBackground, BASE_VIEWER_THEME, disposeTexture, getViewerThemeValue, updateSpotLightTarget
} from "@hardcore/core/lib/viewer/stageTheme.js";
import { buildRuntimeInitializationAlert } from "@hardcore/core/lib/viewer/webglSupport.js";
import { THEME_FLOOR_MODES } from "@hardcore/core/lib/themeSettings.js";
import ViewPlaneControl from "../camera/ViewPlaneControl.js";
import { CAD_DEFAULT_VERTICAL_FOV_DEGREES, explicitViewerFocalLength, perspectiveDistanceScale } from "../camera/cameraLens.js";
import { PREVIEW_AUTO_ROTATE_SPEED } from "../camera/orbitControls.js";
import {
  DEFAULT_DAMPING_FACTOR, applyPerspectiveSnapshot, boundsModelRadius, cancelCameraTransition, captureRuntimeViewportFitScale,
  readOrthographicHalfHeight, readRuntimeZoomPercent, readScopedPerspectiveSnapshot, resetRuntimeZoomBaseline, setRuntimePerspectiveFocalLength, stepCameraTransition,
  syncRuntimeCameraClipPlanes, syncRuntimeCameraProjection, syncRuntimeViewportFraming, transitionCameraToPerspectiveSnapshot,
  zoomRuntimeToBounds
} from "../camera/runtimeCamera.js";
import { useViewportCamera } from "../camera/useViewportCamera.js";
import {
  DEFAULT_VIEW_DIRECTION, DEFAULT_VIEW_PLANE_ORIENTATION, KEYBOARD_ORBIT_NUDGE_RAD, VIEWING_MODE, VIEW_PLANE_FACES,
  VIEW_PLANE_FACE_BY_ID, WHEEL_PINCH_DELTA_BOOST, WORLD_UP, applyOrbitDelta, clearKeyboardOrbitState,
  getActiveViewPlaneFaceId, getKeyboardOrbitAxes, getKeyboardOrbitCommand, isPinchWheelEvent, isTrackpadLikeWheelEvent,
  reframeReason, runtimeFramingBounds, stepKeyboardOrbit, viewPlaneCameraBasis
} from "../camera/viewportCameraKit.js";
import { usePlanMode } from "../camera/usePlanMode.js";
import {
  ACCELERATED_WHEEL_ZOOM_SPEED, COARSE_POINTER_PINCH_ZOOM_SPEED, COARSE_POINTER_ZOOM_SPEED, DEFAULT_ZOOM_SPEED,
  TRACKPAD_PINCH_ZOOM_SPEED
} from "../camera/zoomSpeeds.js";
import { loadStudioScene, studioScene } from "../look/renderStudioChunk.js";
import { DEFAULT_LIGHTING, syncRuntimeScaledLightingAndShadow, updateGridHelper, updateStageEffects } from "../look/stageEffects.js";
import { createStudioEnvironmentCache } from "../look/studioEnvironmentCache.js";
import { isKitScene } from "../scene.js";
import LoadingIndicator from "../status/LoadingIndicator.js";
import DrawingOverlay from "../tools/draw/DrawingOverlay.jsx";
import { useDrawingViewLock } from "../tools/draw/useDrawingViewLock.js";
import { createViewerRenderStateResolver } from "../view-settings/renderState.js";
import { createViewUpdateGate } from "../view-settings/viewUpdateGate.js";
import { viewerTransitionBackdrop } from "../viewport/framePresentation.js";
import { IDLE_PIXEL_RATIO_CAP, INTERACTION_IDLE_DELAY_MS, INTERACTION_PIXEL_RATIO_CAP, getPixelRatioCap } from "../viewport/pixelRatio.js";
import { disposeSceneObject } from "../viewport/sceneObjects.js";
import { useViewerRuntime } from "../viewport/useViewerRuntime.js";

const VIEW_PLANE_CONTROL_SIZE = "6rem";
const STORED_CAMERA_COORDINATES = "cad-z-up-v1";
// The face a plan view looks from: straight down the vertical axis.
/** How long after the open-time fit the viewport and projection may still be settling. */
const OPEN_FIT_SETTLE_MS = 600;
const PLAN_VIEW_FACE = "z";
const PLAN_VIEW_BASIS = viewPlaneCameraBasis(VIEW_PLANE_FACE_BY_ID[PLAN_VIEW_FACE]);

// The stage group holds only what the look put there.
function clearGroup(group) {
  for (const child of [...(group?.children || [])]) disposeSceneObject(child);
}

/**
 * The viewport every file-family renderer mounts: the kit's WebGL runtime, camera,
 * look and Draw overlay around ONE scene the renderer built (`kit/scene.js`). It
 * adopts `scene.object3D`, frames `restBounds`, lights and floors `bounds`, hands
 * the scene the surface look the Display tab resolved, and never reaches inside
 * it. The scene stays its renderer's: this component detaches it, never disposes it.
 *
 * The imperative handle is what the shell drives: view settings preparation and
 * presentation, screenshot pixels, zoom, fit, reset and stored perspectives.
 */
const ShellViewport = forwardRef(function ShellViewport({
  scene = null,
  // Bumped by the renderer when the scene moved its own bounds (an animation frame).
  sceneRevision = 0,
  modelKey = "",
  presentationKey = "",
  sceneScaleMode = VIEWER_SCENE_SCALE.CAD,
  perspective = null,
  perspectiveRef = null,
  projection = CAMERA_PROJECTION.ORTHOGRAPHIC,
  // PLAN VIEW: the camera is locked looking straight down. Orthographic whatever Display
  // asks for (a plan is a measurable projection, not a photograph), no view cube, no
  // rotation, left-drag pans, and every reset lands back on top-down.
  planMode = false,
  focalLength = null,
  themeSettings = null,
  displaySettings = null,
  appearance = "light",
  receiveShadows = false,
  renderMode = false,
  renderConfiguration = null,
  quality = null,
  previewMode = false,
  previewOrbitSpeed = 1,
  isLoading = false,
  viewUpdate = null,
  loadingPresentation = null,
  drawingEnabled = false,
  drawing = null,
  onPerspectiveChange = null,
  onCameraZoomPercentChange = null,
  onPresentationChange = null,
  onViewerAlertChange = null,
  // A renderer's own layer over the canvas: a node, or `(viewport) => node` for one that
  // needs the viewport itself ({ runtimeRef, hostRef, viewerReadyTick }: the live runtime,
  // the element pointer events arrive on, and a tick that changes when the runtime does).
  children = null
}, ref) {
  if (scene && !isKitScene(scene)) {
    throw new Error("ShellViewport needs a kit scene: { object3D, bounds, dispose() } (kit/scene.js).");
  }
  const normalizedSceneScaleMode = normalizeSceneScaleMode(sceneScaleMode);
  const normalizedProjection = normalizeCameraProjection(planMode ? CAMERA_PROJECTION.ORTHOGRAPHIC : projection);
  const defaultGridRadius = defaultSceneGridRadius(normalizedSceneScaleMode);
  const viewerTheme = BASE_VIEWER_THEME;
  const interactionHostRef = useRef(null);
  const mountRef = useRef(null);
  const runtimeRef = useRef(null);
  const perspectiveChangeRef = useRef(onPerspectiveChange);
  const viewerAlertChangeRef = useRef(onViewerAlertChange);
  viewerAlertChangeRef.current = onViewerAlertChange;
  const lastEmittedPerspectiveRef = useRef(null);
  const lastProjectionRef = useRef(normalizedProjection);
  const suppressPerspectiveEventsRef = useRef(0);
  const viewUpdateBindingRef = useRef(null);
  viewUpdateBindingRef.current = viewUpdate?.binding;
  useLayoutEffect(() => {
    const runtime = runtimeRef.current;
    if (runtime && viewUpdate?.revision) {
      runtime.viewUpdateGate ??= createViewUpdateGate(runtime);
      runtime.viewUpdateGate.hold();
    }
  }, [viewUpdate?.revision]);
  const framedModelKeyRef = useRef("");
  const framedBoundsRef = useRef(null);
  // Inspect's orthographic frustum and Render's photographic lens are two cameras:
  // each fits the rest placement itself rather than inheriting the other's pose.
  const framedViewingModeRef = useRef("");
  const modelTransformRef = useRef({ offset: new THREE.Vector3(0, 0, 0) });
  // The camera hook reports whether the default view was left; this viewport draws nothing from it.
  const [, setDefaultPerspectiveDetached] = useState(false);
  const [error, setError] = useState("");
  const [viewerReadyTick, setViewerReadyTick] = useState(0);
  const [runtimeResetToken, setRuntimeResetToken] = useState(0);
  const presentationEpoch = useMemo(() => ({}), [runtimeResetToken]);
  const [presentedEpoch, setPresentedEpoch] = useState(null);
  const [presentedKey, setPresentedKey] = useState("");
  const resolvedPresentationKey = String(presentationKey || modelKey || "");
  const presentationRequestRef = useRef({ key: "", ready: false });
  const handleFramePresented = useCallback((key) => {
    setPresentedEpoch(presentationEpoch);
    setPresentedKey(String(key || ""));
  }, [presentationEpoch]);
  useLayoutEffect(() => {
    // Cover only an actual context recovery. View edits reuse the live canvas.
    const canvas = runtimeRef.current?.renderer?.domElement;
    if (canvas) canvas.style.visibility = "hidden";
  }, [presentationEpoch]);
  useLayoutEffect(() => {
    presentationRequestRef.current = { key: resolvedPresentationKey, ready: false };
  }, [presentationEpoch, resolvedPresentationKey]);
  const markPresentationReady = useCallback((runtime) => {
    if (!runtime || !resolvedPresentationKey) return;
    presentationRequestRef.current = { key: resolvedPresentationKey, ready: true };
    runtime.requestRender?.();
  }, [resolvedPresentationKey]);
  const [activeViewPlaneFace, setActiveViewPlaneFace] = useState("");
  const [viewPlaneOrientation, setViewPlaneOrientation] = useState(DEFAULT_VIEW_PLANE_ORIENTATION);
  const [cameraZoomPercent, setCameraZoomPercent] = useState(100);
  const activeViewPlaneFaceRef = useRef("");
  const defaultPerspectiveResettingRef = useRef(false);
  const previewModeRef = useRef(previewMode);
  // The presentation camera never becomes the file's stored camera.
  const fullscreenCameraRef = useRef(null);
  const perspectivePropRef = useRef(perspective);
  const modelKeyRef = useRef(modelKey);
  const sceneScaleModeRef = useRef(normalizedSceneScaleMode);
  const cameraMovedRef = useRef(null);

  const resolveViewerRenderState = useMemo(() => createViewerRenderStateResolver(), []);
  const renderState = useMemo(() => resolveViewerRenderState({ themeSettings, displaySettings }),
    [resolveViewerRenderState, themeSettings, displaySettings]);
  const normalizedThemeSettings = renderState.themeSettings;
  const normalizedDisplaySettings = renderState.displaySettings;
  const surfaceSettings = normalizedDisplaySettings.surfaces;
  const photographicLighting = renderMode && renderConfiguration?.lighting?.enabled !== false;
  const materialSettings = useMemo(() => resolveDisplayMaterialSettings(
    photographicLighting ? PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS : normalizedThemeSettings.materials,
    normalizedDisplaySettings.partColor
  ), [normalizedDisplaySettings.partColor, normalizedThemeSettings.materials, photographicLighting]);
  // The look a scene wears. Photographic Render keeps what the file authored; the
  // Surfaces section (colour mode, style, opacity) applies in both.
  const surfaceLook = useMemo(() => ({
    materialSettings, authored: photographicLighting,
    surface: surfaceSettings ? { style: surfaceSettings.style, opacity: surfaceSettings.opacity } : null
  }), [materialSettings, photographicLighting, surfaceSettings]);
  const floorSettings = normalizedThemeSettings.floor || {};
  const guideFloorSettings = useMemo(() => ({
    ...floorSettings,
    grid: resolveCadGridSettings(normalizedDisplaySettings.guides.grid, { colorMode: appearance }),
    axis: normalizedDisplaySettings.guides.axis
  }), [floorSettings, normalizedDisplaySettings.guides, appearance]);
  const resolvedFloorMode = floorSettings.enabled === true ? THEME_FLOOR_MODES.STAGE : THEME_FLOOR_MODES.NONE;
  const floorFollowsModel = floorSettings.enabled === true && floorSettings.followModel !== false;
  const renderEnvironmentMapSize = Number(quality?.environmentMapSize) > 0 ? Number(quality.environmentMapSize) : 256;
  const renderShadowMapSize = receiveShadows && Number(quality?.shadowMapSize) > 0 ? Number(quality.shadowMapSize) : 2048;
  const renderShadowMapSizeRef = useRef(renderShadowMapSize);
  renderShadowMapSizeRef.current = renderShadowMapSize;

  // Render's studio is a lazy chunk. The shell normally warms it; this is the
  // backstop for a cold cache and a session restored straight into Render.
  const [studioSceneTick, setStudioSceneTick] = useState(() => (studioScene() ? 1 : 0));
  useEffect(() => {
    if (!renderMode || studioScene()) return undefined;
    let cancelled = false;
    loadStudioScene().then(
      () => { if (!cancelled) setStudioSceneTick((tick) => tick + 1); },
      (loadError) => {
        if (cancelled) return;
        viewerAlertChangeRef.current?.({
          severity: "error",
          summary: "Render unavailable",
          title: "Couldn't load the Render studio",
          message: "The photographic studio is fetched the first time Render is opened, and that request did not complete.",
          recovery: "Check the connection to the viewer and reload the page, then switch to Render again.",
          details: String(loadError?.message || loadError)
        });
        console.error("Failed to load the Render studio chunk", loadError);
      }
    );
    return () => { cancelled = true; };
  }, [renderMode]);

  const renderConfigurationRef = useRef(renderConfiguration);
  renderConfigurationRef.current = renderConfiguration;
  const applyActivePhotographicStudio = useCallback((runtime, bounds = runtime?.modelBounds) => {
    const configuration = renderConfigurationRef.current;
    const studio = studioScene();
    if (!renderMode || !configuration || !runtime?.THREE || !studio) return;
    // The studio floor is sized and centred from the REST placement, as the grid is: a pose or a
    // routine never rescales the ground under the model. Its lights and its height follow the model.
    const studioState = studio.applyPhotographicStudio(runtime.THREE, runtime, configuration, {
      bounds, groundBounds: runtime.zeroPoseBounds || null,
      sceneScale: normalizedSceneScaleMode, shadowMapSize: renderShadowMapSizeRef.current
    });
    runtime.photographicGroundZ = Number.isFinite(Number(studioState?.ground?.position?.z))
      ? Number(studioState.ground.position.z) : null;
  }, [normalizedSceneScaleMode, renderMode, studioSceneTick]);
  useEffect(() => {
    applyActivePhotographicStudio(runtimeRef.current);
  }, [applyActivePhotographicStudio, renderConfiguration, viewerReadyTick]);

  const updateActiveGridHelper = useCallback((runtime, activeViewerTheme, radius, floorZ = 0,
    scaleMode = VIEWER_SCENE_SCALE.CAD, floorMode = THEME_FLOOR_MODES.STAGE) => updateGridHelper(
    runtime, activeViewerTheme, radius, floorZ, scaleMode, floorMode, guideFloorSettings
  ), [guideFloorSettings]);

  perspectivePropRef.current = perspective;
  modelKeyRef.current = modelKey;
  sceneScaleModeRef.current = normalizedSceneScaleMode;
  const runWithoutPerspectiveEvents = (callback) => {
    suppressPerspectiveEventsRef.current += 1;
    try { return callback(); }
    finally { suppressPerspectiveEventsRef.current = Math.max(0, suppressPerspectiveEventsRef.current - 1); }
  };
  const coordinateSystemFor = useCallback(() => STORED_CAMERA_COORDINATES, []);
  const {
    activateDefaultViewPlane, activateViewPlaneFace, applyInitialPerspective, applyZoomPercent, emitPerspectiveChange,
    resetZoomAndPan, syncCameraZoomPercent, syncFullscreenCamera, syncViewPlaneOrientation
  } = useViewportCamera({
    coordinateSystemFor, activeViewPlaneFaceRef, cameraZoomPercent, defaultPerspectiveResettingRef, fullscreenCameraRef,
    lastEmittedPerspectiveRef, cameraMovedRef, modelBounds: scene?.restBounds || scene?.bounds || null, modelKey, modelKeyRef,
    modelTransformRef, onCameraZoomPercentChange, perspectiveChangeRef, perspectivePropRef, perspectiveRef, previewMode,
    previewModeRef, previewOrbitSpeed, runWithoutPerspectiveEvents, runtimeRef, sceneScaleModeRef, setActiveViewPlaneFace,
    setCameraZoomPercent, setDefaultPerspectiveDetached, setViewPlaneOrientation, suppressPerspectiveEventsRef, viewerReadyTick
  });
  // The open-time fit is taken under the lens the viewport opens with, and the file's own
  // projection arrives a moment later. CONVERTING that fit to the other projection is not the
  // same as fitting under it: a wide, flat model came up at ~89% of its own ruler. So while
  // the camera is still the one the viewer itself fitted, a projection change re-FITS along
  // the direction it looks now (a view-cube face is still the viewer's framing).
  //
  // Only while opening settles (`armOpenFit`). Afterwards a viewport RESIZE keeps its
  // long-standing answer (`syncRuntimeViewportFraming`: the model holds its apparent size),
  // because opening or closing a panel is not a request to reframe the model.
  //
  // A camera TRANSITION in flight is a deliberate move being made right now (a view-cube
  // face, entering a plan view): re-fitting mid-flight would read the half-turned direction
  // as "the direction it looks now" and cancel the move. So the open fit waits.
  // Opening SETTLES: after the fit, the Inspector column takes its width and the file's
  // projection arrives, each a beat later. That stretch is the viewer's to re-fit in; once it
  // has been quiet for OPEN_FIT_SETTLE_MS, opening is over, and a resize rescales and a
  // projection change converts, as they always have for a view a person is looking at.
  const armOpenFit = useCallback((runtime) => {
    runtime.openFitPending = true;
    clearTimeout(runtime.openFitTimer);
    runtime.openFitTimer = setTimeout(() => { runtime.openFitPending = false; }, OPEN_FIT_SETTLE_MS);
  }, []);
  const refitOpenFraming = useCallback((runtime) => {
    const framing = runtime.interactiveFraming;
    const target = runtime.controls?.target;
    if (!runtime.openFitPending || runtime.userMovedCamera || previewModeRef.current
      || runtime.cameraTransition || !framing?.bounds || !target) return false;
    const fitted = zoomRuntimeToBounds(runtime, framing.bounds, sceneScaleModeRef.current, {
      animate: false, modelOffset: modelTransformRef.current.offset,
      viewDirection: runtime.camera.position.clone().sub(target).normalize().toArray(), viewUp: runtime.camera.up.toArray()
    });
    if (!fitted) return false;
    captureRuntimeViewportFitScale(runtime);
    resetRuntimeZoomBaseline(runtime);
    armOpenFit(runtime);
    return true;
  }, [armOpenFit]);
  const handleViewportResize = useCallback(() => {
    const runtime = runtimeRef.current;
    if (!runtime) return;
    if (!refitOpenFraming(runtime)) syncRuntimeViewportFraming(runtime);
    syncCameraZoomPercent(runtime);
    emitPerspectiveChange(runtime);
  }, [syncCameraZoomPercent]);

  // Rotation off, left-drag panning, no vertical origin axis. Everything else about the
  // lock — the projection, the hidden cube, where a reset lands — is this component's.
  usePlanMode({ planMode, runtimeRef, viewerReadyTick });
  const planModeRef = useRef(planMode);
  planModeRef.current = planMode;

  const hasViewportContent = Boolean(scene);
  const drawingOverlayActive = drawingEnabled && !previewMode && hasViewportContent;
  const { drawingControllerRef, handleDrawingContent, handleDrawingReady, followDrawingViewport } = useDrawingViewLock({
    active: drawingOverlayActive, drawing, runtimeRef, mountRef, viewerReadyTick
  });

  useImperativeHandle(ref, () => ({
    async prepareViewSettings(nextScene, signal) {
      const runtime = runtimeRef.current;
      if (nextScene.render.enabled) {
        const studio = await loadStudioScene();
        signal.throwIfAborted();
        if (runtime?.renderer && nextScene.view.lighting.enabled) {
          runtime.studioEnvironmentCache ??= createStudioEnvironmentCache();
          await runtime.studioEnvironmentCache.prepare(studio, runtime.renderer,
            nextScene.render.configuration, nextScene.quality.environmentMapSize, signal, runtime.environmentResource);
        }
      }
    },
    presentViewSettings() { return runtimeRef.current?.viewUpdateGate?.present(); },
    // The viewport produces pixels. Its host owns clipboard and prompt delivery.
    async captureScreenshotBlob() {
      await viewUpdateBindingRef.current?.whenReady();
      const runtime = runtimeRef.current;
      if (!runtime?.renderer || !runtime?.scene || !runtime?.camera) throw new Error("The viewer is not ready");
      return await buildCompositeScreenshotBlob(runtime, drawingControllerRef.current?.inkCanvas() || null, {
        backgroundColor: resolveElementBackgroundColor(runtime.renderer.domElement)
      });
    },
    activateViewPlaneFace,
    activateDefaultViewPlane,
    applyZoomPercent,
    requestRender() { runtimeRef.current?.requestRender?.(); },
    resetView() {
      const runtime = runtimeRef.current;
      // A locked plan view resets to its OWN top-down, never to the default three-quarter
      // orientation. One place, so the zoom header, "Reset model" and live `resetCamera`
      // (which all land here) each re-assert the lock as they re-frame.
      const plan = planModeRef.current && PLAN_VIEW_BASIS;
      const reset = zoomRuntimeToBounds(runtime, runtimeFramingBounds(runtime, scene?.restBounds || scene?.bounds), sceneScaleModeRef.current, {
        animate: true, modelOffset: modelTransformRef.current.offset, resetZoomBaseline: true,
        viewDirection: plan ? PLAN_VIEW_BASIS.direction : DEFAULT_VIEW_DIRECTION,
        viewUp: plan ? PLAN_VIEW_BASIS.up : WORLD_UP
      });
      if (reset) {
        activeViewPlaneFaceRef.current = plan ? PLAN_VIEW_FACE : "";
        setActiveViewPlaneFace(plan ? PLAN_VIEW_FACE : "");
        defaultPerspectiveResettingRef.current = !plan;
        setDefaultPerspectiveDetached(Boolean(plan));
      }
      return reset;
    },
    getPerspective() {
      return readScopedPerspectiveSnapshot(runtimeRef.current, {
        modelKey, sceneScaleMode: normalizedSceneScaleMode, coordinateSystem: STORED_CAMERA_COORDINATES
      });
    },
    setPerspective(nextPerspective, options = {}) {
      // A camera somebody hands the viewport — a host command, a session being restored —
      // replaces the open-time fit, so re-fitting it on the next resize would throw it away.
      if (runtimeRef.current) runtimeRef.current.openFitPending = false;
      if (options?.animate) return transitionCameraToPerspectiveSnapshot(runtimeRef.current, nextPerspective, options);
      const applied = applyPerspectiveSnapshot(runtimeRef.current, nextPerspective);
      if (applied && options?.resetZoomBaseline) {
        resetRuntimeZoomBaseline(runtimeRef.current);
        syncCameraZoomPercent(runtimeRef.current);
      }
      return applied;
    },
    resetZoom() { return resetZoomAndPan({ animate: true }); },
    // The scene moved its own bounds (a pose, a frame of a routine): lighting, shadows and
    // the floor follow it NOW, with no React render, no re-adoption and no reframe.
    syncSceneBounds() {
      const runtime = runtimeRef.current;
      if (!runtime?.kitScene || runtime.kitScene !== scene) return false;
      fitStageToSceneRef.current(runtime, scene);
      runtime.invalidateShadows?.();
      runtime.requestRender?.();
      return true;
    },
    // Frame part of the scene (a selection). The camera moves; 100% keeps meaning the rest framing.
    zoomToBounds(bounds, { animate = true } = {}) {
      const runtime = runtimeRef.current;
      if (!bounds || !runtime) return false;
      return zoomRuntimeToBounds(runtime, bounds, sceneScaleModeRef.current, { animate, modelOffset: modelTransformRef.current.offset });
    },
    zoomToFit({ animate = true } = {}) {
      const runtime = runtimeRef.current;
      const fitted = zoomRuntimeToBounds(runtime, runtimeFramingBounds(runtime, scene?.restBounds || scene?.bounds),
        sceneScaleModeRef.current, { animate, modelOffset: modelTransformRef.current.offset, resetZoomBaseline: true });
      if (fitted && !animate) {
        emitPerspectiveChange(runtime);
        syncViewPlaneOrientation(runtime);
      }
      return fitted;
    }
  }), [activateViewPlaneFace, modelKey, normalizedSceneScaleMode, resetZoomAndPan, scene, syncCameraZoomPercent, syncViewPlaneOrientation]);

  // Read-only debug/test seam: the LIVE camera of the viewport that mounted last, so a
  // browser test can assert that moving a model leaves the framing exactly where it was.
  useEffect(() => {
    const read = () => {
      const active = runtimeRef.current;
      const camera = active?.camera;
      if (!camera) return null;
      return {
        projection: camera.isOrthographicCamera ? "orthographic" : "perspective",
        position: camera.position.toArray(), target: active.controls?.target?.toArray?.() || null, up: camera.up.toArray(),
        zoom: Number(camera.zoom), halfHeight: readOrthographicHalfHeight(active), zoomPercent: readRuntimeZoomPercent(active),
        originalBounds: active.zeroPoseBounds
      };
    };
    // Beside it: where the STAGE stands. The ground's size comes from the rest placement and
    // must not change under a pose; the bounds lighting is fitted to and the floor's height do.
    const stage = () => {
      const active = runtimeRef.current;
      const ground = active?.photographicStudio?.ground || null;
      return active ? { gridRadius: active.gridRadius ?? null, bounds: active.modelBounds || null,
        floorZ: active.modelFloorZBelowModel ?? null, studioGroundZ: active.photographicGroundZ ?? null,
        studioGround: ground ? { size: ground.scale.x, center: [ground.position.x, ground.position.y] } : null } : null;
    };
    Object.assign(window, { __cadCamera: read, __cadStage: stage });
    return () => {
      if (window.__cadCamera === read) delete window.__cadCamera;
      if (window.__cadStage === stage) delete window.__cadStage;
    };
  }, []);
  useEffect(() => { perspectiveChangeRef.current = onPerspectiveChange; }, [onPerspectiveChange]);
  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) return undefined;
    runtime.onZoomChange = syncCameraZoomPercent;
    syncCameraZoomPercent(runtime);
    return () => { if (runtime.onZoomChange === syncCameraZoomPercent) runtime.onZoomChange = null; };
  }, [syncCameraZoomPercent, viewerReadyTick]);

  const handleRuntimeContextRestored = useCallback(() => {
    framedModelKeyRef.current = "";
    framedBoundsRef.current = null;
    framedViewingModeRef.current = "";
    lastEmittedPerspectiveRef.current = null;
    defaultPerspectiveResettingRef.current = false;
    viewerAlertChangeRef.current?.(null);
    setDefaultPerspectiveDetached(false);
    setRuntimeResetToken((value) => value + 1);
  }, []);
  const handleRuntimeInitializationError = useCallback((runtimeError) => {
    viewerAlertChangeRef.current?.(buildRuntimeInitializationAlert(runtimeError));
  }, []);
  // The scene is its renderer's: teardown detaches it and leaves disposal to its owner.
  const detachScene = useCallback((runtime) => {
    runtime?.kitScene?.object3D?.removeFromParent?.();
    if (runtime) { runtime.kitScene = null; runtime.hasVisibleModel = false; }
    return null;
  }, []);

  useViewerRuntime({
    mountRef, runtimeRef, previewModeRef, setError, setViewerReadyTick, viewerTheme, emitPerspectiveChange,
    setActiveViewPlaneFace, activeViewPlaneFaceRef, stepCameraTransition, stepKeyboardOrbit, getActiveViewPlaneFaceId,
    cancelCameraTransition, clearKeyboardOrbitState, isTrackpadLikeWheelEvent, isPinchWheelEvent, WHEEL_PINCH_DELTA_BOOST,
    getKeyboardOrbitCommand, getKeyboardOrbitAxes, applyOrbitDelta, getViewerThemeValue, getPixelRatioCap,
    applySceneBackground, onViewportResize: handleViewportResize, applyInitialPerspective,
    updateGridHelper: updateActiveGridHelper, clearSceneGroup: clearGroup, disposeScene: detachScene,
    disposeStudio: (runtime) => studioScene()?.disposePhotographicStudio(runtime),
    disposeSceneObject, disposeTexture, syncViewPlaneOrientation, BASE_VIEWER_THEME, DEFAULT_LIGHTING,
    DEFAULT_DAMPING_FACTOR, DEFAULT_ZOOM_SPEED, COARSE_POINTER_ZOOM_SPEED, INTERACTION_PIXEL_RATIO_CAP,
    IDLE_PIXEL_RATIO_CAP: Number(quality?.idlePixelRatioCap) > 0 ? Number(quality.idlePixelRatioCap) : IDLE_PIXEL_RATIO_CAP,
    INTERACTION_IDLE_DELAY_MS, TRACKPAD_PINCH_ZOOM_SPEED, COARSE_POINTER_PINCH_ZOOM_SPEED, ACCELERATED_WHEEL_ZOOM_SPEED,
    KEYBOARD_ORBIT_NUDGE_RAD, defaultGridRadius, sceneScaleMode: normalizedSceneScaleMode, floorMode: resolvedFloorMode,
    renderMode, onInitializationError: handleRuntimeInitializationError, onFramePresented: handleFramePresented,
    presentationRequestRef, onContextRestored: handleRuntimeContextRestored, runtimeResetToken
  });

  // Lens.
  useEffect(() => {
    const runtime = runtimeRef.current;
    const camera = runtime?.perspectiveCamera;
    const nextFocalLength = explicitViewerFocalLength(focalLength);
    if (runtime?.controls && camera && nextFocalLength == null) {
      delete camera.userData.cadFocalLength;
      if (Math.abs(camera.fov - CAD_DEFAULT_VERTICAL_FOV_DEGREES) >= 1e-4) {
        camera.fov = CAD_DEFAULT_VERTICAL_FOV_DEGREES;
        camera.updateProjectionMatrix();
        camera.lookAt(runtime.controls.target);
        runtime.controls.update?.();
        emitPerspectiveChange(runtime);
        runtime.requestRender?.();
      }
      return;
    }
    if (!runtime?.controls || !camera?.getFocalLength || nextFocalLength == null) return;
    const previousFocalLength = camera.getFocalLength();
    if (Math.abs(previousFocalLength - nextFocalLength) < 1e-4) {
      camera.userData.cadFocalLength = nextFocalLength;
      return;
    }
    const previousFov = camera.fov;
    const offset = camera.position.clone().sub(runtime.controls.target);
    setRuntimePerspectiveFocalLength(runtime, nextFocalLength);
    if (runtime.camera === camera && offset.lengthSq() > 1e-8) {
      const distanceScale = perspectiveDistanceScale(previousFov, camera.fov);
      if (Number.isFinite(distanceScale) && distanceScale > 0) {
        camera.position.copy(runtime.controls.target).add(offset.multiplyScalar(distanceScale));
      }
    }
    camera.lookAt(runtime.controls.target);
    runtime.controls.update?.();
    emitPerspectiveChange(runtime);
    runtime.scheduleIdleQuality?.();
    runtime.requestRender?.();
  }, [focalLength, renderMode, viewerReadyTick]);

  useEffect(() => {
    if (runtimeRef.current) runtimeRef.current.sceneScaleMode = normalizedSceneScaleMode;
  }, [normalizedSceneScaleMode]);

  // Shadow map size.
  useEffect(() => {
    const runtime = runtimeRef.current;
    if (renderMode) { applyActivePhotographicStudio(runtime); return; }
    const shadow = runtime?.keyLight?.shadow;
    if (!runtime?.THREE || !shadow?.mapSize) return;
    if (Math.abs(Number(runtime.shadowMapSize) - renderShadowMapSize) < 1) return;
    const previousMap = shadow.map;
    shadow.map = null;
    previousMap?.dispose?.();
    shadow.mapSize.set(renderShadowMapSize, renderShadowMapSize);
    runtime.shadowMapSize = renderShadowMapSize;
    if (runtime.modelBounds) {
      applyRuntimeModelBounds(runtime.THREE, runtime, runtime.modelBounds, normalizedSceneScaleMode, { shadowMapSize: renderShadowMapSize });
    }
    runtime.invalidateShadows?.();
    runtime.requestRender?.();
  }, [applyActivePhotographicStudio, normalizedSceneScaleMode, renderMode, renderShadowMapSize, viewerReadyTick]);

  // Projection. Its dependencies are deliberately the projection and readiness alone:
  // the camera helpers are fresh closures every render.
  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) return;
    const projectionChanged = lastProjectionRef.current !== normalizedProjection;
    lastProjectionRef.current = normalizedProjection;
    if (!syncRuntimeCameraProjection(runtime, normalizedProjection,
      projectionChanged ? { scheduleIdle: false, requestRender: false } : undefined)) return;
    if (refitOpenFraming(runtime)) syncCameraZoomPercent(runtime);
    emitPerspectiveChange(runtime);
    syncViewPlaneOrientation(runtime);
  }, [normalizedProjection, viewerReadyTick]);

  // The scene's surface look, and whether it takes shadows.
  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime || !scene) return;
    scene.setSurfaceLook?.(surfaceLook);
    scene.object3D.traverse((object) => { if (object.isMesh) object.receiveShadow = receiveShadows; });
    // Read-only test seam: how often a scene was dressed. A guide's or the stage's paint must never be one.
    (window.__viewerSurfaceLooks ||= { count: 0 }).count += 1;
    runtime.requestRender();
  }, [scene, surfaceLook, receiveShadows, viewerReadyTick]);

  // The look: lighting rig or studio, background, floor, grid and axes.
  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) return;
    if (photographicLighting) {
      for (const light of ["hemisphereLight", "ambientLight", "keyLight", "fillLight", "rimLight", "spotLight", "pointLight"]) {
        runtime[light].visible = false;
      }
      runtime.gridConfig = null;
      updateActiveGridHelper(runtime, viewerTheme, runtime.gridRadius ?? defaultGridRadius, 0, normalizedSceneScaleMode, THEME_FLOOR_MODES.NONE);
      clearGroup(runtime.stageGroup);
      applyActivePhotographicStudio(runtime);
      runtime.requestRender();
      return;
    }
    if (!renderMode) studioScene()?.disposePhotographicStudio(runtime);
    const lighting = normalizedThemeSettings.lighting;
    applySceneBackground(runtime, viewerTheme, normalizedThemeSettings.background);
    runtime.renderer.toneMappingExposure = Math.max(lighting.toneMappingExposure, 0.05);
    runtime.hemisphereLight.visible = lighting.hemisphere.enabled;
    runtime.hemisphereLight.color.set(lighting.hemisphere.skyColor);
    runtime.hemisphereLight.groundColor.set(lighting.hemisphere.groundColor);
    runtime.hemisphereLight.intensity = lighting.hemisphere.intensity;
    runtime.ambientLight.visible = lighting.ambient.enabled;
    runtime.ambientLight.color.set(lighting.ambient.color);
    runtime.ambientLight.intensity = lighting.ambient.intensity;
    runtime.keyLight.visible = lighting.directional.enabled;
    runtime.keyLight.color.set(lighting.directional.color);
    runtime.keyLight.intensity = lighting.directional.intensity;
    runtime.fillLight.visible = lighting.fill.enabled && lighting.fill.intensity > 0.0001;
    runtime.fillLight.color.set(lighting.fill.color);
    runtime.fillLight.intensity = Math.max(lighting.fill.intensity, 0);
    runtime.rimLight.visible = lighting.rim.enabled && lighting.rim.intensity > 0.0001;
    runtime.rimLight.color.set(lighting.rim.color);
    runtime.rimLight.intensity = Math.max(lighting.rim.intensity, 0);
    runtime.spotLight.visible = lighting.spot.enabled;
    runtime.spotLight.color.set(lighting.spot.color);
    runtime.spotLight.intensity = lighting.spot.intensity;
    runtime.spotLight.angle = lighting.spot.angle;
    runtime.pointLight.visible = lighting.point.enabled;
    runtime.pointLight.color.set(lighting.point.color);
    runtime.pointLight.intensity = lighting.point.intensity;
    syncRuntimeScaledLightingAndShadow(runtime.THREE, runtime, lighting, runtime.modelRadius ?? runtime.gridRadius ?? defaultGridRadius,
      runtime.modelBounds, normalizedSceneScaleMode, renderShadowMapSizeRef.current);
    updateSpotLightTarget(runtime);
    // One primary shadow; the spot light drives the floor glow.
    runtime.keyLight.castShadow = runtime.keyLight.visible && runtime.softwareRendering !== true;
    runtime.spotLight.castShadow = false;
    runtime.gridConfig = null;
    const floorZCandidate = floorFollowsModel ? runtime.modelFloorZBelowModel : runtime.modelFloorZBase;
    const floorZ = Number.isFinite(floorZCandidate) ? floorZCandidate : runtime.gridFloorZ ?? 0;
    updateActiveGridHelper(runtime, viewerTheme, runtime.gridRadius ?? defaultGridRadius, floorZ, normalizedSceneScaleMode, resolvedFloorMode);
    updateSpotLightTarget(runtime);
    if (runtime.hasVisibleModel) {
      updateStageEffects(runtime, viewerTheme, normalizedThemeSettings, runtime.gridRadius ?? defaultGridRadius, floorZ, resolvedFloorMode, normalizedSceneScaleMode);
    } else clearGroup(runtime.stageGroup);
    if (renderMode) applyActivePhotographicStudio(runtime);
    runtime.requestRender();
  }, [
    defaultGridRadius, photographicLighting, appearance, normalizedThemeSettings, normalizedSceneScaleMode, resolvedFloorMode,
    renderMode, floorFollowsModel, viewerReadyTick, viewerTheme, updateActiveGridHelper, applyActivePhotographicStudio
  ]);

  // The reflection environment: Inspect's small fill for authored materials, or the studio's.
  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime?.THREE || !runtime?.scene) return;
    const studio = studioScene();
    const clearEnvironmentResource = () => {
      runtime.scene.environment = null;
      if (!runtime.studioEnvironmentCache?.owns(runtime.environmentResource)) runtime.environmentResource?.dispose();
      runtime.environmentResource = null;
      runtime.environmentResourceIdentity = "";
    };
    // Render asked for, chunk not here yet: leaving environmentReady false keeps the
    // canvas under the destination backdrop until this re-runs with the studio loaded.
    if (renderMode && renderConfiguration && !studio) { runtime.environmentReady = false; return; }
    if (!photographicLighting || !renderConfiguration) {
      runtime.environmentReady = true;
      if (scene?.keepsAuthoredFinish) {
        if (runtime.environmentResourceIdentity !== INSPECT_ENVIRONMENT_ID) {
          clearEnvironmentResource();
          runtime.environmentResource = createInspectEnvironmentResource(runtime.THREE);
          runtime.environmentResourceIdentity = INSPECT_ENVIRONMENT_ID;
        }
        runtime.scene.environment = runtime.environmentResource.texture;
        runtime.scene.environmentIntensity = 1;
      } else {
        clearEnvironmentResource();
        runtime.scene.environmentIntensity = 0;
      }
      if (renderMode) applyActivePhotographicStudio(runtime);
      else applySceneBackground(runtime, viewerTheme, normalizedThemeSettings.background);
      viewerAlertChangeRef.current?.(null);
      runtime.requestRender();
      return;
    }
    runtime.scene.environmentIntensity = 1;
    const applyBackgroundFallback = () => {
      clearEnvironmentResource();
      applyActivePhotographicStudio(runtime);
      runtime.environmentReady = true;
      runtime.requestRender();
    };
    try {
      const resourceIdentity = studio.environmentResourceIdentity(renderConfiguration, { size: renderEnvironmentMapSize });
      if (!resourceIdentity) {
        viewerAlertChangeRef.current?.(null);
        applyBackgroundFallback();
        return;
      }
      if (!runtime.environmentResource || runtime.environmentResourceIdentity !== resourceIdentity) {
        const nextResource = runtime.studioEnvironmentCache?.get(resourceIdentity)
          || studio.createEnvironmentResource(runtime.renderer, renderConfiguration, { size: renderEnvironmentMapSize });
        const previousResource = runtime.environmentResource;
        runtime.scene.environment = null;
        runtime.environmentResource = nextResource;
        runtime.environmentResourceIdentity = resourceIdentity;
        if (!runtime.studioEnvironmentCache?.owns(previousResource)) studio.disposeEnvironmentResource(previousResource);
      }
      runtime.scene.environment = runtime.environmentResource.texture;
      runtime.environmentReady = true;
      viewerAlertChangeRef.current?.(null);
      applyActivePhotographicStudio(runtime);
      runtime.requestRender();
    } catch (environmentError) {
      applyBackgroundFallback();
      viewerAlertChangeRef.current?.({
        severity: "warning",
        summary: "Environment unavailable",
        title: "Couldn’t prepare studio lighting",
        message: "The reflection environment could not be created. The model is shown with the studio’s direct lighting, so reflective materials may look different.",
        recovery: "Reload the viewer to retry the studio environment.",
        details: String(environmentError?.message || environmentError)
      });
      console.error("Failed to apply environment resource", environmentError);
    }
  }, [
    applyActivePhotographicStudio, renderConfiguration, renderEnvironmentMapSize, photographicLighting,
    scene?.keepsAuthoredFinish, renderMode, studioSceneTick, viewerReadyTick, viewerTheme, normalizedThemeSettings.background
  ]);

  // Fullscreen's orbit.
  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) return;
    if (runtime.interactionState.restoreTimerId) {
      window.clearTimeout(runtime.interactionState.restoreTimerId);
      runtime.interactionState.restoreTimerId = 0;
    }
    clearKeyboardOrbitState(runtime.keyboardOrbitState);
    // Fullscreen installs a presentation camera and leaving restores the file's own: neither
    // is the open-time fit, so the viewport stops treating the pose as its to re-fit.
    runtime.openFitPending = false;
    const orbitActive = previewMode && previewOrbitSpeed > 0;
    runtime.previewOrbitEnabled = orbitActive;
    runtime.orbitControlsLastTimestamp = 0;
    runtime.controls.autoRotate = orbitActive;
    runtime.controls.autoRotateSpeed = PREVIEW_AUTO_ROTATE_SPEED * previewOrbitSpeed;
    if (previewMode) runtime.controls.enabled = true;
    if (!drawingOverlayActive) runtime.controls.enableDamping = true;
    runtime.controls.dampingFactor = DEFAULT_DAMPING_FACTOR;
    if (orbitActive) {
      cancelCameraTransition(runtime, { scheduleIdle: false });
      runtime.beginInteraction?.();
    } else runtime.scheduleIdleQuality();
    runtime.requestRender();
  }, [previewMode, previewOrbitSpeed, viewerReadyTick]);

  // Everything that follows where the scene IS, and nothing that frames it: lighting and
  // shadow reach and the floor's height. The ground's SIZE comes from the rest
  // placement, so animating or posing the scene never rescales the floor under it.
  const fitStageToScene = useCallback((runtime, fitted) => {
    const displayBounds = fitted.bounds;
    const modelOffset = modelTransformRef.current.offset;
    runtime.modelFloorZBase = Number(resolveRuntimeModelFloorZ(displayBounds, modelOffset, normalizedSceneScaleMode));
    runtime.modelFloorZBelowModel = Number(resolveRuntimeModelFloorZ(displayBounds, modelOffset, normalizedSceneScaleMode, { followModel: true }));
    const floorZ = floorFollowsModel ? runtime.modelFloorZBelowModel : runtime.modelFloorZBase;
    const { radius } = applyRuntimeModelBounds(THREE, runtime, displayBounds, normalizedSceneScaleMode, {
      shadowMapSize: renderShadowMapSizeRef.current
    });
    if (renderMode) applyActivePhotographicStudio(runtime, displayBounds);
    else syncRuntimeScaledLightingAndShadow(THREE, runtime, normalizedThemeSettings.lighting, radius, displayBounds,
      normalizedSceneScaleMode, renderShadowMapSizeRef.current);
    const groundRadius = sceneRadiusForBounds(THREE, mergeBoundsList([fitted.restBounds || fitted.bounds]), normalizedSceneScaleMode);
    updateActiveGridHelper(runtime, viewerTheme, groundRadius, floorZ, normalizedSceneScaleMode, resolvedFloorMode);
    if (!renderMode) {
      updateSpotLightTarget(runtime);
      updateStageEffects(runtime, viewerTheme, normalizedThemeSettings, groundRadius, runtime.gridFloorZ ?? 0, resolvedFloorMode, normalizedSceneScaleMode);
    }
    return radius;
  }, [applyActivePhotographicStudio, floorFollowsModel, normalizedSceneScaleMode, normalizedThemeSettings, renderMode,
    resolvedFloorMode, updateActiveGridHelper, viewerTheme]);
  const fitStageToSceneRef = useRef(fitStageToScene);
  fitStageToSceneRef.current = fitStageToScene;

  // Scene adoption: place the scene under the model group, fit lighting, floor and
  // depth to where it is now, and frame the camera on its rest placement.
  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) return;
    const { modelGroup, controls } = runtime;
    if (isLoading || !scene) {
      cancelCameraTransition(runtime);
      runtime.zeroPoseBounds = null;
      detachScene(runtime);
      runtime.requestRender();
      if (isLoading) setError("");
      return;
    }
    if (runtime.kitScene !== scene) {
      detachScene(runtime);
      modelGroup.add(scene.object3D);
      runtime.kitScene = scene;
    }
    runtime.hasVisibleModel = true;
    runtime.activeModelKey = modelKey || "";
    // TWO boxes: `bounds` is the scene as posed now, which lighting, shadows and the
    // floor follow; the camera is grounded on the rest placement, so a playing
    // routine never re-frames the model and 100% keeps meaning "framed at rest".
    const framingBounds = mergeBoundsList([scene.restBounds || scene.bounds]);
    runtime.zeroPoseBounds = framingBounds;
    const framingRadius = boundsModelRadius(THREE, framingBounds, normalizedSceneScaleMode);
    const modelOffset = modelTransformRef.current.offset;
    const radius = fitStageToSceneRef.current(runtime, scene);
    modelGroup.position.copy(modelOffset);
    modelGroup.updateMatrixWorld(true);
    syncRuntimeCameraClipPlanes(runtime, Math.max(radius / 1200, 0.01), Math.max(radius * 600, 2000));
    controls.minDistance = Math.max(radius / 2200, 0.02);
    controls.maxDistance = Math.max(radius * 140, 50);
    controls.zoomSpeed = DEFAULT_ZOOM_SPEED;

    const viewingMode = renderMode ? VIEWING_MODE.RENDER : VIEWING_MODE.INSPECT;
    const reframe = reframeReason({
      modelKey, framedModelKey: framedModelKeyRef.current, framedCompleteModelKey: framedModelKeyRef.current,
      mode: viewingMode, framedMode: framedViewingModeRef.current, modelComplete: true,
      zeroPoseBounds: framingBounds, framedZeroPoseBounds: framedBoundsRef.current, userMovedCamera: runtime.userMovedCamera
    });
    if (reframe) {
      if (reframe === "model") runtime.userMovedCamera = false;
      const nextPerspective = resolvePerspectiveSnapshot(perspectiveRef ? perspectiveRef.current : undefined, perspective);
      const storedMatches = perspectiveSnapshotMatchesScene(nextPerspective, {
        modelKey, sceneScaleMode: normalizedSceneScaleMode, coordinateSystem: STORED_CAMERA_COORDINATES,
        requireModelKey: true, requireSceneScaleMode: true, requireCoordinateSystem: true
      });
      runWithoutPerspectiveEvents(() => {
        const restored = !previewModeRef.current && (reframe === "model" || reframe === "mode") && storedMatches
          && applyPerspectiveSnapshot(runtime, nextPerspective, { scheduleIdle: false });
        // Only a camera the viewer chose is the viewer's to re-fit when the viewport changes.
        if (restored) runtime.openFitPending = false; else armOpenFit(runtime);
        if (restored) {
          runtime.interactiveFraming = { bounds: framingBounds,
            minRadius: getSceneScaleSettings(normalizedSceneScaleMode).minModelRadius,
            nearClip: Math.max(framingRadius / 1200, 0.01),
            direction: runtime.camera.position.clone().sub(controls.target).normalize().toArray(),
            up: runtime.camera.up.toArray() };
        } else {
          cancelCameraTransition(runtime);
          // Fit with the destination lens, so the first Render entry frames like later ones.
          const fitFocalLength = explicitViewerFocalLength(focalLength);
          if (fitFocalLength != null) setRuntimePerspectiveFocalLength(runtime, fitFocalLength);
          // A file opened into a locked plan view fits FROM the lock: coming up at the
          // default three-quarter angle and then being unable to turn out of it reads as broken.
          if (planMode && PLAN_VIEW_BASIS) {
            activeViewPlaneFaceRef.current = PLAN_VIEW_FACE;
            setActiveViewPlaneFace(PLAN_VIEW_FACE);
          }
          zoomRuntimeToBounds(runtime, framingBounds, normalizedSceneScaleMode, {
            animate: false, modelOffset,
            viewDirection: planMode && PLAN_VIEW_BASIS ? PLAN_VIEW_BASIS.direction : DEFAULT_VIEW_DIRECTION,
            viewUp: planMode && PLAN_VIEW_BASIS ? PLAN_VIEW_BASIS.up : WORLD_UP
          });
          runtime.requestRender();
        }
      });
      captureRuntimeViewportFitScale(runtime);
      resetRuntimeZoomBaseline(runtime);
      syncCameraZoomPercent(runtime);
      framedModelKeyRef.current = modelKey || "";
      framedViewingModeRef.current = viewingMode;
      framedBoundsRef.current = framingBounds;
      lastEmittedPerspectiveRef.current = readScopedPerspectiveSnapshot(runtime, { modelKey, sceneScaleMode: normalizedSceneScaleMode });
    }
    // A replaced runtime (context recovery) restores framing independently of what drew last.
    if (runtime.previousViewState) {
      if (runtime.previousViewState.modelKey === modelKey) {
        Object.assign(runtime, runtime.previousViewState.framing);
        syncCameraZoomPercent(runtime);
      }
      runtime.previousViewState = null;
    }
    setError("");
    runtime.requestRender();
    // Also handles opening fullscreen before the first scene arrives.
    syncFullscreenCamera(runtime);
    markPresentationReady(runtime);
  }, [
    scene, sceneRevision, markPresentationReady, modelKey, perspective, perspectiveRef, isLoading, viewerReadyTick,
    normalizedSceneScaleMode, resolvedFloorMode, renderMode, floorFollowsModel, viewerTheme, syncCameraZoomPercent,
    applyActivePhotographicStudio, detachScene, planMode
  ]);

  // A queued view update is acknowledged once the viewport holds (and, when the
  // change is expensive, has compiled) the frame that shows it.
  useEffect(() => {
    if (!viewUpdate?.revision) return undefined;
    const { revision, expensive, binding } = viewUpdate;
    const runtime = runtimeRef.current;
    let cancelled = false;
    const complete = (updateError) => {
      if (cancelled) return;
      const acknowledged = binding.complete(revision, updateError);
      if (!acknowledged && !updateError) runtime?.viewUpdateGate?.present().catch(() => {});
    };
    if (!runtime) { complete(); return undefined; }
    runtime.viewUpdateGate ??= createViewUpdateGate(runtime);
    runtime.viewUpdateGate.hold();
    (expensive ? runtime.viewUpdateGate.compile() : Promise.resolve()).then(() => complete(), complete);
    return () => { cancelled = true; };
  }, [viewUpdate?.revision, viewUpdate?.binding, viewerReadyTick]);

  const viewportContext = useMemo(() => ({ runtimeRef, hostRef: interactionHostRef, viewerReadyTick }), [viewerReadyTick]);
  const preparingFrame = Boolean(resolvedPresentationKey) &&
    (presentedEpoch !== presentationEpoch || presentedKey !== resolvedPresentationKey) && !error;
  const coveringModeTransition = presentedEpoch !== presentationEpoch && !error && hasViewportContent;
  useEffect(() => {
    onPresentationChange?.({
      file: modelKey, renderMode, key: resolvedPresentationKey,
      preparing: Boolean(preparingFrame), covering: Boolean(coveringModeTransition)
    });
  }, [modelKey, renderMode, resolvedPresentationKey, preparingFrame, coveringModeTransition, onPresentationChange]);
  const transitionBackdrop = viewerTransitionBackdrop({
    renderMode, renderConfiguration, background: normalizedThemeSettings.background, viewerTheme
  });

  return (
    <div
      ref={interactionHostRef}
      className="relative h-full w-full"
      style={coveringModeTransition ? { backgroundColor: transitionBackdrop.backgroundColor } : undefined}
      aria-busy={preparingFrame}
    >
      <div className="h-full w-full" ref={mountRef} />
      {coveringModeTransition ? (
        <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center" style={transitionBackdrop} role="status" data-viewer-transition={renderMode ? "render" : "inspect"}>
          <LoadingIndicator
            progress={loadingPresentation?.busy ? loadingPresentation.progress : { label: "Preparing view" }}
            operationKey={`${resolvedPresentationKey}:${renderMode}`}
          />
        </div>
      ) : null}
      {drawingOverlayActive ? <DrawingOverlay drawing={drawing} onReady={handleDrawingReady} onContentChange={handleDrawingContent} onViewportChange={followDrawingViewport} /> : null}
      {typeof children === "function" ? children(viewportContext) : children}
      {/* A locked view stops advertising the axes it cannot turn towards. */}
      <ViewPlaneControl
        showViewPlane={!previewMode && !drawingOverlayActive && !planMode}
        previewMode={previewMode}
        isLoading={isLoading}
        meshData={scene}
        viewPlaneOffsetRight={16}
        viewPlaneOffsetBottom="1rem"
        viewPlaneSize={VIEW_PLANE_CONTROL_SIZE}
        viewPlaneHeader={null}
        compact={false}
        activeViewPlaneFace={activeViewPlaneFace}
        viewPlaneFaces={VIEW_PLANE_FACES}
        viewPlaneOrientation={viewPlaneOrientation}
        viewerTheme={viewerTheme}
        activateViewPlaneFace={activateViewPlaneFace}
        activateDefaultViewPlane={activateDefaultViewPlane}
      />
      {error ? (
        <p className="bg-popover pointer-events-none absolute left-4 top-24 z-20 rounded-lg border border-error-border px-4 py-3 text-sm text-error shadow-sm sm:top-20">
          {error}
        </p>
      ) : null}
    </div>
  );
});

export default ShellViewport;
