export function findStepModuleAnimation(definition, animationId) {
  const animations = Array.isArray(definition?.animations) ? definition.animations : [];
  if (!animations.length) {
    return null;
  }
  const normalizedId = String(animationId || "").trim();
  return animations.find((animation) => animation.id === normalizedId) || animations[0] || null;
}

export function buildDefaultStepModuleAnimationState(definition) {
  const animation = findStepModuleAnimation(definition, "");
  return {
    activeId: animation?.id || "",
    playing: false,
    elapsedSec: 0,
    speed: 1,
    // Runtime loop preference; defaults to the active animation's manifest
    // loop flag and can be toggled from the viewer without touching the model.
    loopEnabled: animation?.loop !== false
  };
}

export function animationNowMs() {
  if (typeof performance !== "undefined" && typeof performance.now === "function") {
    return performance.now();
  }
  return Date.now();
}
