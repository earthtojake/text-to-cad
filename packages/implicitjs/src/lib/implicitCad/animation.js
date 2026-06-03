import {
  normalizeParameterValue,
  normalizeParameterValues
} from "../../common/parameters.js";

function finiteNumber(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

export function findImplicitAnimation(definition, animationId = "") {
  const animations = Array.isArray(definition?.animations) ? definition.animations : [];
  if (!animations.length) {
    return null;
  }
  const id = String(animationId || "").trim();
  return animations.find((animation) => animation.id === id) || animations[0] || null;
}

export function normalizeImplicitAnimationElapsed(elapsedSec, animation) {
  const duration = Math.max(finiteNumber(animation?.duration, 1), 0.001);
  const elapsed = Math.max(finiteNumber(elapsedSec, 0), 0);
  return animation?.loop === false
    ? Math.min(elapsed, duration)
    : elapsed % duration;
}

export function animatedImplicitParameterValues(definition, animationOrId, baseValues = {}, elapsedSec = 0) {
  const animation = typeof animationOrId === "string"
    ? findImplicitAnimation(definition, animationOrId)
    : animationOrId;
  const normalizedBase = normalizeParameterValues(definition, baseValues);
  if (!definition || typeof animation?.update !== "function") {
    return normalizedBase;
  }
  const duration = Math.max(finiteNumber(animation.duration, 1), 0.001);
  const elapsed = normalizeImplicitAnimationElapsed(elapsedSec, animation);
  const nextValues = { ...normalizedBase };
  const set = (parameterId, value) => {
    const id = String(parameterId || "").trim();
    const parameter = definition.parameterMap?.[id];
    if (parameter) {
      nextValues[id] = normalizeParameterValue(parameter, value);
    }
  };

  animation.update({
    ...normalizedBase,
    elapsed,
    elapsedSec: elapsed,
    duration,
    progress: clamp(elapsed / duration, 0, 1),
    cycle: elapsed / duration,
    t: elapsed,
    time: elapsed,
    loop: animation.loop !== false,
    params: normalizedBase,
    set
  });

  return nextValues;
}

export function buildImplicitAnimatedModel(definition, {
  animationId = "",
  elapsedSec = 0,
  params = null,
  parameterValues = null,
  playing = false,
  speed = 1
} = {}) {
  if (!definition?.buildModel) {
    throw new Error("Implicit animation export requires a compiled implicit definition.");
  }
  const animation = findImplicitAnimation(definition, animationId);
  const baseValues = params || parameterValues || definition.defaultParameterValues || {};
  const animatedValues = animatedImplicitParameterValues(definition, animation, baseValues, elapsedSec);
  return definition.buildModel(animatedValues, {
    activeId: animation?.id || animationId,
    elapsedSec: normalizeImplicitAnimationElapsed(elapsedSec, animation),
    playing,
    speed
  });
}

export const implicitAnimatedParameterValues = animatedImplicitParameterValues;
export const buildImplicitAnimationModel = buildImplicitAnimatedModel;
