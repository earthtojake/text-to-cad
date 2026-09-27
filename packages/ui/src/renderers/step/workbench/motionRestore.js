import { normalizeParameterValues } from "@hardcore/core/common/parameters.js";
import { restoreAnimationState } from "@hardcore/core/common/animationClock.js";

// A model can be posed by Position or by a routine. The owner in hand wins: while a routine
// owns the pose, the Position values are not applied under it.
export function restoreMotionParameters(definition, values, animation) {
  const animationOwnsPose = animation?.enabled !== false && Boolean(animation?.activeClipId);
  return normalizeParameterValues(definition,
    animationOwnsPose ? definition?.defaultParameterValues : values || definition?.defaultParameterValues);
}

// The animation state carried across a load, reconciled against the clips this model actually
// compiled. A routine never resumes: every open, and every reload of the clips, starts at rest.
export function restoreMotionAnimation(current, clips) {
  const restored = restoreAnimationState(current, clips);
  return { ...restored, playing: false, elapsedSec: 0 };
}
