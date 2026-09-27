import { useEffect } from "react";
import {
  applyExplodedViewProgress, clearExplodedViewRecords, computeExplodedViewLayout, easeExplodedViewProgress
} from "@hardcore/core/lib/viewer/explodedView.js";
import { applyDisplayRecordTransform, toNumber } from "@hardcore/core/lib/viewer/modelRuntime.js";
import { syncRecordTopologyDisplayEdgeTransforms } from "@hardcore/core/lib/viewer/topologyDisplayEdgeLine.js";
import { clamp } from "../../kit/camera/viewportCameraKit.js";
import { inactiveExplodedViewNeedsReset } from "../render/explodedViewLifecycle.js";

const EXPLODED_VIEW_ANIMATION_DURATION_MS = 1000;

function cancelExplodedViewAnimation(animationRef) {
  const animation = animationRef?.current;
  if (!animation?.rafId || typeof window === "undefined") {
    return;
  }
  window.cancelAnimationFrame(animation.rafId);
  animation.rafId = 0;
}

export function displayRecordExplodedViewTranslation(THREE, record) {
  const elements = record?.explodedViewMatrix?.elements;
  if (!THREE?.Vector3 || !elements || elements.length < 16) {
    return THREE?.Vector3 ? new THREE.Vector3() : null;
  }
  return new THREE.Vector3(
    toNumber(elements[12]),
    toNumber(elements[13]),
    toNumber(elements[14])
  );
}

function applyExplodedViewRuntimeProgress(runtime, layout, progress) {
  if (!runtime?.THREE || !Array.isArray(runtime.displayRecords)) {
    return;
  }
  applyExplodedViewProgress(runtime.THREE, layout, progress);
  for (const record of runtime.displayRecords) {
    applyDisplayRecordTransform(runtime.THREE, record);
  }
  runtime.modelGroup?.updateMatrixWorld?.(true);
  runtime.edgesGroup?.updateMatrixWorld?.(true);
  if (runtime.topologyDisplayEdgeTransformByRecord === true) {
    syncRecordTopologyDisplayEdgeTransforms(runtime, runtime.displayRecords);
  }
  runtime.requestRender?.();
}

/**
 * The exploded view: a radial layout over the display records, eased in and out over a second
 * and snapped by the slider. It writes a per-record matrix and nothing else; it never frames
 * the camera, and 100% keeps meaning the rest framing.
 *
 * `displayRecordsToken` is why isolating a part while exploded does not collapse the model: a
 * rebuild makes fresh records, and state baked ONTO records has to be re-applied to them.
 * `explosionRef` is read by the static-reset receipt, which must not skip a reset while an
 * explosion is active, easing or still holding a pose.
 */
export function useStepExplode(layers) {
  const { viewport, props, policy, displayRecordsToken, setExplodedViewPoseTick, explosionRef: explodedViewAnimationRef } = layers;
  const { runtimeRef, viewerReadyTick } = viewport;
  const { meshData, modelKey, isLoading } = props;
  const { explodedViewActive, explodeAmount, normalizedExplodedSettings, focusedPartIds, normalizedThemeSettings } = policy;
  const meshGeometrySource = meshData?.geometrySource && typeof meshData.geometrySource === "object"
    ? meshData.geometrySource
    : meshData;

  useEffect(() => {
    const runtime = runtimeRef.current;
    const animation = explodedViewAnimationRef.current;
    cancelExplodedViewAnimation(explodedViewAnimationRef);

    if (
      !runtime?.THREE ||
      isLoading ||
      !Array.isArray(runtime.displayRecords) ||
      !runtime.displayRecords.length
    ) {
      animation.progress = 0;
      animation.modelKey = "";
      animation.enabled = false;
      animation.layout = null;
      return undefined;
    }

    const THREE = runtime.THREE;
    const animationModelKey = modelKey || "";
    const modelChanged = animation.modelKey !== animationModelKey;
    const baseBounds = runtime.modelBounds || meshData?.bounds;
    const targetProgress = explodedViewActive ? explodeAmount : 0;
    const wasEnabled = animation.enabled === true;
    animation.modelKey = animationModelKey;
    animation.enabled = explodedViewActive;

    // Steady disabled state: nothing to evaluate. (When disabling from an
    // exploded state we still evaluate below so the collapse animates.)
    if (!explodedViewActive && !wasEnabled) {
      if (!inactiveExplodedViewNeedsReset(animation, runtime.displayRecords)) {
        animation.layout = null;
        return undefined;
      }
      clearExplodedViewRecords(runtime.displayRecords);
      for (const record of runtime.displayRecords) {
        applyDisplayRecordTransform(THREE, record);
      }
      syncRecordTopologyDisplayEdgeTransforms(runtime, runtime.displayRecords);
      setExplodedViewPoseTick((tick) => tick + 1);
      runtime.requestRender?.();
      animation.progress = 0;
      animation.layout = null;
      return undefined;
    }

    // Compute the radial layout from the current records. On disable the
    // layout is still resolvable, so collapse can animate from the current
    // progress down to 0.
    const layout = computeExplodedViewLayout(runtime.displayRecords, baseBounds);
    animation.layout = layout;

    if (!layout.entries.length) {
      clearExplodedViewRecords(runtime.displayRecords);
      for (const record of runtime.displayRecords) {
        applyDisplayRecordTransform(THREE, record);
      }
      syncRecordTopologyDisplayEdgeTransforms(runtime, runtime.displayRecords);
      setExplodedViewPoseTick((tick) => tick + 1);
      runtime.requestRender?.();
      animation.progress = 0;
      return undefined;
    }

    // Animate only the enable/disable transition (explode/collapse). Amount
    // scrubs snap directly for a responsive feel — the slider is the timeline.
    const startProgress = clamp(toNumber(animation.progress, 0), 0, 1);
    const shouldAnimate = wasEnabled !== explodedViewActive && !modelChanged
      && Math.abs(targetProgress - startProgress) > 1e-4;

    if (!shouldAnimate) {
      animation.progress = targetProgress;
      applyExplodedViewRuntimeProgress(runtime, layout, targetProgress);
      setExplodedViewPoseTick((tick) => tick + 1);
      return undefined;
    }

    // Multi-level cascades get more time so each stage of the disassembly
    // still reads at a calm pace.
    const durationMs = EXPLODED_VIEW_ANIMATION_DURATION_MS
      * (1 + 0.35 * Math.max(layout.levelCount - 1, 0));
    const startedAt = typeof performance !== "undefined" && typeof performance.now === "function"
      ? performance.now()
      : Date.now();
    applyExplodedViewRuntimeProgress(runtime, layout, startProgress);

    const step = (timestamp) => {
      const now = Number.isFinite(Number(timestamp)) ? Number(timestamp) : Date.now();
      const linearProgress = clamp((now - startedAt) / durationMs, 0, 1);
      const eased = easeExplodedViewProgress(linearProgress);
      const progress = startProgress + (targetProgress - startProgress) * eased;
      animation.progress = progress;
      applyExplodedViewRuntimeProgress(runtime, layout, progress);
      if (linearProgress < 1) {
        animation.rafId = window.requestAnimationFrame(step);
      } else {
        animation.rafId = 0;
        animation.progress = targetProgress;
        setExplodedViewPoseTick((tick) => tick + 1);
      }
    };

    animation.rafId = window.requestAnimationFrame(step);
    return () => {
      cancelExplodedViewAnimation(explodedViewAnimationRef);
    };
  }, [
    explodedViewActive,
    explodeAmount,
    normalizedExplodedSettings,
    isLoading,
    meshData?.bounds,
    meshGeometrySource,
    modelKey,
    focusedPartIds.length,
    displayRecordsToken,
    normalizedThemeSettings,
    viewerReadyTick
  ]);
}
