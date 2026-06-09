import { useEffect } from "react";
import { isEditableTarget } from "../../../ui/dom";
import {
  isWebGlContextCreationError,
  runtimeErrorMessage
} from "cadjs/lib/viewer/webglSupport";
import {
  createCadWebGlRenderer
} from "cadjs/common/webglRenderer";
import {
  resolveInteractionPixelRatioCap
} from "cadjs/lib/viewer/renderQuality";

function createWebGlRenderer(THREE) {
  return createCadWebGlRenderer(THREE, {
    allowFallback: true,
    isRecoverableError: isWebGlContextCreationError
  });
}

export function useViewerRuntime({
  mountRef,
  runtimeRef,
  previewModeRef,
  setError,
  setViewerReadyTick,
  viewerTheme,
  syncDrawingCanvasSize,
  renderDrawingOverlay,
  emitPerspectiveChange,
  setActiveViewPlaneFace,
  activeViewPlaneFaceRef,
  stepCameraTransition,
  stepKeyboardOrbit,
  getActiveViewPlaneFaceId,
  cancelCameraTransition,
  clearKeyboardOrbitState,
  isTrackpadLikeWheelEvent,
  getKeyboardOrbitCommand,
  getKeyboardOrbitAxes,
  applyOrbitDelta,
  getViewerThemeValue,
  getPixelRatioCap,
  applySceneBackground,
  applyCameraFrameInsets,
  frameInsetsRef,
  applyInitialPerspective,
  updateGridHelper,
  clearSceneGroup,
  disposeSceneObject,
  disposeTexture,
  syncViewPlaneOrientation,
  BASE_VIEWER_THEME,
  DEFAULT_LIGHTING,
  DEFAULT_DAMPING_FACTOR,
  DEFAULT_ZOOM_SPEED,
  COARSE_POINTER_ZOOM_SPEED,
  INTERACTION_PIXEL_RATIO_CAP,
  IDLE_PIXEL_RATIO_CAP,
  INTERACTION_IDLE_DELAY_MS,
  TRACKPAD_PINCH_ZOOM_SPEED,
  COARSE_POINTER_PINCH_ZOOM_SPEED,
  ACCELERATED_WHEEL_ZOOM_SPEED,
  KEYBOARD_ORBIT_NUDGE_RAD,
  defaultGridRadius,
  sceneScaleMode,
  floorMode,
  onManualCameraInteraction,
  onViewportResize,
  onContextLost,
  onContextRestored,
  onInitializationError,
  preserveInteractionPixelRatio = false,
  runtimeResetToken = 0
}) {
  useEffect(() => {
    if (runtimeRef.current) {
      runtimeRef.current.preserveInteractionPixelRatio = preserveInteractionPixelRatio === true;
    }
  }, [preserveInteractionPixelRatio, runtimeRef, runtimeResetToken]);

  // Runtime setup/teardown should run once per WebGL runtime epoch.
  useEffect(() => {
    let cancelled = false;
    let cleanup = () => {};

    async function initializeViewer() {
      const [
        THREE,
        { OrbitControls },
        { Line2 },
        { LineGeometry },
        { LineSegments2 },
        { LineSegmentsGeometry },
        { LineMaterial }
      ] = await Promise.all([
        import("three"),
        import("three/examples/jsm/controls/OrbitControls.js"),
        import("three/examples/jsm/lines/Line2.js"),
        import("three/examples/jsm/lines/LineGeometry.js"),
        import("three/examples/jsm/lines/LineSegments2.js"),
        import("three/examples/jsm/lines/LineSegmentsGeometry.js"),
        import("three/examples/jsm/lines/LineMaterial.js")
      ]);
      if (cancelled || !mountRef.current) {
        return;
      }

      const container = mountRef.current;
      const coarsePointerQuery = typeof window.matchMedia === "function"
        ? window.matchMedia("(pointer: coarse)")
        : null;
      const prefersCoarsePointer = coarsePointerQuery?.matches ?? false;
      const getOrbitControlsPixelRatioBucket = () => Math.max((window.devicePixelRatio || 1) | 0, 1);
      const initialWheelPixelRatioBucket = getOrbitControlsPixelRatioBucket();
      const getDefaultZoomSpeed = () => (prefersCoarsePointer ? COARSE_POINTER_ZOOM_SPEED : DEFAULT_ZOOM_SPEED);
      const getPinchZoomSpeed = () => (prefersCoarsePointer ? COARSE_POINTER_PINCH_ZOOM_SPEED : TRACKPAD_PINCH_ZOOM_SPEED);
      const getWheelZoomSpeed = (baseZoomSpeed) => {
        // OrbitControls divides wheel deltas by a floored devicePixelRatio internally.
        // Browser zoom changes that bucket, so scale our speed back to the initial bucket.
        return baseZoomSpeed * (getOrbitControlsPixelRatioBucket() / initialWheelPixelRatioBucket);
      };
      const width = container.clientWidth || 800;
      const height = container.clientHeight || 640;

      const scene = new THREE.Scene();

      const syncCameraViewport = (targetCamera, nextWidth = width, nextHeight = height) => {
        if (!targetCamera) {
          return;
        }
        const aspect = Math.max(nextWidth, 1) / Math.max(nextHeight, 1);
        if (targetCamera.isPerspectiveCamera) {
          targetCamera.aspect = aspect;
        } else if (targetCamera.isOrthographicCamera) {
          const halfHeight = Math.max(Number(targetCamera.userData?.cadHalfHeight) || 120, 1e-3);
          targetCamera.left = -halfHeight * aspect;
          targetCamera.right = halfHeight * aspect;
          targetCamera.top = halfHeight;
          targetCamera.bottom = -halfHeight;
        }
        targetCamera.updateProjectionMatrix?.();
      };

      const perspectiveCamera = new THREE.PerspectiveCamera(48, width / height, 0.1, 50000);
      const orthographicCamera = new THREE.OrthographicCamera(-120, 120, 120, -120, 0.1, 50000);
      orthographicCamera.userData.cadHalfHeight = 120;
      const camera = perspectiveCamera;
      camera.up.set(0, 0, 1);
      camera.position.set(180, -180, 120);
      orthographicCamera.up.copy(camera.up);
      orthographicCamera.position.copy(camera.position);
      syncCameraViewport(perspectiveCamera, width, height);
      syncCameraViewport(orthographicCamera, width, height);

      const renderer = createWebGlRenderer(THREE);
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = getViewerThemeValue(viewerTheme, "toneMappingExposure", DEFAULT_LIGHTING.toneMappingExposure);
      renderer.localClippingEnabled = true;
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      renderer.setPixelRatio(getPixelRatioCap(IDLE_PIXEL_RATIO_CAP));
      renderer.setSize(width, height);
      container.innerHTML = "";
      container.appendChild(renderer.domElement);

      const controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = DEFAULT_DAMPING_FACTOR;
      controls.rotateSpeed = 1;
      controls.panSpeed = 1.35;
      controls.zoomSpeed = getDefaultZoomSpeed();
      if ("zoomToCursor" in controls) {
        controls.zoomToCursor = true;
      }

      const hemisphereLight = new THREE.HemisphereLight(
        getViewerThemeValue(viewerTheme, "hemisphereSky", DEFAULT_LIGHTING.hemisphereSky),
        getViewerThemeValue(viewerTheme, "hemisphereGround", DEFAULT_LIGHTING.hemisphereGround),
        getViewerThemeValue(viewerTheme, "hemisphereIntensity", DEFAULT_LIGHTING.hemisphereIntensity)
      );
      scene.add(hemisphereLight);
      const ambientLight = new THREE.AmbientLight("#ffffff", 0);
      scene.add(ambientLight);
      const keyLight = new THREE.DirectionalLight(
        getViewerThemeValue(viewerTheme, "keyLightColor", DEFAULT_LIGHTING.keyLightColor),
        getViewerThemeValue(viewerTheme, "keyLightIntensity", DEFAULT_LIGHTING.keyLightIntensity)
      );
      keyLight.position.set(240, -150, 340);
      keyLight.castShadow = true;
      keyLight.shadow.mapSize.set(2048, 2048);
      keyLight.shadow.bias = -0.00025;
      keyLight.shadow.normalBias = 0.024;
      scene.add(keyLight);
      const fillLight = new THREE.DirectionalLight(
        getViewerThemeValue(viewerTheme, "fillLightColor", DEFAULT_LIGHTING.fillLightColor),
        getViewerThemeValue(viewerTheme, "fillLightIntensity", DEFAULT_LIGHTING.fillLightIntensity)
      );
      fillLight.position.set(120, 80, 210);
      scene.add(fillLight);
      const rimLight = new THREE.DirectionalLight(
        getViewerThemeValue(viewerTheme, "rimLightColor", DEFAULT_LIGHTING.rimLightColor),
        getViewerThemeValue(viewerTheme, "rimLightIntensity", DEFAULT_LIGHTING.rimLightIntensity)
      );
      rimLight.position.set(-260, 240, 180);
      scene.add(rimLight);
      const spotLight = new THREE.SpotLight("#ffffff", 0, 0, Math.PI / 6);
      spotLight.position.set(160, -120, 140);
      spotLight.visible = false;
      spotLight.castShadow = false;
      spotLight.shadow.mapSize.set(1024, 1024);
      spotLight.shadow.bias = -0.00025;
      spotLight.shadow.normalBias = 0.01;
      scene.add(spotLight);
      scene.add(spotLight.target);
      const pointLight = new THREE.PointLight("#ffffff", 0, 0);
      pointLight.position.set(-120, 80, 140);
      pointLight.visible = false;
      pointLight.castShadow = false;
      scene.add(pointLight);
      const axesHelper = null;

      const stageGroup = new THREE.Group();
      const modelGroup = new THREE.Group();
      const edgesGroup = new THREE.Group();
      const facePickGroup = new THREE.Group();
      const edgePickGroup = new THREE.Group();
      const vertexPickGroup = new THREE.Group();
      scene.add(stageGroup);
      scene.add(modelGroup);
      scene.add(edgesGroup);
      scene.add(facePickGroup);
      scene.add(edgePickGroup);
      scene.add(vertexPickGroup);

      const raycaster = new THREE.Raycaster();
      const pointer = new THREE.Vector2();
      const interactionState = {
        active: false,
        pixelRatioCap: IDLE_PIXEL_RATIO_CAP,
        pixelRatio: getPixelRatioCap(IDLE_PIXEL_RATIO_CAP),
        renderQueued: false,
        renderQueuedAt: 0,
        renderFallbackTimerId: 0,
        restoreTimerId: 0
      };
      const keyboardOrbitState = {
        pressedKeys: new Set(),
        directionCounts: {
          left: 0,
          right: 0,
          up: 0,
          down: 0
        },
        lastFrameTime: 0
      };
      const screenSpaceLineMaterials = new Set();

      const getScreenSpaceLineMaterialCount = () => (
        screenSpaceLineMaterials.size +
        Number(runtimeRef.current?.cadScene?.runtime?.screenSpaceLineMaterials?.size || 0)
      );

      const syncScreenSpaceLineMaterials = () => {
        const nextWidth = container.clientWidth || width || 1;
        const nextHeight = container.clientHeight || height || 1;
        for (const material of screenSpaceLineMaterials) {
          material?.resolution?.set?.(nextWidth, nextHeight);
        }
        runtimeRef.current?.cadScene?.runtime?.syncScreenSpaceLineMaterials?.(nextWidth, nextHeight);
      };

      const registerScreenSpaceLineMaterial = (material) => {
        if (!material?.resolution?.set) {
          return;
        }
        screenSpaceLineMaterials.add(material);
        material.resolution.set(container.clientWidth || width || 1, container.clientHeight || height || 1);
      };

      const unregisterScreenSpaceLineMaterial = (material) => {
        if (!material) {
          return;
        }
        screenSpaceLineMaterials.delete(material);
      };
      const handleContextLost = (event) => {
        event.preventDefault();
        clearKeyboardOrbitState(keyboardOrbitState);
        setError("WebGL context was lost. Restoring CAD Viewer...");
        onContextLost?.();
      };
      const handleContextRestored = () => {
        setError("");
        onContextRestored?.();
      };

      const applyRenderQuality = (pixelRatioCap) => {
        const nextPixelRatio = getPixelRatioCap(pixelRatioCap);
        if (
          Math.abs(interactionState.pixelRatioCap - pixelRatioCap) < 1e-4 &&
          Math.abs((interactionState.pixelRatio || 0) - nextPixelRatio) < 1e-4
        ) {
          return;
        }
        interactionState.pixelRatioCap = pixelRatioCap;
        interactionState.pixelRatio = nextPixelRatio;
        renderer.setPixelRatio(nextPixelRatio);
        renderer.setSize(container.clientWidth || width, container.clientHeight || height, false);
        syncScreenSpaceLineMaterials();
        syncDrawingCanvasSize(runtimeRef.current);
        renderDrawingOverlay();
      };

      let rafId = 0;
      const requestRender = () => {
        if (interactionState.renderQueued) {
          const now = typeof performance !== "undefined" && typeof performance.now === "function"
            ? performance.now()
            : Date.now();
          if (interactionState.renderQueuedAt && now - interactionState.renderQueuedAt < 120) {
            return;
          }
          window.cancelAnimationFrame(rafId);
          interactionState.renderQueued = false;
          interactionState.renderQueuedAt = 0;
        }
        interactionState.renderQueued = true;
        interactionState.renderQueuedAt = typeof performance !== "undefined" && typeof performance.now === "function"
          ? performance.now()
          : Date.now();
        rafId = window.requestAnimationFrame(renderFrame);
        if (interactionState.renderFallbackTimerId) {
          window.clearTimeout(interactionState.renderFallbackTimerId);
        }
        interactionState.renderFallbackTimerId = window.setTimeout(() => {
          if (!interactionState.renderQueued) {
            return;
          }
          window.cancelAnimationFrame(rafId);
          renderFrame(
            typeof performance !== "undefined" && typeof performance.now === "function"
              ? performance.now()
              : Date.now()
          );
        }, 120);
        if (runtimeRef.current) {
          runtimeRef.current.rafId = rafId;
        }
      };

      function renderFrame(timestamp) {
        interactionState.renderQueued = false;
        interactionState.renderQueuedAt = 0;
        if (interactionState.renderFallbackTimerId) {
          window.clearTimeout(interactionState.renderFallbackTimerId);
          interactionState.renderFallbackTimerId = 0;
        }
        const cameraTransitionActive = stepCameraTransition(runtimeRef.current, timestamp);
        const keyboardOrbitMoved = stepKeyboardOrbit(runtimeRef.current, timestamp);
        const needsMoreFrames = controls.update();
        if (cameraTransitionActive || keyboardOrbitMoved) {
          emitPerspectiveChange(runtimeRef.current);
        }
        const previewOrbitActive = !!runtimeRef.current?.previewOrbitEnabled;
        renderer.render(scene, runtimeRef.current?.camera || camera);
        const nextActiveFace = getActiveViewPlaneFaceId(runtimeRef.current);
        if (nextActiveFace !== activeViewPlaneFaceRef.current) {
          activeViewPlaneFaceRef.current = nextActiveFace;
          setActiveViewPlaneFace(nextActiveFace);
        }
        syncViewPlaneOrientation(runtimeRef.current);
        if (
          cameraTransitionActive ||
          keyboardOrbitMoved ||
          needsMoreFrames ||
          interactionState.active ||
          previewOrbitActive
        ) {
          requestRender();
        }
      }

      const beginInteraction = () => {
        if (interactionState.restoreTimerId) {
          window.clearTimeout(interactionState.restoreTimerId);
          interactionState.restoreTimerId = 0;
        }
        interactionState.active = true;
        applyRenderQuality(resolveInteractionPixelRatioCap({
          idlePixelRatioCap: IDLE_PIXEL_RATIO_CAP,
          interactionPixelRatioCap: INTERACTION_PIXEL_RATIO_CAP,
          preservePixelRatio: runtimeRef.current?.preserveInteractionPixelRatio === true,
          screenSpaceLineMaterialCount: getScreenSpaceLineMaterialCount()
        }));
        requestRender();
      };

      const scheduleIdleQuality = () => {
        if (interactionState.restoreTimerId) {
          window.clearTimeout(interactionState.restoreTimerId);
        }
        interactionState.restoreTimerId = window.setTimeout(() => {
          interactionState.restoreTimerId = 0;
          interactionState.active = false;
          controls.enableDamping = true;
          controls.dampingFactor = DEFAULT_DAMPING_FACTOR;
          controls.zoomSpeed = getDefaultZoomSpeed();
          applyRenderQuality(IDLE_PIXEL_RATIO_CAP);
          requestRender();
        }, INTERACTION_IDLE_DELAY_MS);
      };

      const onResize = () => {
        const w = container.clientWidth || 800;
        const h = container.clientHeight || 640;
        applyRenderQuality(interactionState.pixelRatioCap);
        renderer.setSize(w, h);
        syncCameraViewport(perspectiveCamera, w, h);
        syncCameraViewport(orthographicCamera, w, h);
        applyCameraFrameInsets?.(runtimeRef.current, frameInsetsRef?.current, { updateProjection: false });
        syncScreenSpaceLineMaterials();
        syncDrawingCanvasSize(runtimeRef.current);
        renderDrawingOverlay();
        runtimeRef.current?.onViewportResize?.();
        requestRender();
      };
      window.addEventListener("resize", onResize);
      const resizeObserver = typeof ResizeObserver === "function"
        ? new ResizeObserver(() => {
          onResize();
        })
        : null;
      resizeObserver?.observe(container);

      let controlsStartDistance = null;
      const readControlsDistance = () => {
        const activeRuntime = runtimeRef.current;
        if (!activeRuntime?.camera || !activeRuntime?.controls?.target) {
          return null;
        }
        return activeRuntime.camera.position.distanceTo(activeRuntime.controls.target);
      };
      const handleControlsStart = () => {
        controlsStartDistance = readControlsDistance();
        cancelCameraTransition(runtimeRef.current);
        beginInteraction();
      };
      const handleControlsChange = () => {
        emitPerspectiveChange(runtimeRef.current);
        requestRender();
      };
      const handleControlsEnd = () => {
        const controlsEndDistance = readControlsDistance();
        if (Number.isFinite(controlsStartDistance) && Number.isFinite(controlsEndDistance)) {
          const threshold = Math.max(Math.abs(controlsStartDistance) * 0.002, 1e-4);
          if (Math.abs(controlsEndDistance - controlsStartDistance) > threshold) {
            runtimeRef.current?.onManualCameraInteraction?.("zoom");
          }
        }
        controlsStartDistance = null;
        scheduleIdleQuality();
      };
      const handleWheel = (event) => {
        runtimeRef.current?.onManualCameraInteraction?.("wheel");
        cancelCameraTransition(runtimeRef.current);
        controls.enableDamping = false;
        controls.zoomSpeed = getWheelZoomSpeed(isTrackpadLikeWheelEvent(event)
          ? getPinchZoomSpeed()
          : ACCELERATED_WHEEL_ZOOM_SPEED);
        beginInteraction();
      };
      const wheelListenerOptions = { passive: true, capture: true };

      controls.addEventListener("start", handleControlsStart);
      controls.addEventListener("change", handleControlsChange);
      controls.addEventListener("end", handleControlsEnd);
      renderer.domElement.addEventListener("wheel", handleWheel, wheelListenerOptions);
      renderer.domElement.addEventListener("webglcontextlost", handleContextLost, false);
      renderer.domElement.addEventListener("webglcontextrestored", handleContextRestored, false);

      const handleKeyDown = (event) => {
        if (
          previewModeRef.current ||
          event.defaultPrevented ||
          event.ctrlKey ||
          event.metaKey ||
          event.altKey ||
          isEditableTarget(event.target)
        ) {
          return;
        }

        const command = getKeyboardOrbitCommand(event);
        if (!command) {
          return;
        }
        if (keyboardOrbitState.pressedKeys.has(command.keyId)) {
          event.preventDefault();
          return;
        }

        keyboardOrbitState.pressedKeys.add(command.keyId);
        keyboardOrbitState.directionCounts[command.direction] += 1;
        keyboardOrbitState.lastFrameTime = 0;
        cancelCameraTransition(runtimeRef.current);
        beginInteraction();
        applyOrbitDelta(
          runtimeRef.current,
          (command.direction === "right" ? 1 : command.direction === "left" ? -1 : 0) * KEYBOARD_ORBIT_NUDGE_RAD,
          (command.direction === "down" ? 1 : command.direction === "up" ? -1 : 0) * KEYBOARD_ORBIT_NUDGE_RAD
        );
        emitPerspectiveChange(runtimeRef.current);
        requestRender();
        event.preventDefault();
      };

      const handleKeyUp = (event) => {
        const command = getKeyboardOrbitCommand(event);
        if (!command) {
          return;
        }
        if (!keyboardOrbitState.pressedKeys.delete(command.keyId)) {
          return;
        }

        keyboardOrbitState.directionCounts[command.direction] = Math.max(
          0,
          keyboardOrbitState.directionCounts[command.direction] - 1
        );
        const axes = getKeyboardOrbitAxes(keyboardOrbitState);
        if (!axes.azimuth && !axes.polar) {
          keyboardOrbitState.lastFrameTime = 0;
          scheduleIdleQuality();
        }
        event.preventDefault();
      };

      const clearKeyboardOrbit = () => {
        if (!keyboardOrbitState.pressedKeys.size) {
          return;
        }
        clearKeyboardOrbitState(keyboardOrbitState);
        scheduleIdleQuality();
      };

      const handleVisibilityChange = () => {
        if (document.visibilityState !== "visible") {
          clearKeyboardOrbit();
        }
      };

      runtimeRef.current = {
        THREE,
        scene,
        camera,
        perspectiveCamera,
        orthographicCamera,
        projection: "perspective",
        syncCameraViewport,
        renderer,
        Line2,
        LineGeometry,
        LineSegments2,
        LineSegmentsGeometry,
        LineMaterial,
        controls,
        stageGroup,
        modelGroup,
        edgesGroup,
        facePickGroup,
        edgePickGroup,
        vertexPickGroup,
        facePickMesh: null,
        edgePickLines: null,
        vertexPickPoints: null,
        edgePickObjects: [],
        displayRecords: [],
        modelBounds: null,
        modelRadius: 1,
        activeModelKey: "",
        sceneScaleMode,
        raycaster,
        pointer,
        hemisphereLight,
        ambientLight,
        keyLight,
        fillLight,
        rimLight,
        spotLight,
        pointLight,
        axesHelper,
        sceneBackgroundTexture: null,
        environmentTexture: null,
        environmentTextureUrl: "",
        gridConfig: null,
        gridHelper: null,
        floorMode,
        hasVisibleModel: false,
        edgePickThreshold: 1.5,
        vertexPickThreshold: 0.9,
        cameraTransition: null,
        previewOrbitEnabled: false,
        preserveInteractionPixelRatio: preserveInteractionPixelRatio === true,
        interactionState,
        keyboardOrbitState,
        onResize,
        resizeObserver,
        rafId,
        requestRender,
        beginInteraction,
        scheduleIdleQuality,
        applyCameraFrameInsets,
        frameInsetsRef,
        onManualCameraInteraction,
        onViewportResize,
        registerScreenSpaceLineMaterial,
        unregisterScreenSpaceLineMaterial
      };
      syncDrawingCanvasSize(runtimeRef.current);
      renderDrawingOverlay();
      applySceneBackground(runtimeRef.current, viewerTheme);
      applyCameraFrameInsets?.(runtimeRef.current, frameInsetsRef?.current);
      applyInitialPerspective?.(runtimeRef.current);
      window.addEventListener("keydown", handleKeyDown);
      window.addEventListener("keyup", handleKeyUp);
      window.addEventListener("blur", clearKeyboardOrbit);
      document.addEventListener("visibilitychange", handleVisibilityChange);
      requestRender();
      updateGridHelper(runtimeRef.current, viewerTheme, defaultGridRadius, 0, sceneScaleMode, floorMode);
      setViewerReadyTick((value) => value + 1);

      cleanup = () => {
        const runtime = runtimeRef.current;
        if (!runtime) {
          return;
        }
        if (runtime.interactionState.restoreTimerId) {
          window.clearTimeout(runtime.interactionState.restoreTimerId);
        }
        if (runtime.interactionState.renderFallbackTimerId) {
          window.clearTimeout(runtime.interactionState.renderFallbackTimerId);
        }
        cancelCameraTransition(runtime, { scheduleIdle: false });
        window.cancelAnimationFrame(runtime.rafId);
        window.removeEventListener("resize", runtime.onResize);
        runtime.resizeObserver?.disconnect();
        runtime.controls.removeEventListener("start", handleControlsStart);
        runtime.controls.removeEventListener("change", handleControlsChange);
        runtime.controls.removeEventListener("end", handleControlsEnd);
        runtime.renderer.domElement.removeEventListener("wheel", handleWheel, wheelListenerOptions);
        runtime.renderer.domElement.removeEventListener("webglcontextlost", handleContextLost, false);
        runtime.renderer.domElement.removeEventListener("webglcontextrestored", handleContextRestored, false);
        window.removeEventListener("keydown", handleKeyDown);
        window.removeEventListener("keyup", handleKeyUp);
        window.removeEventListener("blur", clearKeyboardOrbit);
        document.removeEventListener("visibilitychange", handleVisibilityChange);
        runtime.controls.dispose();
        clearSceneGroup(runtime.stageGroup);
        clearSceneGroup(runtime.modelGroup);
        clearSceneGroup(runtime.edgesGroup);
        clearSceneGroup(runtime.facePickGroup);
        clearSceneGroup(runtime.edgePickGroup);
        clearSceneGroup(runtime.vertexPickGroup);
        disposeSceneObject(runtime.gridHelper);
        disposeSceneObject(runtime.axesHelper);
        disposeTexture(runtime.sceneBackgroundTexture);
        disposeTexture(runtime.environmentTexture);
        runtime.renderer.dispose();
        if (container.contains(runtime.renderer.domElement)) {
          container.removeChild(runtime.renderer.domElement);
        }
        runtimeRef.current = null;
      };
    }

    initializeViewer().catch((err) => {
      if (!cancelled) {
        setError(runtimeErrorMessage(err));
        onInitializationError?.(err);
      }
    });

    return () => {
      cancelled = true;
      cleanup();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runtimeResetToken]);
}
