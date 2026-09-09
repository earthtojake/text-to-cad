// ONE implementation of the effects pass. The sequence "kinematics module
// update → animation clip merge → apply effects to records" is the law both
// halves of the split meet in (the effect records, nowhere else), and it used
// to exist twice — the viewer's interactive pass and cadScene's headless
// twin. Both call THIS now, so a change to the sequence cannot drift.
//
// The caller keeps what is legitimately its own: resetting to rest when
// neither system has anything to say, applying record transforms, edge
// runtimes, alerts UI, bounds. This module owns only the shared state
// evaluation.

import { normalizeStepModuleParameterValues, resolveStepModuleFeatures } from "./stepModule.js";
import {
  applyStepModuleEffectsToRecords,
  buildStepModuleContext,
  createStepModuleEffectsApi
} from "./stepModuleEffects.js";
import { applyAnimationFrameToEffects, evaluateAnimationClip } from "./animationRuntime.js";

/**
 * Evaluate kinematics + animation into the runtime's display records.
 *
 * stepParameterRuntime: the POSE half — {definition, parameterValues,
 *   selectorRuntime?, ...} or null. The definition's module.update folds DOF
 *   values through the FK evaluator into matrix effects.
 * animation: the CHOREOGRAPHY half — {clip, elapsedSec} or null. Evaluated
 *   pure-in-t against the live meshData; its matrices premultiply whatever
 *   the mate graph wrote. Neither half knows about the other.
 *
 * Returns {applied, transformDetected, effectsByPartId}. applied=false means
 * neither system had anything to say — the caller resets to rest.
 */
export function applySceneState(THREE, {
  runtime,
  meshData,
  stepParameterRuntime = null,
  animation = null,
  selectorRuntime = null,
  onTransformEffect = null,
  onError = null,
  cleanup = null
}) {
  const definition = stepParameterRuntime?.definition || null;
  const module = definition?.module || null;
  const clip = animation?.clip || null;
  if ((!definition && !clip) || !meshData || !runtime) {
    return { applied: false, transformDetected: false, effectsByPartId: new Map() };
  }

  let transformDetected = false;
  const features = resolveStepModuleFeatures(definition, {
    meshData,
    selectorRuntime: selectorRuntime ?? stepParameterRuntime?.selectorRuntime ?? null
  });
  const effectsByPartId = new Map();
  const effects = createStepModuleEffectsApi(THREE, {
    meshData,
    features,
    runtime,
    effectsByPartId,
    onTransformEffect: () => {
      transformDetected = true;
      onTransformEffect?.();
    }
  });
  const ctx = buildStepModuleContext({
    runtime,
    stepModuleRuntime: stepParameterRuntime,
    features,
    effects,
    cleanup
  });

  try {
    module?.update?.(ctx);
    module?.render?.(ctx);
  } catch (error) {
    onError?.({ phase: "pose", error });
  }

  if (clip) {
    try {
      const frame = evaluateAnimationClip(THREE, meshData, clip, Number(animation?.elapsedSec) || 0);
      if (applyAnimationFrameToEffects(THREE, effectsByPartId, frame) > 0) {
        transformDetected = true;
      }
    } catch (error) {
      onError?.({ phase: "animation", error });
    }
  }

  applyStepModuleEffectsToRecords(THREE, runtime.displayRecords, effectsByPartId);
  return { applied: true, transformDetected, effectsByPartId };
}

/** Normalized DOF values for a definition (clamped, defaulted). */
export function sceneParameterValues(definition, values = {}) {
  return normalizeStepModuleParameterValues(definition, values);
}
