export function toFiniteNumber(value, fallback = 0) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

export function clampNumber(value, min, max) {
  return Math.min(Math.max(toFiniteNumber(value, min), min), max);
}

export function shallowObjectValuesEqual(left, right) {
  const leftKeys = Object.keys(left || {});
  const rightKeys = Object.keys(right || {});
  if (leftKeys.length !== rightKeys.length) {
    return false;
  }
  return leftKeys.every((key) => Object.hasOwn(right || {}, key) && left?.[key] === right?.[key]);
}
