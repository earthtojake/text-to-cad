import { DEFAULT_PART_COLOR_SETTINGS, normalizeExplodedViewSettings, validateDisplaySettings } from "./displaySettings.js";
import { DEFAULT_STEP_CLIP_SETTINGS, normalizeStepClipSettings } from "../lib/viewer/clipPlane.js";

/** @typedef {"solid" | "shaded" | "parts" | "xray" | "hidden-line" | "wireframe"} ViewMode */
/** @typedef {ViewMode | "render"} ViewLook */
/** @typedef {{colorMode?: "original" | "single" | "by-part", color?: string, colors?: string[]}} ViewParts */
/** @typedef {{enabled?: boolean, axis?: "x" | "y" | "z", at?: number, invert?: boolean, partColors?: boolean}} ViewClip */
/** @typedef {{enabled?: boolean, amount?: number}} ViewExploded */
/**
 * The public Viewer / snapshot vocabulary: the file's display mode, whether the grid is on, and
 * what every mode shares (appearance, camera, clip, exploded). A mode is a look of its own, at its
 * own defaults: there is nothing else to set in it.
 * @typedef {Object} ViewSettings
 * @property {ViewMode} [mode]
 * @property {boolean} [grid]
 * @property {"light" | "dark"} [appearance]
 * @property {{projection?: "orthographic" | "perspective", focalLength?: number}} [camera]
 * @property {ViewClip} [clip]
 * @property {ViewExploded} [exploded]
 */
/**
 * Preview's own settings, sparse: only what the person changed. Preview is no display mode: it is
 * the photographic look (Render) the viewer's Preview draws, kept apart from the display.
 * @typedef {{
 *   parts?: ViewParts,
 *   lighting?: {quality?: "preview" | "final", exposure?: number, rotation?: number, size?: number, fill?: number},
 *   background?: {color?: string, opacity?: number},
 *   floor?: {enabled?: boolean, placement?: "origin" | "lowest", color?: string, opacity?: number, finish?: "matte" | "glossy"}
 * }} PreviewSettings
 */
/** @typedef {{enabled: boolean, projection: "orthographic" | "perspective", focalLength: number}} ViewCamera */
/** @typedef {{enabled: boolean, style: "shaded" | "hidden" | "off", colorMode: "original" | "single" | "by-part", color: string, colors: string[], opacity: number}} ViewSurfaces */
/** @typedef {{enabled: boolean, visibility: "visible" | "all", color: string}} ViewEdges */
/** @typedef {{enabled: boolean, quality: "preview" | "final", exposure: number, rotation: number, size: number, fill: number}} ViewLighting */
/** @typedef {{enabled: boolean, color: string, opacity: number}} ViewPaint */
/** @typedef {ViewPaint & {placement: "origin" | "lowest", finish: "matte" | "glossy"}} ViewFloor */
/**
 * What the renderer draws: the look on screen mapped onto the scene's groups.
 * @typedef {Object} ResolvedViewSettings
 * @property {ViewLook} mode
 * @property {"light" | "dark"} appearance
 * @property {ViewCamera} camera
 * @property {ViewSurfaces} surfaces
 * @property {ViewEdges} edges
 * @property {ViewLighting} lighting
 * @property {ViewPaint} background
 * @property {ViewFloor} floor
 * @property {ViewPaint & {density: number}} grid
 * @property {ViewPaint} axes
 * @property {ReturnType<typeof normalizeStepClipSettings>} clip
 * @property {{enabled: boolean, amount: number}} exploded
 */
/** @typedef {{appearance?: "light" | "dark", lightingQuality?: "preview" | "final"}} ViewDefaults */

// A file's display modes, in the order its Display menu lists them. Solid is shaded with the
// model's CAD edges; Shaded the same surfaces without them; Parts is Solid with each part its own
// colour; X-ray, Hidden line and Wireframe are made of the edges. Preview's photographic look
// (Render) is none of them: it is asked for on its own, drawn with Preview's own settings.
export const VIEW_MODE_VALUES = Object.freeze(["solid", "shaded", "parts", "xray", "hidden-line", "wireframe"]);
export const VIEW_MODES = Object.freeze([
  Object.freeze({ id: "solid", label: "Solid" }),
  Object.freeze({ id: "shaded", label: "Shaded" }),
  Object.freeze({ id: "parts", label: "Parts" }),
  Object.freeze({ id: "xray", label: "X-ray" }),
  Object.freeze({ id: "hidden-line", label: "Hidden line" }),
  Object.freeze({ id: "wireframe", label: "Wireframe" })
]);
export const VIEW_SETTINGS_KEYS = Object.freeze(["mode", "grid", "appearance", "camera", "clip", "exploded"]);
export const VIEW_CAMERA_KEYS = Object.freeze(["projection", "focalLength"]);
// Preview's settings, in the order its panel lists them, and each group's fields.
export const PREVIEW_SETTING_KEYS = Object.freeze(["parts", "lighting", "background", "floor"]);
const PREVIEW_GROUP_FIELDS = {
  parts: ["colorMode", "color", "colors"],
  lighting: ["quality", "exposure", "rotation", "size", "fill"],
  background: ["color", "opacity"],
  floor: ["enabled", "placement", "color", "opacity", "finish"]
};
export const VIEW_COLOR_MODE_VALUES = Object.freeze(["original", "single", "by-part"]);
// Matte is the studio floor; glossy also reflects the model (photographicStudio.js).
export const VIEW_FLOOR_FINISH_VALUES = Object.freeze(["matte", "glossy"]);
export const VIEW_FLOOR_PLACEMENT_VALUES = Object.freeze(["lowest", "origin"]);
export const VIEW_LIGHTING_QUALITY_VALUES = Object.freeze(["preview", "final"]);

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
function boolean(value, field) {
  if (typeof value !== "boolean") throw new Error(`${field} must be a boolean`);
  return value;
}
function color(value, field) {
  if (typeof value !== "string" || !HEX.test(value.trim())) throw new Error(`${field} must be a hex color`);
  const text = value.trim().toLowerCase();
  return text.length === 4 ? `#${[...text.slice(1)].map(c => c + c).join("")}` : text;
}
const CHOICES = {
  projection: ["orthographic", "perspective"], colorMode: VIEW_COLOR_MODE_VALUES, quality: VIEW_LIGHTING_QUALITY_VALUES,
  placement: VIEW_FLOOR_PLACEMENT_VALUES, finish: VIEW_FLOOR_FINISH_VALUES
};
function field(key, entry, path) {
  if (key === "enabled") return boolean(entry, path);
  if (key === "color") return color(entry, path);
  if (key === "colors") {
    if (!Array.isArray(entry) || entry.length < 1 || entry.length > 50) throw new Error(`${path} must contain 1 to 50 hex colors`);
    return entry.map((c, i) => color(c, `${path}[${i}]`));
  }
  if (key === "opacity" || key === "fill") return number(entry, 0, 1, path);
  if (key === "focalLength") return number(entry, 20, 200, path);
  if (key === "exposure") return number(entry, -5, 5, path);
  if (key === "rotation") return number(entry, -180, 180, path);
  if (key === "size") return number(entry, 0.25, 3, path);
  return choice(entry, CHOICES[key], path);
}
function group(value, allowed, path) {
  keys(value, allowed, path);
  return Object.fromEntries(Object.entries(value).map(([key, entry]) => [key, field(key, entry, `${path}.${key}`)]));
}

/**
 * Validate without filling omitted settings or pinning inherited appearance.
 * @param {unknown} input
 * @returns {ViewSettings & {mode: ViewMode}}
 */
export function normalizeViewSettings(input = {}) {
  keys(input, VIEW_SETTINGS_KEYS, "display");
  const result = { mode: choice(Object.hasOwn(input, "mode") ? input.mode : "solid", VIEW_MODE_VALUES, "display.mode") };
  if (Object.hasOwn(input, "grid")) result.grid = boolean(input.grid, "display.grid");
  if (Object.hasOwn(input, "appearance")) result.appearance = choice(input.appearance, ["light", "dark"], "display.appearance");
  if (Object.hasOwn(input, "camera")) result.camera = group(input.camera, VIEW_CAMERA_KEYS, "display.camera");
  // Tools keep their established validation and sparse payload; no mode owns them.
  for (const name of ["clip", "exploded"]) {
    if (Object.hasOwn(input, name)) {
      validateDisplaySettings({ [name]: input[name] });
      result[name] = structuredClone(input[name]);
    }
  }
  return result;
}

/**
 * A stored display as far as this build can read it: each setting it knows and can validate, on
 * its own. Anything else (a setting a build no longer has, a mode it no longer offers) is left out,
 * never rewritten to fit.
 * @param {unknown} input @returns {ViewSettings & {mode: ViewMode}}
 */
export function readViewSettings(input) {
  if (!object(input)) return normalizeViewSettings({});
  const readable = {};
  for (const key of VIEW_SETTINGS_KEYS) {
    if (!Object.hasOwn(input, key)) continue;
    try { normalizeViewSettings({ [key]: input[key] }); readable[key] = input[key]; } catch { /* left out */ }
  }
  return normalizeViewSettings(readable);
}

/**
 * Preview's settings, validated and sparse.
 * @param {unknown} input @returns {PreviewSettings}
 */
export function normalizePreviewSettings(input = {}) {
  keys(input, PREVIEW_SETTING_KEYS, "preview");
  return Object.fromEntries(Object.entries(input).map(([key, value]) => [key, group(value, PREVIEW_GROUP_FIELDS[key], `preview.${key}`)]));
}

/** Stored Preview settings as far as this build can read them, group by group. @returns {PreviewSettings} */
export function readPreviewSettings(input) {
  if (!object(input)) return {};
  const readable = {};
  for (const key of PREVIEW_SETTING_KEYS) {
    if (!Object.hasOwn(input, key)) continue;
    try { readable[key] = normalizePreviewSettings({ [key]: input[key] })[key]; } catch { /* left out */ }
  }
  return readable;
}

// Where Preview's floor stands: at the model's lowest point ("lowest"), under it wherever it was
// authored, rather than the document's Z=0 plane ("origin", Model origin), which a person may still
// choose. The Render recipe's own backdrop default (`sceneSettings.js`) is this too, and the stills'
// Preview stands its floor there as well (cadgen's `render/occt.py`): one value for the Viewer and
// the snapshot.
export const RENDER_FLOOR_PLACEMENT = "lowest";

// The CAD edges' ink on a model's faces.
const EDGE_COLOR = "#253443";
// A line drawing's edges (Hidden line, Wireframe) have no surfaces behind them, only the backdrop:
// the dark edges that read on a part's faces vanish on a dark one, so there they are light.
function lineDrawingEdgeColor(appearance) {
  return appearance === "dark" ? "#c9d3de" : EDGE_COLOR;
}

/**
 * The measuring grid, the same in every mode that turns it on: plain to see without competing
 * with the model's edges. @param {"light" | "dark"} appearance
 */
export function viewGridDefaults(appearance = "light") {
  const dark = appearance === "dark";
  return { color: dark ? "#5d9ac0" : "#4ea8cc", opacity: dark ? 0.35 : 0.45, density: 1 };
}

/**
 * Every Preview setting at its defaults, in `appearance`.
 * @param {ViewDefaults} options
 */
export function previewDefaults({ appearance = "light", lightingQuality = "final" } = {}) {
  const dark = appearance === "dark";
  return {
    parts: { colorMode: "original", color: DEFAULT_PART_COLOR_SETTINGS.color, colors: [...DEFAULT_PART_COLOR_SETTINGS.colors] },
    lighting: { quality: choice(lightingQuality, VIEW_LIGHTING_QUALITY_VALUES, "lightingQuality"), exposure: 0, rotation: 0, size: 1, fill: 0.25 },
    background: { color: dark ? "#202226" : "#ffffff", opacity: 1 },
    floor: { enabled: true, placement: RENDER_FLOOR_PLACEMENT, color: dark ? "#202226" : "#e7e7e5", opacity: 0.6, finish: "matte" }
  };
}

/**
 * Every Preview setting as it stands: its defaults under what the person changed.
 * @param {unknown} input @param {ViewDefaults} options
 */
export function resolvePreviewSettings(input = {}, options = {}) {
  const own = normalizePreviewSettings(input ?? {});
  return Object.fromEntries(Object.entries(previewDefaults(options)).map(([key, value]) => [key, { ...value, ...own[key] }]));
}

/** Whether Preview's settings differ from its defaults: what its Reset takes away. */
export function previewSettingsChanged(input = {}, options = {}) {
  return JSON.stringify(resolvePreviewSettings(input, options)) !== JSON.stringify(resolvePreviewSettings({}, options));
}

// What a view offers is declared by whoever shows it, as explicit opt-in lists: the modes it
// lists and the settings it has. Nothing here knows who opts in to what. `edges`: the file has
// CAD edges for Solid and Parts to draw. `clip` and `exploded`: the model tools it offers.
export const VIEW_SETTING_IDS = Object.freeze(["edges", "clip", "exploded"]);

/**
 * @typedef {object} ViewFeatures
 * @property {readonly string[]} modes  Modes it lists (`VIEW_MODE_VALUES`).
 * @property {readonly string[]} settings  Settings it has (`VIEW_SETTING_IDS`).
 */

/** Every mode and setting: a STEP assembly. @type {ViewFeatures} */
export const ALL_VIEW_FEATURES = Object.freeze({ modes: VIEW_MODE_VALUES, settings: VIEW_SETTING_IDS });

// A view without edges: shaded surfaces alone, which is Solid. Shaded would be Solid again, and
// X-ray, Hidden line and Wireframe are made of edges (drawn from triangles alone they would show
// the tessellation). Clip and Explode section solids and move parts, which it does not have either.
/** @type {ViewFeatures} */
export const EDGELESS_VIEW_FEATURES = Object.freeze({ modes: Object.freeze(["solid"]), settings: Object.freeze([]) });

/** A STEP part file: one part, so no Parts and no Explode. @type {ViewFeatures} */
export const STEP_PART_VIEW_FEATURES = Object.freeze({
  modes: Object.freeze(VIEW_MODE_VALUES.filter(mode => mode !== "parts")),
  settings: Object.freeze(VIEW_SETTING_IDS.filter(id => id !== "exploded"))
});

/** A cadgen engine document: what a STEP assembly offers (its CAD edges in every mode, Clip, Explode). @type {ViewFeatures} */
export const XBF_VIEW_FEATURES = ALL_VIEW_FEATURES;
/** A cadgen engine document of one part: what a STEP part file offers (no Parts, no Explode). @type {ViewFeatures} */
export const XBF_PART_VIEW_FEATURES = STEP_PART_VIEW_FEATURES;

/**
 * What a file of `kind` offers, for the viewer and a snapshot alike: a STEP everything; any other
 * 3D file (STL, 3MF, GLB, a robot) has no CAD edges, so Solid, and Parts where it has several
 * parts, objects or links (`parts`); Clip cuts whatever it draws (`lib/viewer/sceneClip.js`), and a
 * GLB of several parts explodes (`explodeParts`, `sceneExplode.js`). A drawing (DXF) no more than
 * an edgeless view: nothing in it to cut.
 * @param {string} kind  The file's extension, without the dot.
 * @param {{ parts?: number, explodeParts?: number }} [scene]
 * @returns {ViewFeatures}
 */
export function viewFeaturesForKind(kind, { parts = 0, explodeParts = 0 } = {}) {
  const normalized = String(kind || "").trim().toLowerCase();
  if (normalized === "step" || normalized === "stp") return ALL_VIEW_FEATURES;
  if (normalized === "dxf") return EDGELESS_VIEW_FEATURES;
  // A cadgen engine document is offered what a STEP is: an assembly everything, a part no Parts or Explode.
  if (normalized === "xbf") return parts > 1 ? XBF_VIEW_FEATURES : XBF_PART_VIEW_FEATURES;
  return {
    modes: parts > 1 ? ["solid", "parts"] : ["solid"],
    settings: normalized === "glb" && explodeParts > 1 ? ["clip", "exploded"] : ["clip"]
  };
}

/**
 * How many parts a mesh scene draws, for Parts to colour: a 3MF's objects, a GLB's meshes, a
 * robot's link meshes (`meshScene.js`, `glbScene.js`, `robotScene.js`). An STL is one.
 */
export function scenePartCount(scene) {
  return Number(scene?.meshCount ?? scene?.partCount) || 0;
}

/** A caller's lists, with the full set standing in for any it left out. @returns {ViewFeatures} */
export function normalizeViewFeatures(features = null) {
  return {
    modes: Array.isArray(features?.modes) ? features.modes : ALL_VIEW_FEATURES.modes,
    settings: Array.isArray(features?.settings) ? features.settings : ALL_VIEW_FEATURES.settings
  };
}

/**
 * The look on screen, mapped onto the scene's groups: the file's mode at its defaults with the grid
 * as switched, or with `preview` Preview's photographic look (Render), whatever the mode, drawn with
 * Preview's own settings (`previewSettings`). `features` resolves a view that did not opt into
 * everything: a saved mode it does not list resolves as Solid, and a setting it does not have is
 * off. The saved settings are left alone, so they still mean X-ray, or Clip, in the next view that
 * offers them. Preview is always in perspective, and has no grid.
 *
 * @param {unknown} input
 * @param {ViewDefaults & { features?: ViewFeatures, preview?: boolean, previewSettings?: PreviewSettings }} options
 * @returns {ResolvedViewSettings}
 */
export function resolveViewSettings(input = {}, {
  appearance = "light", lightingQuality = "final", features = ALL_VIEW_FEATURES, preview = false, previewSettings = {}
} = {}) {
  const offered = normalizeViewFeatures(features);
  const offers = id => offered.settings.includes(id);
  const saved = normalizeViewSettings(input);
  const mode = preview ? "render" : offered.modes.includes(saved.mode) ? saved.mode : "solid";
  const resolvedAppearance = saved.appearance ?? (appearance === "dark" ? "dark" : "light");
  const studio = resolvePreviewSettings(previewSettings, { appearance: resolvedAppearance, lightingQuality });
  const lit = mode === "render";
  const original = previewDefaults().parts;
  const parts = lit ? studio.parts : mode === "parts" ? { ...original, colorMode: "by-part" } : original;
  const style = mode === "hidden-line" ? "hidden" : mode === "wireframe" ? "off" : "shaded";
  // Solid and Parts draw the model's visible edges where it has them; Shaded and Preview none;
  // the others are made of theirs.
  const edged = mode === "solid" || mode === "parts" ? offers("edges") : ["xray", "hidden-line", "wireframe"].includes(mode);
  const edges = {
    enabled: edged,
    visibility: mode === "xray" || mode === "wireframe" ? "all" : "visible",
    color: mode === "hidden-line" || mode === "wireframe" ? lineDrawingEdgeColor(resolvedAppearance) : EDGE_COLOR
  };
  const dark = resolvedAppearance === "dark";
  return {
    mode,
    appearance: resolvedAppearance,
    camera: {
      enabled: true,
      projection: lit ? "perspective" : saved.camera?.projection ?? "orthographic",
      focalLength: saved.camera?.focalLength ?? 50
    },
    surfaces: { enabled: true, style, ...parts, colors: [...parts.colors], opacity: mode === "xray" ? 0.22 : 1 },
    edges,
    lighting: { enabled: lit, ...studio.lighting },
    background: { enabled: lit, ...studio.background },
    floor: { ...studio.floor, enabled: lit && studio.floor.enabled },
    grid: { enabled: !lit && saved.grid === true, ...viewGridDefaults(resolvedAppearance) },
    // The scene still has an axis guide; no view turns it on.
    axes: { enabled: false, color: dark ? "#5b8cff" : "#3d6fe8", opacity: 0.85 },
    clip: normalizeStepClipSettings(offers("clip") ? saved.clip ?? DEFAULT_STEP_CLIP_SETTINGS : DEFAULT_STEP_CLIP_SETTINGS),
    exploded: normalizeExplodedViewSettings(offers("exploded") ? saved.exploded : null)
  };
}
