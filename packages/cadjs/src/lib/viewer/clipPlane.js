export const STEP_CLIP_AXES = Object.freeze(["x", "y", "z"]);
const DEFAULT_STEP_CLIP_OFFSETS = Object.freeze({
  x: 0,
  y: 0,
  z: 0
});
export const DEFAULT_STEP_CLIP_SETTINGS = Object.freeze({
  enabled: false,
  axis: "x",
  offset: DEFAULT_STEP_CLIP_OFFSETS.x,
  offsets: DEFAULT_STEP_CLIP_OFFSETS,
  invert: false
});

const AXIS_INDEX = Object.freeze({
  x: 0,
  y: 1,
  z: 2
});
const ACTIVE_CLIP_OFFSET_EPSILON = 1e-6;

function normalizeNumber(value, fallback) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) ? numericValue : fallback;
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

export function normalizeStepClipSettings(value = null) {
  const source = value && typeof value === "object" ? value : {};
  const axis = STEP_CLIP_AXES.includes(String(source.axis || "").toLowerCase())
    ? String(source.axis).toLowerCase()
    : DEFAULT_STEP_CLIP_SETTINGS.axis;
  const sourceOffsets = source.offsets && typeof source.offsets === "object" ? source.offsets : {};
  const legacyOffset = normalizeNumber(source.offset, DEFAULT_STEP_CLIP_SETTINGS.offset);
  const offsets = Object.fromEntries(
    STEP_CLIP_AXES.map((clipAxis) => [
      clipAxis,
      clamp(
        normalizeNumber(
          sourceOffsets[clipAxis],
          clipAxis === axis ? legacyOffset : DEFAULT_STEP_CLIP_OFFSETS[clipAxis]
        ),
        0,
        1
      )
    ])
  );
  const activeOffset = offsets[axis];
  const offsetEnabled = activeOffset > ACTIVE_CLIP_OFFSET_EPSILON;
  const requestedEnabled = source.enabled === true
    ? true
    : source.enabled === false
      ? false
      : offsetEnabled;
  return {
    enabled: requestedEnabled && offsetEnabled,
    axis,
    offset: activeOffset,
    offsets,
    invert: source.invert === true
  };
}

export function stepClipSettingsEqual(left, right) {
  const a = normalizeStepClipSettings(left);
  const b = normalizeStepClipSettings(right);
  return (
    a.enabled === b.enabled &&
    a.axis === b.axis &&
    Math.abs(a.offset - b.offset) < 1e-6 &&
    STEP_CLIP_AXES.every((axis) => Math.abs((a.offsets?.[axis] ?? DEFAULT_STEP_CLIP_OFFSETS[axis]) - (b.offsets?.[axis] ?? DEFAULT_STEP_CLIP_OFFSETS[axis])) < 1e-6) &&
    a.invert === b.invert
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

export function clipAxisPosition(bounds, settings) {
  const normalized = normalizeStepClipSettings(settings);
  const { min, max } = clipAxisBounds(bounds, normalized.axis);
  return min + ((max - min) * normalized.offset);
}

export function pointVisibleByClipPlane(clipPlane, point, epsilon = 1e-5) {
  if (!clipPlane || !point || typeof clipPlane.distanceToPoint !== "function") {
    return true;
  }
  const tolerance = Math.abs(normalizeNumber(epsilon, 1e-5));
  return clipPlane.distanceToPoint(point) >= -tolerance;
}

export function buildStepClipPatch(settings, patch) {
  const current = normalizeStepClipSettings(settings);
  const rawPatch = patch && typeof patch === "object" ? patch : {};
  const hasExplicitEnabled = Object.prototype.hasOwnProperty.call(rawPatch, "enabled");
  const hasOffsetPatch = Object.prototype.hasOwnProperty.call(rawPatch, "offset") ||
    (rawPatch.offsets && typeof rawPatch.offsets === "object");
  const patchedAxis = STEP_CLIP_AXES.includes(String(rawPatch.axis || "").toLowerCase())
    ? String(rawPatch.axis).toLowerCase()
    : current.axis;
  const offsets = {
    ...current.offsets,
    ...(rawPatch.offsets && typeof rawPatch.offsets === "object" ? rawPatch.offsets : {})
  };
  if (Object.prototype.hasOwnProperty.call(rawPatch, "offset")) {
    offsets[patchedAxis] = rawPatch.offset;
  }
  const activeOffset = clamp(normalizeNumber(offsets[patchedAxis], 0), 0, 1);
  return normalizeStepClipSettings({
    ...current,
    ...rawPatch,
    ...(!hasExplicitEnabled && hasOffsetPatch ? { enabled: activeOffset > ACTIVE_CLIP_OFFSET_EPSILON } : {}),
    axis: patchedAxis,
    offsets,
    offset: offsets[patchedAxis]
  });
}
