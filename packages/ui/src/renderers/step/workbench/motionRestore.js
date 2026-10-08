import { normalizeControlValues } from "@text-to-cad/core/common/articulation.js";
import { restoreAnimationState } from "@text-to-cad/core/common/animationClock.js";

// A model can be posed by Position or by a routine. The owner in hand wins: while a routine
// owns the pose, the Position values are not applied under it.
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
