import { useEffect, useMemo, useRef } from "react";
import {
  createImplicitCadFullscreenScene,
  estimateImplicitCadFrameBoundsAsync,
  implicitCadModelShaderKey,
  refreshImplicitCadFloorBounds,
  setImplicitCadBackgroundPainting,
  updateImplicitCadThemeUniforms,
  updateImplicitCadGraphicsUniforms,
  updateImplicitCadMaterialUniforms,
  updateImplicitCadModelUniforms
} from "cadjs/implicit/render";
import {
  implicitGraphicsRenderResolutionScale,
  implicitGraphicsRenderSettings,
  normalizeImplicitGraphicsSettings
} from "@/workbench/implicitGraphicsSettings";
import { implicitBoundsKey, implicitModelBounds } from "../implicitFit.js";

// Hosts the implicit raymarch pass inside the SHARED viewer runtime instead of a
// second renderer. The pass is a fullscreen quad whose vertex shader already
// emits clip space, so it covers the viewport under any camera; the fragment
// shader builds its rays purely from camera uniforms. That means the shared
// OrbitControls, zoom defaults, fit/reset logic and view cube drive it with no
// per-format camera code — the whole point of making implicit a render type
// rather than a parallel viewer.
//
// The quad paints its own background and stage-floor shadow (deliberately
// matched to the mesh stage), so CadViewer suppresses the three.js stage while
// this pass is active rather than trying to blend the two.

// Interaction frames get a fixed pixel budget rather than a fixed pixel ratio, so
// gesture cost stops scaling with window size. Without this, the same 1.25 ratio
// that is comfortable in a 1440x900 pane is four times the work fullscreen on a
// retina display — the difference between smooth and unusable.
const INTERACTION_PIXEL_BUDGET = 2_500_000;
const MIN_INTERACTION_PIXEL_RATIO = 0.5;
// Long enough that discrete wheel ticks do not each pay a full-quality restore.
const IMPLICIT_IDLE_QUALITY_DELAY_MS = 400;

export function useImplicitRaymarch({
  runtimeRef,
  viewerReadyTick = 0,
  enabled = false,
  model = null,
  themeSettings = null,
  graphicsSettings = null,
  dynamicRenderActive = false,
  previewMode = false,
  onModelBounds,
  onShaderError
}) {
  const normalizedGraphicsSettings = useMemo(
    () => normalizeImplicitGraphicsSettings(graphicsSettings),
    [graphicsSettings]
  );
  const graphicsSettingsRef = useRef(normalizedGraphicsSettings);
  graphicsSettingsRef.current = normalizedGraphicsSettings;
  const dynamicRenderActiveRef = useRef(dynamicRenderActive === true);
  dynamicRenderActiveRef.current = dynamicRenderActive === true;
  const previewModeRef = useRef(previewMode === true);
  previewModeRef.current = previewMode === true;
  const themeSettingsRef = useRef(themeSettings);
  themeSettingsRef.current = themeSettings;
  const modelRef = useRef(model);
  modelRef.current = model;
  const modelBoundsRef = useRef(onModelBounds);
  modelBoundsRef.current = onModelBounds;
  const shaderErrorRef = useRef(onShaderError);
  shaderErrorRef.current = onShaderError;
  const passRef = useRef(null);

  // The reduced-quality tier (step budget 96, detail 0.75, no shadows/AO) used to
  // engage only for parameter drags and preview orbit. Plain camera interaction
  // dropped resolution but kept paying for shadows, AO and a 192-step march —
  // the single biggest cost during an orbit or pinch. Motion hides the
  // difference, and the idle restore repaints at full quality.
  const interactionQuality = (runtime) => (
    dynamicRenderActiveRef.current ||
    previewModeRef.current ||
    runtime?.interactionState?.active === true
  );

  // three's compileAsync polls `material.program.isReady()` from an internal timer.
  // Disposing the material while that poll is live makes the poll read `.isReady` off an
  // undefined program and throw — asynchronously, so it escapes the promise's own catch
  // and surfaces as an uncaught TypeError. Switching models faster than shaders link
  // (a corpus sweep, or a user scrubbing the file tree) hits it. So a pass with a compile
  // in flight is disposed only once that compile settles.
  const disposePass = (pass) => {
    if (!pass) {
      return;
    }
    pass.quad?.removeFromParent?.();
    if (pass.pendingCompile) {
      pass.pendingCompile.then(() => pass.dispose?.());
      return;
    }
    pass.dispose?.();
  };

  const applyUniforms = (runtime, activeModel, interaction) => {
    const material = passRef.current?.material;
    if (!material || !runtime?.THREE || !activeModel) {
      return;
    }
    const tier = interaction === undefined ? interactionQuality(runtime) : interaction;
    const tierSettings = implicitGraphicsRenderSettings(graphicsSettingsRef.current, {
      interaction: tier
    });
    updateImplicitCadThemeUniforms(runtime.THREE, material, activeModel, {
      themeSettings: themeSettingsRef.current,
      graphicsSettings: tierSettings
    });
    updateImplicitCadGraphicsUniforms(material, activeModel, tierSettings);
    if (passRef.current) {
      passRef.current.appliedTier = tier;
    }
  };

  // Tune the shared render loop for this render type's frame cost. Every hook
  // here is inert unless installed, so the mesh path keeps its current
  // behaviour exactly.
  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!runtime) {
      return undefined;
    }
    const release = (activeRuntime) => {
      if (!activeRuntime) {
        return;
      }
      activeRuntime.renderOnDemandOnly = false;
      activeRuntime.idleQualityDelayMs = 0;
      activeRuntime.onIdleQualityRestore = null;
      activeRuntime.resolveExtraPixelRatioCap = null;
      activeRuntime.refreshRenderQuality?.();
    };
    if (!enabled) {
      release(runtime);
      return undefined;
    }

    runtime.renderOnDemandOnly = true;
    runtime.idleQualityDelayMs = IMPLICIT_IDLE_QUALITY_DELAY_MS;
    runtime.onIdleQualityRestore = () => {
      applyUniforms(runtimeRef.current, modelRef.current, false);
    };
    runtime.resolveExtraPixelRatioCap = (interaction) => {
      const active = interaction === true || interactionQuality(runtimeRef.current);
      const scale = implicitGraphicsRenderResolutionScale(graphicsSettingsRef.current, {
        interaction: active
      });
      if (!active) {
        return scale;
      }
      const canvas = runtimeRef.current?.renderer?.domElement;
      const width = Math.max(canvas?.clientWidth || 0, 1);
      const height = Math.max(canvas?.clientHeight || 0, 1);
      const budgetRatio = Math.sqrt(INTERACTION_PIXEL_BUDGET / (width * height));
      return Math.min(scale, Math.max(budgetRatio, MIN_INTERACTION_PIXEL_RATIO));
    };
    runtime.refreshRenderQuality?.();
    return () => release(runtimeRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, normalizedGraphicsSettings, runtimeRef, viewerReadyTick]);

  // Dynamic render (slider drag, animation playback) swaps in the interaction
  // quality tier for as long as it is active.
  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!enabled || !runtime) {
      return;
    }
    runtime.refreshRenderQuality?.();
    applyUniforms(runtime, model);
    runtime.requestRender?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dynamicRenderActive, previewMode, enabled, viewerReadyTick]);

  // Build or update the pass. A model whose GLSL is unchanged (a parameter or
  // animation frame) only updates uniforms; rebuilding the material there would
  // recompile the shader every frame.
  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!enabled || !runtime?.THREE || !runtime?.scene || !model) {
      return;
    }

    const { THREE } = runtime;
    let nextShaderKey = "";
    try {
      nextShaderKey = implicitCadModelShaderKey(model);
    } catch (error) {
      shaderErrorRef.current?.(error instanceof Error ? error.message : String(error));
      return;
    }

    const existing = passRef.current;
    if (existing && existing.shaderKey === nextShaderKey) {
      updateImplicitCadModelUniforms(THREE, existing.material, model);
      applyUniforms(runtime, model);
      runtime.requestRender?.();
      return;
    }

    let nextPass = null;
    try {
      nextPass = createImplicitCadFullscreenScene(THREE, model);
    } catch (error) {
      shaderErrorRef.current?.(error instanceof Error ? error.message : String(error));
      return;
    }

    disposePass(existing);

    const { quad, material } = nextPass;
    quad.frustumCulled = false;
    // Composite over the shared scene rather than replacing it. The pass stops
    // painting its own background, so the themed background, grid and stage
    // floor every other format renders show through and the model blends on
    // top — which is what keeps an implicit looking like the rest of the viewer
    // instead of a separate world. It draws LAST and ignores depth: the shared
    // stage has no depth relationship with an SDF body.
    setImplicitCadBackgroundPainting(material, false);
    material.transparent = true;
    material.depthTest = false;
    material.depthWrite = false;
    quad.renderOrder = 1000;
    // Feed the SHARED camera to the shader every frame. This single line is what
    // replaces the deleted viewer's entire camera stack.
    const drawingBufferSize = new THREE.Vector2();
    quad.onBeforeRender = (renderer, _scene, camera) => {
      renderer.getDrawingBufferSize(drawingBufferSize);
      updateImplicitCadMaterialUniforms(material, camera, drawingBufferSize.x, drawingBufferSize.y);
      // Swap quality tiers the moment the gesture starts or ends. Cheap: a
      // boolean compare per frame, uniform writes only on the transition.
      const runtime = runtimeRef.current;
      const tier = interactionQuality(runtime);
      if (passRef.current === nextPass && passRef.current.appliedTier !== tier) {
        applyUniforms(runtime, modelRef.current, tier);
      }
    };
    // Hide until the program links: the shared loop would otherwise compile it
    // synchronously on the next frame and freeze the tab on a heavy model.
    quad.visible = false;
    runtime.scene.add(quad);
    passRef.current = nextPass;
    shaderErrorRef.current?.(null);
    applyUniforms(runtime, model);

    const reveal = () => {
      if (passRef.current === nextPass) {
        quad.visible = true;
        runtime.requestRender?.();
      }
    };
    if (typeof runtime.renderer?.compileAsync === "function") {
      const compiling = runtime.renderer.compileAsync(runtime.scene, runtime.camera)
        .catch(() => {});
      nextPass.pendingCompile = compiling;
      compiling.then(() => {
        nextPass.pendingCompile = null;
        reveal();
      });
    } else {
      reveal();
    }
    runtime.requestRender?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, model, runtimeRef, themeSettings, viewerReadyTick]);

  // Theme and graphics settings are uniform-only updates.
  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!enabled || !runtime) {
      return;
    }
    applyUniforms(runtime, model);
    runtime.requestRender?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, model, normalizedGraphicsSettings, themeSettings, viewerReadyTick]);

  // Publish the model envelope for the shared fit. The declared bounds land
  // immediately so the first frame is framed; the CPU SDF scan then reports a
  // tighter envelope and the caller re-fits once. Never runs during dynamic
  // render: an animation would otherwise spawn a scan per frame.
  useEffect(() => {
    const runtime = runtimeRef.current;
    if (!enabled || !runtime || !model) {
      return;
    }
    const declared = implicitModelBounds(model);
    if (declared) {
      modelBoundsRef.current?.(declared, { refined: false });
    }
    if (dynamicRenderActiveRef.current) {
      return;
    }
    const key = implicitBoundsKey(model);
    if (key && runtime.implicitRefinedBoundsKey === key) {
      return;
    }
    runtime.implicitRefinedBoundsKey = key;
    const token = (runtime.implicitRefineToken = (runtime.implicitRefineToken || 0) + 1);
    const pass = passRef.current;
    let cancelled = false;

    Promise.resolve()
      .then(async () => {
        if (pass?.material) {
          await refreshImplicitCadFloorBounds(pass.material, model);
        }
        return estimateImplicitCadFrameBoundsAsync(model);
      })
      .then((refined) => {
        const activeRuntime = runtimeRef.current;
        if (
          cancelled ||
          activeRuntime !== runtime ||
          runtime.implicitRefineToken !== token ||
          passRef.current !== pass
        ) {
          return;
        }
        runtime.requestRender?.();
        if (!refined || dynamicRenderActiveRef.current) {
          return;
        }
        modelBoundsRef.current?.({ min: [...refined.min], max: [...refined.max] }, { refined: true });
      })
      .catch(() => {
        if (!cancelled && runtimeRef.current === runtime && runtime.implicitRefinedBoundsKey === key) {
          runtime.implicitRefinedBoundsKey = "";
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, model, runtimeRef, viewerReadyTick]);

  // Tear the pass down when the entry stops being an implicit, when the runtime
  // is recreated, or on unmount.
  useEffect(() => {
    if (enabled) {
      return undefined;
    }
    const pass = passRef.current;
    if (pass) {
      passRef.current = null;
      disposePass(pass);
      runtimeRef.current?.requestRender?.();
    }
    return undefined;
  }, [enabled, runtimeRef, viewerReadyTick]);

  useEffect(() => () => {
    const pass = passRef.current;
    if (pass) {
      passRef.current = null;
      disposePass(pass);
    }
  }, []);
}

export default useImplicitRaymarch;
