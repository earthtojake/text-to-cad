import { useEffect } from "react";
import { isEditableTarget } from "../../../lib/dom";

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
  floorMode
}) {
  // Runtime setup/teardown should run once on mount, matching the previous CadViewer behavior.
  useEffect(() => {
    let cancelled = false;
    let cleanup = () => {};

    async function initializeViewer() {
      const [
        THREE,
        { TrackballControls },
        { LineSegments2 },
        { LineSegmentsGeometry },
        { LineMaterial }
      ] = await Promise.all([
        import("three"),
        import("three/examples/jsm/controls/TrackballControls.js"),
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

      const camera = new THREE.PerspectiveCamera(48, width / height, 0.1, 50000);
      camera.up.set(0, 0, 1);
      camera.position.set(180, 120, 180);

      const renderer = new THREE.WebGLRenderer({
        antialias: true,
        powerPreference: "high-performance",
        alpha: true,
        preserveDrawingBuffer: false,
        logarithmicDepthBuffer: true
      });
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = getViewerThemeValue(viewerTheme, "toneMappingExposure", DEFAULT_LIGHTING.toneMappingExposure);
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      renderer.setPixelRatio(getPixelRatioCap(IDLE_PIXEL_RATIO_CAP));
      renderer.setSize(width, height);
      container.innerHTML = "";
      container.appendChild(renderer.domElement);

      const controls = new TrackballControls(camera, renderer.domElement);
      controls.staticMoving = false;
      controls.dynamicDampingFactor = DEFAULT_DAMPING_FACTOR;
      controls.rotateSpeed = 1;
      controls.panSpeed = 1.35;
      controls.zoomSpeed = getDefaultZoomSpeed();

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
      keyLight.position.set(240, 340, 150);
      keyLight.castShadow = true;
      keyLight.shadow.mapSize.set(2048, 2048);
      keyLight.shadow.bias = -0.00025;
      keyLight.shadow.normalBias = 0.012;
      scene.add(keyLight);
      const fillLight = new THREE.DirectionalLight(
        getViewerThemeValue(viewerTheme, "fillLightColor", DEFAULT_LIGHTING.fillLightColor),
        getViewerThemeValue(viewerTheme, "fillLightIntensity", DEFAULT_LIGHTING.fillLightIntensity)
      );
      fillLight.position.set(120, 80, -210);
      scene.add(fillLight);
      const rimLight = new THREE.DirectionalLight(
        getViewerThemeValue(viewerTheme, "rimLightColor", DEFAULT_LIGHTING.rimLightColor),
        getViewerThemeValue(viewerTheme, "rimLightIntensity", DEFAULT_LIGHTING.rimLightIntensity)
      );
      rimLight.position.set(-260, 180, 240);
      scene.add(rimLight);
      const spotLight = new THREE.SpotLight("#ffffff", 0, 0, Math.PI / 6);
      spotLight.position.set(160, 120, 100);
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

      const syncScreenSpaceLineMaterials = () => {
        const nextWidth = container.clientWidth || width || 1;
        const nextHeight = container.clientHeight || height || 1;
        for (const material of screenSpaceLineMaterials) {
          material?.resolution?.set?.(nextWidth, nextHeight);
        }
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
          return;
        }
        interactionState.renderQueued = true;
        rafId = window.requestAnimationFrame(renderFrame);
        if (runtimeRef.current) {
          runtimeRef.current.rafId = rafId;
        }
      };

      function renderFrame(timestamp) {
        interactionState.renderQueued = false;
        const cameraTransitionActive = stepCameraTransition(runtimeRef.current, timestamp);
        const keyboardOrbitMoved = stepKeyboardOrbit(runtimeRef.current, timestamp);
        const needsMoreFrames = controls.update();
        if (cameraTransitionActive || keyboardOrbitMoved) {
          emitPerspectiveChange(runtimeRef.current);
        }
        const previewOrbitActive = !!runtimeRef.current?.previewOrbitEnabled;
        renderer.render(scene, camera);
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
        applyRenderQuality(INTERACTION_PIXEL_RATIO_CAP);
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
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        controls.handleResize?.();
        applyCameraFrameInsets?.(runtimeRef.current, frameInsetsRef?.current, { updateProjection: false });
        syncScreenSpaceLineMaterials();
        syncDrawingCanvasSize(runtimeRef.current);
        renderDrawingOverlay();
        requestRender();
      };
      window.addEventListener("resize", onResize);
      const resizeObserver = typeof ResizeObserver === "function"
        ? new ResizeObserver(() => {
          onResize();
        })
        : null;
      resizeObserver?.observe(container);

      const handleControlsStart = () => {
        cancelCameraTransition(runtimeRef.current);
        beginInteraction();
      };
      const handleControlsChange = () => {
        emitPerspectiveChange(runtimeRef.current);
        requestRender();
      };
      const handleControlsEnd = () => {
        scheduleIdleQuality();
      };
      const handleWheel = (event) => {
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
        renderer,
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
        interactionState,
        keyboardOrbitState,
        onResize,
        resizeObserver,
        rafId,
        requestRender,
        beginInteraction,
        scheduleIdleQuality,
        registerScreenSpaceLineMaterial,
        unregisterScreenSpaceLineMaterial
      };
      syncDrawingCanvasSize(runtimeRef.current);
      renderDrawingOverlay();
      applySceneBackground(runtimeRef.current, viewerTheme);
      applyCameraFrameInsets?.(runtimeRef.current, frameInsetsRef?.current);
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
        cancelCameraTransition(runtime, { scheduleIdle: false });
        window.cancelAnimationFrame(runtime.rafId);
        window.removeEventListener("resize", runtime.onResize);
        runtime.resizeObserver?.disconnect();
        runtime.controls.removeEventListener("start", handleControlsStart);
        runtime.controls.removeEventListener("change", handleControlsChange);
        runtime.controls.removeEventListener("end", handleControlsEnd);
        runtime.renderer.domElement.removeEventListener("wheel", handleWheel, wheelListenerOptions);
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
        setError(err instanceof Error ? err.message : String(err));
      }
    });

    return () => {
      cancelled = true;
      cleanup();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
