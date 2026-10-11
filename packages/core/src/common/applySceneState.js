// ONE implementation of the effects pass. The sequence "pose → animation clip merge →
// apply effects to records" is the law both halves of the split meet in (the effect
// records, nowhere else), and it used to exist twice — the viewer's interactive pass and
// cadScene's headless twin. Both call THIS now, so a change to the sequence cannot drift.
//
// The caller keeps what is legitimately its own: resetting to rest when neither system has
// anything to say, applying record transforms, edge runtimes, alerts UI, bounds. This
// module owns only the shared state evaluation.

import { applyArticulationToEffects } from "./articulation.js";
import { applyEffectsToRecords } from "./recordEffects.js";
import { applyAnimationFrameToEffects, evaluateAnimationClip } from "./animationRuntime.js";

/**
 * Evaluate the pose and the animation into the runtime's display records.
 *
 * pose: the POSE half — {articulation, values} or null. cadgen's articulation is played
 *   at the control values: joint deltas onto the occurrences each joint carries.
 * animation: the CHOREOGRAPHY half — {clip, elapsedSec} or null. Its keyframes are
 *   interpolated at elapsedSec; its matrices premultiply whatever the pose wrote. Neither
 *   half knows about the other.
 *
 * Returns {applied, transformDetected, appearanceChanged, effectsByPartId}. applied=false
 * means neither system had anything to say — the caller resets to rest.
 */
export function applySceneState(THREE, {
  runtime,
  meshData,
  pose = null,
  animation = null,
  onTransformEffect = null,
  onError = null
}) {
  const articulation = pose?.articulation || null;
  const clip = animation?.clip || null;
  if ((!articulation && !clip) || !meshData || !runtime) {
    return { applied: false, transformDetected: false, appearanceChanged: false, effectsByPartId: new Map() };
  }

  let transformDetected = false;
  const effectsByPartId = new Map();
  if (articulation) {
    try {
      if (applyArticulationToEffects(THREE, articulation, pose?.values, effectsByPartId) > 0) {
        transformDetected = true;
        onTransformEffect?.();
      }
    } catch (error) {
      onError?.({ phase: "pose", error });
    }
  }

  if (clip) {
    try {
      const frame = evaluateAnimationClip(THREE, clip, Number(animation?.elapsedSec) || 0);
      if (applyAnimationFrameToEffects(THREE, effectsByPartId, frame) > 0) {
        transformDetected = true;
      }
    } catch (error) {
      onError?.({ phase: "animation", error });
    }
  }

  const { appearanceChanged } = applyEffectsToRecords(THREE, runtime.displayRecords, effectsByPartId);
  return { applied: true, transformDetected, appearanceChanged, effectsByPartId };
}
