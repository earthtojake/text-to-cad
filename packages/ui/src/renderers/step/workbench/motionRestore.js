import { normalizeParameterValues } from "@hardcore/core/common/parameters.js";
import { restoreAnimationState } from "@hardcore/core/common/animationClock.js";

// Older sessions could store both a posed model and an animation frame. The
// recorded owner wins; never restore the other producer's dormant transforms.
export function restoreMotionParameters(definition, values, animation) {
  const animationOwnsPose = animation?.enabled !== false && Boolean(animation?.activeClipId);
  return normalizeParameterValues(definition,
    animationOwnsPose ? definition?.defaultParameterValues : values || definition?.defaultParameterValues);
}

export function restoreMotionAnimation(stored, clips) {
  const restored = restoreAnimationState(stored, clips);
  return restored.enabled ? restored : { ...restored, playing: false, elapsedSec: 0 };
}
