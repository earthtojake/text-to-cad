import { useEffect, useRef } from "react";
import { createHeightSchedule } from "@text-to-cad/core/common/studioContactShadow.js";
import {
  applyExplodedViewProgress, clearExplodedViewRecords, computeExplodedViewLayout, easeExplodedViewProgress
} from "@text-to-cad/core/lib/viewer/explodedView.js";
import { applyDisplayRecordTransform, toNumber } from "@text-to-cad/core/lib/viewer/modelRuntime.js";
import { syncRecordTopologyDisplayEdgeTransforms } from "@text-to-cad/core/lib/viewer/topologyDisplayEdgeLine.js";
import { clamp } from "../../kit/camera/viewportCameraKit.js";
import { inactiveExplodedViewNeedsReset } from "../render/explodedViewLifecycle.js";

const EXPLODED_VIEW_ANIMATION_DURATION_MS = 1000;
/** While the explosion eases, the stage follows it at most this often (`createExplodedStage`). */
const EXPLODED_STAGE_INTERVAL_MS = 100;

const clockNow = () => (typeof performance !== "undefined" && typeof performance.now === "function"
  ? performance.now()
  : Date.now());

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

/**
 * The stage follows the parts to where they are drawn, as it follows a pose (`useStepPose`):
 * the lights, the key's shadow and the depth range are fitted to the box the explosion fills
 * (`refit`: the scene's bounds, then `syncSceneBounds`), while the floor keeps its rest
 * footprint. The pose pass refits it too, but it runs before this layer in a commit, so on its
 * own the stage stayed fitted to the model as it was before the explosion moved it.
 *
 * Where the explosion comes to rest (`settled`: a snap of the slider, the end of an ease, a
 * collapse to rest) the stage is refitted at once, so at rest it always holds the box the parts
 * fill. A refit is cheap, under a millisecond for the hypercar's 1,450 records; a frame is not,
 * and a refit owed to a timer draws a frame of its own, in the middle of a slider drag. An ease
 * steps every frame for a second or two, so it is followed at most every `interval` ms
 * (`eased`), a step that comes sooner owed a refit when the interval is up, of wherever the
 * parts are by then: the floor shadow's schedule (`createHeightSchedule`).
 */
function createExplodedStage(refit, interval = EXPLODED_STAGE_INTERVAL_MS) {
  const follow = () => {
    refit();
    schedule.rendered();
  };
  const schedule = createHeightSchedule({ interval, requestFrame: follow });
  return {
    eased() {
      if (schedule.due()) follow();
    },
    settled: follow,
    /** No refit is owed any more: the scene it was owed to is going away. */
    cancel() {
      schedule.dispose();
    }
  };
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
  // A refit owed when the interval is up runs outside this render: it reads the viewport then.
  const viewportRef = useRef(viewport);
  viewportRef.current = viewport;
  const stageRef = useRef(null);
  stageRef.current ||= createExplodedStage(() => {
    const { runtimeRef: currentRuntimeRef, syncSceneBounds } = viewportRef.current;
    const runtime = currentRuntimeRef.current;
    if (!runtime?.cadScene) return;
    runtime.cadScene.refreshBounds?.();
    syncSceneBounds?.();
    runtime.requestRender?.();
  });
  useEffect(() => () => stageRef.current.cancel(), []);

  useEffect(() => {
    const runtime = runtimeRef.current;
    const animation = explodedViewAnimationRef.current;
    const stage = stageRef.current;
    cancelExplodedViewAnimation(explodedViewAnimationRef);
    const interruptedEase = animation.ease;
    animation.ease = null;

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
      stage.cancel();
      return undefined;
    }

    const THREE = runtime.THREE;
    const animationModelKey = modelKey || "";
    const modelChanged = animation.modelKey !== animationModelKey;
    // The layout is centred on the REST placement, never on the bounds as drawn: those include
    // the explosion itself (and a pose), so recomputing from them — a reload that restores an
    // explosion, a rebuild, an amount change — would re-centre the parts and drift the model.
    const baseBounds = runtime.zeroPoseBounds || meshData?.bounds || runtime.modelBounds;
    const targetProgress = explodedViewActive ? explodeAmount : 0;
    const wasEnabled = animation.enabled === true;
    animation.modelKey = animationModelKey;
    animation.enabled = explodedViewActive;
    // An ease outlives a run that changes nothing it eases. The scene sync answers the commit that
    // turns the view on or off with a new `displayRecordsToken`, which runs this effect again a
    // frame or two into the ease; snapping to the target there ended every ease before it showed.
    // It carries on toward the same target, over the records as they are now. A new target (an
    // amount, the other direction) or another model still ends it.
    const resumeEase = Boolean(interruptedEase && !modelChanged && Math.abs(interruptedEase.target - targetProgress) <= 1e-4);

    // Steady disabled state: nothing to evaluate. (When disabling from an
    // exploded state we still evaluate below so the collapse animates.)
    if (!explodedViewActive && !wasEnabled && !resumeEase) {
      if (!inactiveExplodedViewNeedsReset(animation, runtime.displayRecords)) {
        animation.layout = null;
        return undefined;
      }
      clearExplodedViewRecords(runtime.displayRecords);
      for (const record of runtime.displayRecords) {
        applyDisplayRecordTransform(THREE, record);
      }
      syncRecordTopologyDisplayEdgeTransforms(runtime, runtime.displayRecords);
      stage.settled();
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
      stage.settled();
      setExplodedViewPoseTick((tick) => tick + 1);
      runtime.requestRender?.();
      animation.progress = 0;
      return undefined;
    }

    // Ease `timeline` ({ start, target, startedAt, durationMs }) from where it is now: its first
    // step is applied at once, so fresh records are never drawn at rest in between.
    const ease = (timeline) => {
      animation.ease = timeline;
      const advance = (now) => {
        const linearProgress = clamp((now - timeline.startedAt) / timeline.durationMs, 0, 1);
        const eased = easeExplodedViewProgress(linearProgress);
        const progress = timeline.start + (timeline.target - timeline.start) * eased;
        animation.progress = progress;
        applyExplodedViewRuntimeProgress(runtime, layout, progress);
        if (linearProgress < 1) {
          stage.eased();
          animation.rafId = window.requestAnimationFrame((timestamp) => (
            advance(Number.isFinite(Number(timestamp)) ? Number(timestamp) : clockNow())
          ));
          return;
        }
        stage.settled();
        animation.rafId = 0;
        animation.ease = null;
        animation.progress = timeline.target;
        setExplodedViewPoseTick((tick) => tick + 1);
      };
      advance(clockNow());
      return () => {
        cancelExplodedViewAnimation(explodedViewAnimationRef);
      };
    };
    if (resumeEase) {
      return ease(interruptedEase);
    }

    // Animate only the enable/disable transition (explode/collapse). Amount
    // scrubs snap directly for a responsive feel — the slider is the timeline.
    const startProgress = clamp(toNumber(animation.progress, 0), 0, 1);
    const shouldAnimate = wasEnabled !== explodedViewActive && !modelChanged
      && Math.abs(targetProgress - startProgress) > 1e-4;

    if (!shouldAnimate) {
      animation.progress = targetProgress;
      applyExplodedViewRuntimeProgress(runtime, layout, targetProgress);
      stage.settled();
      setExplodedViewPoseTick((tick) => tick + 1);
      return undefined;
    }

    // Multi-level cascades get more time so each stage of the disassembly
    // still reads at a calm pace.
    const durationMs = EXPLODED_VIEW_ANIMATION_DURATION_MS
      * (1 + 0.35 * Math.max(layout.levelCount - 1, 0));
    return ease({ start: startProgress, target: targetProgress, startedAt: clockNow(), durationMs });
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
