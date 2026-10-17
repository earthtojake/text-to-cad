import { normalizeControlValues } from "@text-to-cad/core/common/articulation.js";
import { restoreAnimationState } from "@text-to-cad/core/common/animationClock.js";
import { canonicalJson } from "./canonicalJson.js";

// What a STEP's pose is made of: the controls its joints are driven by (each one's id, unit,
// range and rest value) and its named poses, as one comparable string ("" for nothing to pose).
// A rebuild whose articulation declares the same keeps the pose in hand; one that declares
// anything else starts at the new defaults, since a pose is never fitted onto joints that
// changed. The definition's `url` is not part of it: a rebuild writes the sidecar again under a
// new version.
export function stepPoseLogic(definition) {
  const articulation = definition?.articulation;
  return articulation ? canonicalJson([articulation.controls || [], articulation.poses || {}]) : "";
}

// A model can be posed by Position or by a routine. The owner in hand wins: while a routine
// owns the pose, the Position values are not applied under it. Values are fitted to the
// articulation: within each control's limits, a control they do not name at its rest value, and
// a name it does not declare dropped. A model with no articulation has no values.
export function restoreMotionParameters(definition, values, animation) {
  const articulation = definition?.articulation || null;
  if (!articulation) return {};
  const animationOwnsPose = animation?.enabled !== false && Boolean(animation?.activeClipId);
  return normalizeControlValues(articulation, animationOwnsPose ? null : values || null);
}

// The animation state carried across a load, reconciled against the clips this model actually
// loaded. A routine never resumes: every open, and every reload of the clips, starts at rest.
export function restoreMotionAnimation(current, clips) {
  const restored = restoreAnimationState(current, clips);
  return { ...restored, playing: false, elapsedSec: 0 };
}
