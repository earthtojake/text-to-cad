import { DEFAULT_PART_COLOR_SETTINGS, normalizeExplodedViewSettings, validateDisplaySettings } from "./displaySettings.js";
import { DEFAULT_STEP_CLIP_SETTINGS, normalizeStepClipSettings } from "../lib/viewer/clipPlane.js";

/** @typedef {"solid" | "render" | "xray" | "hidden-line" | "wireframe"} ViewPreset */
/** @typedef {{enabled: boolean, projection: "orthographic" | "perspective", focalLength: number}} ViewCamera */
/** @typedef {{enabled: boolean, style: "shaded" | "flat" | "hidden" | "off", colorMode: "original" | "single" | "by-part", color: string, colors: string[], opacity: number}} ViewSurfaces */
/** @typedef {{enabled: boolean, visibility: "visible" | "all", color: string}} ViewEdges */
/** @typedef {{enabled: boolean, quality: "preview" | "final", exposure: number, rotation: number, size: number, fill: number}} ViewLighting */
/** @typedef {{enabled: boolean, color: string, opacity: number}} ViewPaint */
/** @typedef {ViewPaint & {placement: "origin" | "lowest"}} ViewFloor */
/** @typedef {{enabled?: boolean, axis?: "x" | "y" | "z", offset?: number, offsets?: {x?: number, y?: number, z?: number}, invert?: boolean}} ViewClip */
/** @typedef {{enabled?: boolean, amount?: number}} ViewExploded */
/**
 * @typedef {Object} ViewSettings
 * @property {ViewPreset} [mode]
 * @property {"light" | "dark"} [appearance]
 * @property {Partial<ViewCamera>} [camera]
 * @property {Partial<ViewSurfaces>} [surfaces]
 * @property {Partial<ViewEdges>} [edges]
 * @property {Partial<ViewLighting>} [lighting]
 * @property {Partial<ViewPaint>} [background]
 * @property {Partial<ViewFloor>} [floor]
 * @property {Partial<ViewPaint>} [grid]
 * @property {Partial<ViewPaint>} [axes]
 * @property {ViewClip} [clip]
 * @property {ViewExploded} [exploded]
 */
/**
 * @typedef {Object} ResolvedViewSettings
 * @property {ViewPreset} mode
 * @property {"light" | "dark"} appearance
 * @property {ViewCamera} camera
 * @property {ViewSurfaces} surfaces
 * @property {ViewEdges} edges
 * @property {ViewLighting} lighting
 * @property {ViewPaint} background
 * @property {ViewFloor} floor
 * @property {ViewPaint} grid
 * @property {ViewPaint} axes
 * @property {ReturnType<typeof normalizeStepClipSettings>} clip
 * @property {{enabled: boolean, amount: number}} exploded
 */
/** @typedef {{appearance?: "light" | "dark", lightingQuality?: "preview" | "final"}} ViewDefaults */

// This is the public Viewer / snapshot vocabulary. The renderer's historical
// display modes remain an implementation detail behind resolveViewSceneSettings.
export const VIEW_PRESET_VALUES = Object.freeze(["solid", "render", "xray", "hidden-line", "wireframe"]);
export const VIEW_PRESETS = Object.freeze([
  Object.freeze({ id: "solid", label: "Solid" }),
  Object.freeze({ id: "render", label: "Render" }),
  Object.freeze({ id: "xray", label: "X-ray" }),
  Object.freeze({ id: "hidden-line", label: "Hidden line" }),
  Object.freeze({ id: "wireframe", label: "Wireframe" })
]);
export const VIEW_SETTINGS_KEYS = Object.freeze(["mode", "appearance", "camera", "surfaces", "edges", "lighting", "background", "floor", "grid", "axes", "clip", "exploded"]);
export const VIEW_CAMERA_KEYS = Object.freeze(["enabled", "projection", "focalLength"]);
export const VIEW_SURFACES_KEYS = Object.freeze(["enabled", "style", "colorMode", "color", "colors", "opacity"]);
export const VIEW_EDGES_KEYS = Object.freeze(["enabled", "visibility", "color"]);
export const VIEW_LIGHTING_KEYS = Object.freeze(["enabled", "quality", "exposure", "rotation", "size", "fill"]);
export const VIEW_BACKGROUND_KEYS = Object.freeze(["enabled", "color", "opacity"]);
export const VIEW_FLOOR_KEYS = Object.freeze(["enabled", "placement", "color", "opacity"]);
export const VIEW_GRID_KEYS = Object.freeze(["enabled", "color", "opacity"]);
export const VIEW_AXES_KEYS = Object.freeze(["enabled", "color", "opacity"]);
export const VIEW_SURFACE_STYLE_VALUES = Object.freeze(["shaded", "flat", "hidden", "off"]);
export const VIEW_COLOR_MODE_VALUES = Object.freeze(["original", "single", "by-part"]);
export const VIEW_EDGE_VISIBILITY_VALUES = Object.freeze(["visible", "all"]);
export const VIEW_GROUP_KEYS = Object.freeze(["camera", "surfaces", "edges", "lighting", "background", "floor", "grid", "axes"]);

const GROUP_KEYS = {
  camera: VIEW_CAMERA_KEYS, surfaces: VIEW_SURFACES_KEYS, edges: VIEW_EDGES_KEYS,
  lighting: VIEW_LIGHTING_KEYS, background: VIEW_BACKGROUND_KEYS, floor: VIEW_FLOOR_KEYS,
  grid: VIEW_GRID_KEYS, axes: VIEW_AXES_KEYS
};
const HEX = /^#(?:[0-9a-fA-F]{3}){1,2}$/;
const object = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);
function keys(value, allowed, field) {
  if (!object(value)) throw new Error(`${field} must be an object`);
  const unknown = Object.keys(value).filter(key => !allowed.includes(key));
  if (unknown.length) throw new Error(`Unsupported ${field} fields: ${unknown.join(", ")}`);
}
function choice(value, allowed, field) {
  if (!allowed.includes(value)) throw new Error(`${field} must be one of: ${allowed.join(", ")}`);
  return value;
}
function number(value, min, max, field) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max) {
    throw new Error(`${field} must be a finite number between ${min} and ${max}`);
  }
  return value;
}
function color(value, field) {
  if (typeof value !== "string" || !HEX.test(value.trim())) throw new Error(`${field} must be a hex color`);
  const text = value.trim().toLowerCase();
  return text.length === 4 ? `#${[...text.slice(1)].map(c => c + c).join("")}` : text;
}
function normalizeGroup(value, name) {
  const prefix = `display.${name}`;
  keys(value, GROUP_KEYS[name], prefix);
  const result = {};
  for (const [key, entry] of Object.entries(value)) {
    const field = `${prefix}.${key}`;
    if (key === "enabled") {
      if (typeof entry !== "boolean") throw new Error(`${field} must be a boolean`);
      result[key] = entry;
    } else if (key === "color") result[key] = color(entry, field);
    else if (key === "colors") {
      if (!Array.isArray(entry) || entry.length < 1 || entry.length > 50) throw new Error(`${field} must contain 1 to 50 hex colors`);
      result[key] = entry.map((c, i) => color(c, `${field}[${i}]`));
    } else if (key === "opacity" || key === "fill") result[key] = number(entry, 0, 1, field);
    else if (key === "focalLength") result[key] = number(entry, 20, 200, field);
    else if (key === "exposure") result[key] = number(entry, -5, 5, field);
    else if (key === "rotation") result[key] = number(entry, -180, 180, field);
    else if (key === "size") result[key] = number(entry, 0.25, 3, field);
    else result[key] = choice(entry, {
      projection: ["orthographic", "perspective"], style: VIEW_SURFACE_STYLE_VALUES,
      colorMode: VIEW_COLOR_MODE_VALUES, visibility: VIEW_EDGE_VISIBILITY_VALUES,
      quality: ["preview", "final"], placement: ["origin", "lowest"]
    }[key], field);
  }
  return result;
}

/**
 * Validate without filling omitted groups or pinning inherited appearance.
 * @param {unknown} input
 * @returns {ViewSettings & {mode: ViewPreset}}
 */
export function normalizeViewSettings(input = {}) {
  keys(input, VIEW_SETTINGS_KEYS, "display");
  const result = { mode: choice(Object.hasOwn(input, "mode") ? input.mode : "solid", VIEW_PRESET_VALUES, "display.mode") };
  if (Object.hasOwn(input, "appearance")) result.appearance = choice(input.appearance, ["light", "dark"], "display.appearance");
  for (const name of VIEW_GROUP_KEYS) {
    if (Object.hasOwn(input, name)) result[name] = normalizeGroup(input[name], name);
  }
  // Tools retain their established validation and sparse payload; they do not
  // become part of a preset or its Custom/reset comparison.
  for (const name of ["clip", "exploded"]) {
    if (Object.hasOwn(input, name)) {
      validateDisplaySettings({ [name]: input[name] });
      result[name] = structuredClone(input[name]);
    }
  }
  return result;
}

function defaults(appearance, lightingQuality) {
  const dark = appearance === "dark";
  return {
    camera: { enabled: true, projection: "orthographic", focalLength: 50 },
    surfaces: { enabled: true, style: "shaded", colorMode: "original", color: DEFAULT_PART_COLOR_SETTINGS.color, colors: [...DEFAULT_PART_COLOR_SETTINGS.colors], opacity: 1 },
    edges: { enabled: true, visibility: "visible", color: "#253443" },
    lighting: { enabled: false, quality: lightingQuality, exposure: 0, rotation: 0, size: 1, fill: 0.25 },
    background: { enabled: false, color: dark ? "#121315" : "#e7e7e5", opacity: 1 },
    floor: { enabled: false, placement: "origin", color: dark ? "#121315" : "#e7e7e5", opacity: 0.6 },
    grid: { enabled: true, color: dark ? "#495665" : "#cbd5e1", opacity: 0.16 },
    axes: { enabled: true, color: dark ? "#495665" : "#cbd5e1", opacity: 0.28 }
  };
}

// What a view offers is declared by whoever shows it, as explicit opt-in lists:
// the Display sections it mounts, the presets it lists and the surface styles it
// lists. Nothing here knows who opts in to what.
export const VIEW_SECTION_IDS = Object.freeze(["mode", "camera", "surfaces", "edges", "lighting", "background", "floor", "grid", "axes", "clip", "exploded"]);

/**
 * @typedef {object} ViewFeatures
 * @property {readonly string[]} sections  Display sections the view opts into (`VIEW_SECTION_IDS`).
 * @property {readonly string[]} modes  Presets it lists (`VIEW_PRESET_VALUES`).
 * @property {readonly string[]} surfaceStyles  Surface styles it lists (`VIEW_SURFACE_STYLE_VALUES`).
 */

/** Every section, preset and surface style. @type {ViewFeatures} */
export const ALL_VIEW_FEATURES = Object.freeze({
  sections: VIEW_SECTION_IDS,
  modes: VIEW_PRESET_VALUES,
  surfaceStyles: VIEW_SURFACE_STYLE_VALUES
});

// A view without edges. X-ray, Hidden line and Wireframe are made of edges; drawn
// from triangles alone they would show the tessellation. "hidden" and "off" exist
// to let edges carry the picture; without edges they draw an empty one. Clip and
// Explode section solids and move parts, which such a view does not have either.
/** @type {ViewFeatures} */
export const EDGELESS_VIEW_FEATURES = Object.freeze({
  sections: Object.freeze(VIEW_SECTION_IDS.filter(id => !["edges", "clip", "exploded"].includes(id))),
  modes: Object.freeze(["solid", "render"]),
  surfaceStyles: Object.freeze(["shaded", "flat"])
});

/** A caller's lists, with the full set standing in for any it left out. @returns {ViewFeatures} */
export function normalizeViewFeatures(features = null) {
  return {
    sections: Array.isArray(features?.sections) ? features.sections : ALL_VIEW_FEATURES.sections,
    modes: Array.isArray(features?.modes) ? features.modes : ALL_VIEW_FEATURES.modes,
    surfaceStyles: Array.isArray(features?.surfaceStyles) ? features.surfaceStyles : ALL_VIEW_FEATURES.surfaceStyles
  };
}

/**
 * `features` resolves a view that did not opt into everything. A section it left
 * out is off whatever was saved, a saved preset it does not list resolves as
 * Solid, and a surface style it does not list resolves as the neutral one. The
 * saved settings themselves are left alone, so the same settings still mean
 * X-ray, or a section, in the next view that offers them.
 *
 * @param {unknown} input @param {ViewDefaults & { features?: ViewFeatures }} options @returns {ResolvedViewSettings}
 */
export function resolveViewSettings(input = {}, { appearance = "light", lightingQuality = "final", features = ALL_VIEW_FEATURES } = {}) {
  const offered = normalizeViewFeatures(features);
  const offers = section => offered.sections.includes(section);
  const saved = normalizeViewSettings(input);
  const source = offered.modes.includes(saved.mode) ? saved : { ...saved, mode: "solid" };
  const resolvedAppearance = source.appearance ?? (appearance === "dark" ? "dark" : "light");
  const neutral = defaults(resolvedAppearance, choice(lightingQuality, ["preview", "final"], "lightingQuality"));
  const result = { mode: source.mode, appearance: resolvedAppearance, ...structuredClone(neutral) };
  if (source.mode === "render") {
    result.camera.projection = "perspective";
    for (const name of ["lighting", "background", "floor"]) result[name].enabled = true;
    for (const name of ["edges", "grid", "axes"]) result[name].enabled = false;
  } else if (source.mode === "xray") {
    result.surfaces.opacity = 0.22;
    result.edges.visibility = "all";
  } else if (source.mode === "hidden-line") {
    result.surfaces.style = "hidden";
  } else if (source.mode === "wireframe") {
    result.surfaces.style = "off";
    result.edges.visibility = "all";
  }
  for (const name of VIEW_GROUP_KEYS) {
    if (!Object.hasOwn(source, name)) continue;
    result[name] = { ...result[name], ...source[name], enabled: source[name].enabled !== false };
    if (!result[name].enabled) {
      result[name] = { ...neutral[name], enabled: false };
    }
  }
  if (!offers("edges")) result.edges = { ...neutral.edges, enabled: false };
  if (!offered.surfaceStyles.includes(result.surfaces.style)) result.surfaces = { ...result.surfaces, style: neutral.surfaces.style };
  result.clip = normalizeStepClipSettings(offers("clip") ? source.clip ?? DEFAULT_STEP_CLIP_SETTINGS : DEFAULT_STEP_CLIP_SETTINGS);
  result.exploded = normalizeExplodedViewSettings(offers("exploded") ? source.exploded : null);
  return result;
}

function comparable(view) {
  return Object.fromEntries(["appearance", ...VIEW_GROUP_KEYS].map(name => [name,
    view[name]?.enabled === false ? { enabled: false } : view[name]
  ]));
}

/** @param {unknown} input @param {ViewDefaults} options */
export function viewSettingsAreCustom(input = {}, options = {}) {
  const source = normalizeViewSettings(input);
  return JSON.stringify(comparable(resolveViewSettings(source, options))) !==
    JSON.stringify(comparable(resolveViewSettings({ mode: source.mode }, options)));
}

/** @param {unknown} input @returns {ViewSettings & {mode: ViewPreset}} */
export function resetViewSettings(input = {}) {
  const source = normalizeViewSettings(input);
  return { mode: source.mode };
}
