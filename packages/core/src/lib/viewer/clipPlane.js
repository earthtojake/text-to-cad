export const STEP_CLIP_AXES = Object.freeze(["x", "y", "z"]);
// No clip object at all is no clip; a supplied one cuts unless it says `enabled: false`.
export const DEFAULT_STEP_CLIP_SETTINGS = Object.freeze({
  enabled: false,
  axis: "x",
  invert: false,
  partColors: true
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
    partColors: value.partColors !== false,
    ...(at !== null ? { at } : {})
  };
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

/**
 * Cut `material` (one, or a list) by `clipPlanes`, or by none for an empty list: the planes, their
 * shadows too, and a program rebuilt only when whether it clips, or by how many planes, changed.
 */
export function syncMaterialClipPlanes(material, clipPlanes) {
  if (!material) {
    return;
  }
  const materials = Array.isArray(material) ? material : [material];
  const clippingEnabled = Array.isArray(clipPlanes) && clipPlanes.length > 0;
  for (const item of materials) {
    if (!item) {
      continue;
    }
    const previousEnabled = item.userData?.cadClipPlaneEnabled === true;
    const previousCount = Number(item.userData?.cadClipPlaneCount) || 0;
    const previousShaderClipping = item.clipping === true;
    item.clippingPlanes = clippingEnabled ? clipPlanes : null;
    item.clipIntersection = false;
    item.clipShadows = clippingEnabled;
    if ("clipping" in item) {
      item.clipping = clippingEnabled;
    }
    const clipPlaneCount = clippingEnabled ? clipPlanes.length : 0;
    if (item.userData?.cadClipPlaneEnabled !== clippingEnabled
      || item.userData?.cadClipPlaneCount !== clipPlaneCount) {
      item.userData = {
        ...(item.userData || {}),
        cadClipPlaneEnabled: clippingEnabled,
        cadClipPlaneCount: clipPlaneCount
      };
    }
    if (
      previousEnabled !== clippingEnabled ||
      previousCount !== (clippingEnabled ? clipPlanes.length : 0) ||
      previousShaderClipping !== (item.clipping === true)
    ) {
      item.needsUpdate = true;
    }
  }
}

/** Clip's plane in the scene's coordinates, or null where it cuts nothing (off, or past the kept face of `bounds`). */
export function buildStepClipPlane(THREE, clip, bounds, modelOffset = null) {
  const normalized = normalizeStepClipSettings(clip);
  if (!normalized.enabled || (normalized.at === undefined && !bounds)) {
    return null;
  }
  const index = axisIndex(normalized.axis);
  // `at` in millimetres in the model's frame; without it, the middle of the model at rest.
  const position = clipAxisPosition(bounds, normalized);
  // A plane that cuts nothing (at or past the face on the kept side) activates no clipping
  // shaders or stencil caps, so an idle tool costs nothing.
  if (bounds) {
    const { min, max } = clipAxisBounds(bounds, normalized.axis);
    if (normalized.invert ? position <= min : position >= max) return null;
  }
  const normal = new THREE.Vector3(
    index === 0 ? 1 : 0,
    index === 1 ? 1 : 0,
    index === 2 ? 1 : 0
  );
  // Keep the lower-coordinate half by default, exposing the cut toward the
  // default camera. Flip reverses that side without moving the section plane.
  if (!normalized.invert) {
    normal.multiplyScalar(-1);
  }
  const point = modelOffset?.clone ? modelOffset.clone() : new THREE.Vector3(0, 0, 0);
  point.setComponent(index, point.getComponent(index) + position);
  return new THREE.Plane().setFromNormalAndCoplanarPoint(normal, point);
}
