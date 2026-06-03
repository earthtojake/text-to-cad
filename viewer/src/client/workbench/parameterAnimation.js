export function findParameterAnimation(definition, animationId) {
  const animations = Array.isArray(definition?.animations) ? definition.animations : [];
  if (!animations.length) {
    return null;
  }
  const normalizedId = String(animationId || "").trim();
  return animations.find((animation) => animation.id === normalizedId) || animations[0] || null;
}

export function buildDefaultParameterAnimationState(definition) {
  const animation = findParameterAnimation(definition, "");
  return {
    activeId: animation?.id || "",
    playing: false,
    elapsedSec: 0,
    speed: 1
  };
}
