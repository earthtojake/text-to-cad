export const STEP_CLIP_AXES = Object.freeze(["x", "y", "z"]);
// No clip object at all is no clip; a supplied one cuts unless it says `enabled: false`.
export const DEFAULT_STEP_CLIP_SETTINGS = Object.freeze({
  enabled: false,
  axis: "x",
  invert: false
});

const AXIS_INDEX = Object.freeze({
  x: 0,
  y: 1,
  z: 2
});

function normalizeNumber(value, fallback) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function normalizeAxis(value) {
  const axis = String(value || "").toLowerCase();
  return STEP_CLIP_AXES.includes(axis) ? axis : DEFAULT_STEP_CLIP_SETTINGS.axis;
}

/**
 * `at` is the plane's coordinate on its axis, in millimetres in the model's own frame; without
 * one the plane goes through the middle of the model at rest. `invert: false` keeps the
 * lower-coordinate side.
 */
export function normalizeStepClipSettings(value = null) {
  if (!value || typeof value !== "object") {
    return { ...DEFAULT_STEP_CLIP_SETTINGS };
  }
  const at = typeof value.at === "number" && Number.isFinite(value.at) ? value.at : null;
  return {
    enabled: value.enabled !== false,
    axis: normalizeAxis(value.axis),
    invert: value.invert === true,
    ...(at !== null ? { at } : {})
  };
}

export function stepClipSettingsEqual(left, right) {
  const a = normalizeStepClipSettings(left);
  const b = normalizeStepClipSettings(right);
  return (
    a.enabled === b.enabled &&
    a.axis === b.axis &&
    a.invert === b.invert &&
    (a.at ?? null) === (b.at ?? null)
  );
}

export function axisIndex(axis) {
  return AXIS_INDEX[String(axis || "").toLowerCase()] ?? AXIS_INDEX.x;
}

export function clipAxisBounds(bounds, axis) {
  const index = axisIndex(axis);
  const min = normalizeNumber(bounds?.min?.[index], 0);
  const max = normalizeNumber(bounds?.max?.[index], min);
  return min <= max ? { min, max } : { min: max, max: min };
}

/** Where the plane stands on its axis: `at`, else the middle of the bounds. */
export function clipAxisPosition(bounds, settings) {
  const normalized = normalizeStepClipSettings(settings);
  if (normalized.at !== undefined) return normalized.at;
  const { min, max } = clipAxisBounds(bounds, normalized.axis);
  return min + ((max - min) * 0.5);
}

/**
 * The share of the model (0..1) the clip cuts away, measured on its axis against `bounds` (the
 * model at rest, as the plane is placed): the viewer's "Clip amount". Off is 0; a plane outside
 * the bounds reads 0 or 1.
 */
export function clipAmount(settings, bounds) {
  const clip = normalizeStepClipSettings(settings);
  if (!clip.enabled) return 0;
  if (clip.at === undefined) return 0.5;
  const { min, max } = clipAxisBounds(bounds, clip.axis);
  const range = max - min;
  if (!(range > 0)) {
    return (clip.invert ? clip.at > min : clip.at < max) ? 1 : 0;
  }
  return clamp(clip.invert ? (clip.at - min) / range : (max - clip.at) / range, 0, 1);
}

/** The coordinate at which a clip on `settings`' axis and side cuts away `amount` (0..1) of `bounds`. */
export function clipAtForAmount(settings, bounds, amount) {
  const clip = normalizeStepClipSettings(settings);
  const { min, max } = clipAxisBounds(bounds, clip.axis);
  const share = clamp(normalizeNumber(amount, 0), 0, 1);
  return clip.invert ? min + (share * (max - min)) : max - (share * (max - min));
}

export function pointVisibleByClipPlane(clipPlane, point, epsilon = 1e-5) {
  if (!clipPlane || !point || typeof clipPlane.distanceToPoint !== "function") {
    return true;
  }
  const tolerance = Math.abs(normalizeNumber(epsilon, 1e-5));
  return clipPlane.distanceToPoint(point) >= -tolerance;
}

/**
 * A patch merges into the clip (no clip is the default, which cuts nothing). Placing the plane is
 * a cut, so a patch that gives `at` and says nothing of `enabled` turns the clip on; an axis or a
 * side alone leaves it as it was. `at` is a coordinate on one axis, so a patch that moves the clip
 * to another axis without placing it there drops it (the plane then goes through the middle).
 */
export function buildStepClipPatch(settings, patch) {
  const current = normalizeStepClipSettings(settings);
  const source = patch && typeof patch === "object" ? patch : {};
  const merged = { ...current, ...source };
  if (Object.hasOwn(source, "at") && !Object.hasOwn(source, "enabled")) {
    merged.enabled = true;
  }
  if (!Object.hasOwn(source, "at") && normalizeAxis(merged.axis) !== current.axis) {
    delete merged.at;
  }
  return normalizeStepClipSettings(merged);
}
