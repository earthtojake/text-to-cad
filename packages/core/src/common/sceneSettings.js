import {
  CAMERA_PROJECTION,
  normalizeCameraSpec
} from "./camera.js";
import {
  CAD_DISPLAY_MODE,
  CAD_PART_COLOR_MODE,
  DEFAULT_DISPLAY_SETTINGS,
  normalizePartColorSettings,
  normalizeDisplaySettings,
  validateDisplaySettings
} from "./displaySettings.js";
import { PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS } from "./photographicStudioRig.js";
import {
  cloneThemePresetSettings,
  normalizeThemeSettings
} from "./themeSettings.js";
import { resolveViewSettings } from "./viewSettings.js";

const SCENE_APPEARANCE = Object.freeze({
  SYSTEM: "system",
  LIGHT: "light",
  DARK: "dark"
});

/** @type {"system" | "light" | "dark"} */
const DEFAULT_SCENE_APPEARANCE = SCENE_APPEARANCE.SYSTEM;

// The studio, quality, envelope, lighting and backdrop vocabularies are the
// cross-language Render contract: cadgen's snapshot_core carries the same sets
// and tests/python/global/test_snapshot_viewer_theme_parity.py reads these
// exports from source to prove they still agree. Keep them exported and frozen.
export const RENDER_STUDIO = Object.freeze({
  LIGHT: "light",
  DARK: "dark"
});

export const RENDER_STUDIO_PRESETS = Object.freeze([
  Object.freeze({ id: RENDER_STUDIO.LIGHT, label: "Light studio" }),
  Object.freeze({ id: RENDER_STUDIO.DARK, label: "Dark studio" }),
]);

export const RENDER_QUALITY = Object.freeze({
  PREVIEW: "preview",
  FINAL: "final"
});

export const RENDER_QUALITY_PRESETS = Object.freeze([
  Object.freeze({ id: RENDER_QUALITY.PREVIEW, label: "Preview", sceneQuality: "standard" }),
  Object.freeze({ id: RENDER_QUALITY.FINAL, label: "Final", sceneQuality: "high" })
]);

export const SCENE_QUALITY = Object.freeze({
  INTERACTIVE: "interactive",
  STANDARD: "standard",
  HIGH: "high"
});

const SCENE_QUALITY_PRESETS = Object.freeze([
  Object.freeze({
    id: SCENE_QUALITY.INTERACTIVE,
    label: "Interactive",
    targetPixelError: 1.25,
    minimumLodLevel: 1,
    idlePixelRatioCap: 1.5,
    snapshotLodLevel: 1,
    renderScale: 1,
    shadowMapSize: 2048,
    environmentMapSize: 256
  }),
  Object.freeze({
    id: SCENE_QUALITY.STANDARD,
    label: "Standard",
    targetPixelError: 1,
    minimumLodLevel: 1,
    idlePixelRatioCap: 2,
    snapshotLodLevel: 1,
    renderScale: 1,
    shadowMapSize: 2048,
    environmentMapSize: 256
  }),
  Object.freeze({
    id: SCENE_QUALITY.HIGH,
    label: "High",
    targetPixelError: 0.25,
    minimumLodLevel: 1,
    idlePixelRatioCap: 2,
    snapshotLodLevel: 3,
    renderScale: 2,
    shadowMapSize: 4096,
    environmentMapSize: 512
  })
]);

export const RENDER_PAYLOAD_KEYS = Object.freeze([
  "studio",
  "quality",
  "exposure",
  "lighting",
  "backdrop"
]);

export const RENDER_LIGHTING_KEYS = Object.freeze([
  "rotation",
  "size",
  "fill"
]);

export const RENDER_BACKDROP_KEYS = Object.freeze([
  "color",
  "transparent",
  "ground",
  "groundPlacement",
  "groundColor",
  "groundOpacity"
]);

const RENDER_STUDIO_IDS = new Set(RENDER_STUDIO_PRESETS.map((preset) => preset.id));
const RENDER_QUALITY_BY_ID = new Map(RENDER_QUALITY_PRESETS.map((preset) => [preset.id, preset]));
const SCENE_QUALITY_BY_ID = new Map(SCENE_QUALITY_PRESETS.map((preset) => [preset.id, preset]));

export const DEFAULT_RENDER_LIGHTING = Object.freeze({
  rotation: 0,
  size: 1,
  fill: 0.25
});

// Keep the authored origin as the default reference; opacity lets geometry
// below that plane remain visible. "lowest" follows the current model bounds.
export const DEFAULT_RENDER_BACKDROP = Object.freeze({
  transparent: false,
  ground: true,
  groundPlacement: "origin",
  groundOpacity: 0.6
});

const STUDIO_BACKDROP_COLORS = Object.freeze({
  [RENDER_STUDIO.LIGHT]: "#e7e7e5",
  [RENDER_STUDIO.DARK]: "#121315"
});

const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}){1,2}$/;

const DEFAULT_NORMAL_CAMERA = Object.freeze({
  preset: "iso",
  projection: CAMERA_PROJECTION.ORTHOGRAPHIC
});

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function cloneValue(value) {
  if (Array.isArray(value)) {
    return value.map(cloneValue);
  }
  if (isPlainObject(value)) {
    return Object.fromEntries(Object.entries(value).map(([key, entry]) => [key, cloneValue(entry)]));
  }
  return value;
}

function validateKeys(source, allowed, fieldName) {
  const unknown = Object.keys(source).filter((key) => !allowed.includes(key));
  if (unknown.length) {
    throw new Error(`Unsupported ${fieldName} fields: ${unknown.join(", ")}`);
  }
}

function validateNumber(value, fieldName, min = -Infinity, max = Infinity) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max) {
    throw new Error(`${fieldName} must be a finite number between ${min} and ${max}`);
  }
}

function validateBoolean(value, fieldName) {
  if (typeof value !== "boolean") {
    throw new Error(`${fieldName} must be a boolean`);
  }
}

function validateColor(value, fieldName) {
  if (typeof value !== "string" || !HEX_COLOR_PATTERN.test(value.trim())) {
    throw new Error(`${fieldName} must be a hex color`);
  }
}

function validateRenderLighting(value) {
  if (!isPlainObject(value)) {
    throw new Error("render.lighting must be an object");
  }
  validateKeys(value, RENDER_LIGHTING_KEYS, "render.lighting");
  if (Object.hasOwn(value, "rotation")) validateNumber(value.rotation, "render.lighting.rotation", -180, 180);
  if (Object.hasOwn(value, "size")) validateNumber(value.size, "render.lighting.size", 0.25, 3);
  if (Object.hasOwn(value, "fill")) validateNumber(value.fill, "render.lighting.fill", 0, 1);
}

function validateRenderBackdrop(value) {
  if (!isPlainObject(value)) {
    throw new Error("render.backdrop must be an object");
  }
  validateKeys(value, RENDER_BACKDROP_KEYS, "render.backdrop");
  if (Object.hasOwn(value, "color")) validateColor(value.color, "render.backdrop.color");
  if (Object.hasOwn(value, "groundColor")) validateColor(value.groundColor, "render.backdrop.groundColor");
  if (Object.hasOwn(value, "groundOpacity")) validateNumber(value.groundOpacity, "render.backdrop.groundOpacity", 0, 1);
  if (Object.hasOwn(value, "transparent")) validateBoolean(value.transparent, "render.backdrop.transparent");
  if (Object.hasOwn(value, "ground")) validateBoolean(value.ground, "render.backdrop.ground");
  if (Object.hasOwn(value, "groundPlacement") && !["origin", "lowest"].includes(value.groundPlacement)) {
    throw new Error("render.backdrop.groundPlacement must be origin or lowest");
  }
}

function normalizeSceneAppearance(value = SCENE_APPEARANCE.SYSTEM, {
  prefersDark = false
} = {}) {
  const normalized = String(value ?? SCENE_APPEARANCE.SYSTEM).trim().toLowerCase();
  if (normalized === SCENE_APPEARANCE.SYSTEM) {
    return prefersDark ? SCENE_APPEARANCE.DARK : SCENE_APPEARANCE.LIGHT;
  }
  if (normalized === SCENE_APPEARANCE.LIGHT || normalized === SCENE_APPEARANCE.DARK) {
    return normalized;
  }
  throw new Error("appearance must be 'system', 'light', or 'dark'");
}

function normalizeRenderStudioId(value) {
  if (typeof value !== "string" || !RENDER_STUDIO_IDS.has(value)) {
    throw new Error(`Unknown render studio '${value}'. Expected one of: ${[...RENDER_STUDIO_IDS].join(", ")}`);
  }
  return value;
}

function normalizeRenderQuality(value = RENDER_QUALITY.FINAL) {
  if (typeof value !== "string" || !RENDER_QUALITY_BY_ID.has(value)) {
    throw new Error(`Unknown render quality '${value}'. Expected one of: ${[...RENDER_QUALITY_BY_ID.keys()].join(", ")}`);
  }
  return value;
}

export function normalizeSceneQuality(value, {
  fallback = SCENE_QUALITY.STANDARD
} = {}) {
  const normalized = String(value ?? fallback).trim().toLowerCase();
  if (!SCENE_QUALITY_BY_ID.has(normalized)) {
    throw new Error(`Unknown scene quality '${value}'. Expected one of: ${[...SCENE_QUALITY_BY_ID.keys()].join(", ")}`);
  }
  return normalized;
}

export function resolveSceneQuality(value, options = {}) {
  return { ...SCENE_QUALITY_BY_ID.get(normalizeSceneQuality(value, options)) };
}

export function resolveRenderQuality(value = RENDER_QUALITY.FINAL) {
  const renderQuality = RENDER_QUALITY_BY_ID.get(normalizeRenderQuality(value));
  return resolveSceneQuality(renderQuality.sceneQuality);
}

export function normalizeRenderPayload(render) {
  if (!isPlainObject(render)) {
    throw new Error("render must be an object");
  }
  validateKeys(render, RENDER_PAYLOAD_KEYS, "render");
  const result = {};
  if (Object.prototype.hasOwnProperty.call(render, "studio")) {
    result.studio = normalizeRenderStudioId(render.studio);
  }
  if (Object.hasOwn(render, "quality")) {
    result.quality = normalizeRenderQuality(render.quality);
  }
  if (Object.hasOwn(render, "exposure")) {
    validateNumber(render.exposure, "render.exposure", -5, 5);
    result.exposure = render.exposure;
  }
  if (Object.hasOwn(render, "lighting")) {
    validateRenderLighting(render.lighting);
    result.lighting = cloneValue(render.lighting);
  }
  if (Object.hasOwn(render, "backdrop")) {
    validateRenderBackdrop(render.backdrop);
    result.backdrop = cloneValue(render.backdrop);
  }
  return result;
}

/**
 * Expand a normalized Render payload into the RENDER RECIPE: the closed set of
 * controls Render exposes, each with its effective value. This is the only
 * input the photographic rig takes. It is not a CAD theme and never grows
 * lights, floors, or background gradients — an unlisted knob has no way in.
 */
function resolveRenderConfiguration(render = {}, appearance = SCENE_APPEARANCE.LIGHT) {
  const payload = normalizeRenderPayload(render);
  const studio = resolvedStudioId(payload.studio, appearance);
  return {
    studio,
    quality: payload.quality ?? RENDER_QUALITY.FINAL,
    exposure: payload.exposure ?? 0,
    lighting: {
      ...DEFAULT_RENDER_LIGHTING,
      ...(payload.lighting || {})
    },
    backdrop: {
      color: payload.backdrop?.color || STUDIO_BACKDROP_COLORS[studio],
      transparent: payload.backdrop?.transparent ?? DEFAULT_RENDER_BACKDROP.transparent,
      ground: payload.backdrop?.ground ?? DEFAULT_RENDER_BACKDROP.ground,
      groundPlacement: payload.backdrop?.groundPlacement ?? DEFAULT_RENDER_BACKDROP.groundPlacement,
      groundColor: payload.backdrop?.groundColor || payload.backdrop?.color || STUDIO_BACKDROP_COLORS[studio],
      groundOpacity: payload.backdrop?.groundOpacity ?? DEFAULT_RENDER_BACKDROP.groundOpacity
    }
  };
}

function resolvedStudioId(studio, appearance) {
  if (studio != null) {
    return studio;
  }
  return appearance === SCENE_APPEARANCE.DARK
    ? RENDER_STUDIO.DARK
    : RENDER_STUDIO.LIGHT;
}

/**
 * The CAD inspection scene settings — the theme model. Only the Inspect path
 * reads these. Render has no theme: it is built from the Render recipe alone.
 */
function cadSceneSettings(appearance) {
  const normalized = normalizeThemeSettings(cloneThemePresetSettings(
    appearance === SCENE_APPEARANCE.DARK ? "workbench-dark" : "workbench-light"
  ));
  return {
    materials: cloneValue(normalized.materials),
    background: cloneValue(normalized.background),
    floor: cloneValue(normalized.floor),
    environment: cloneValue(normalized.environment),
    lighting: cloneValue(normalized.lighting)
  };
}

function cameraPatch(value) {
  if (value == null) {
    return null;
  }
  return typeof value === "string" ? { preset: value } : cloneValue(value);
}

function resolveCamera(base, ...overrides) {
  let merged = cloneValue(base);
  for (const override of overrides) {
    const patch = cameraPatch(override);
    if (patch) {
      // A higher-priority named view selects that view in full. Retaining a
      // lower-priority custom pose would make `{preset: "front"}` still show
      // the copied Render camera. A projection-only patch intentionally keeps
      // the pose so callers can switch lenses without losing framing.
      if (Object.prototype.hasOwnProperty.call(patch, "preset")) {
        for (const field of ["name", "position", "target", "direction", "up", "zoom", "orthographicHalfHeight"]) {
          delete merged[field];
        }
      } else if (
        Object.prototype.hasOwnProperty.call(patch, "direction") &&
        !Object.prototype.hasOwnProperty.call(patch, "position")
      ) {
        // A higher-priority direction is another complete orientation choice.
        // Drop a copied position that would otherwise make normalization infer
        // direction from position -> target and silently ignore this patch.
        // The target and up vector remain useful framing/roll inputs.
        for (const field of ["name", "preset", "position", "orthographicHalfHeight"]) {
          delete merged[field];
        }
      }
      merged = { ...merged, ...patch };
    }
  }
  const spec = normalizeCameraSpec(merged, {
    strict: true,
    defaultProjection: base.projection
  });
  const result = {
    preset: spec.preset,
    name: spec.name,
    projection: spec.projection,
    direction: [...spec.direction],
    up: [...spec.up],
    zoom: spec.zoom
  };
  if (spec.focalLength != null) {
    result.focalLength = spec.focalLength;
  }
  if (spec.orthographicHalfHeight != null) {
    result.orthographicHalfHeight = spec.orthographicHalfHeight;
  }
  if (spec.position) {
    result.position = [...spec.position];
  }
  if (spec.target) {
    result.target = [...spec.target];
  }
  return result;
}

function resolveDisplay(base, ...overrides) {
  let resolved = normalizeDisplaySettings(base, { fallback: base });
  for (const override of overrides) {
    if (override != null) {
      validateDisplaySettings(override);
      resolved = normalizeDisplaySettings(override, { fallback: resolved });
    }
  }
  return resolved;
}

export function resolveDisplayMaterialSettings(materialSettings = {}, partColorSettings = null) {
  const partColor = normalizePartColorSettings(partColorSettings);
  if (partColor.mode === CAD_PART_COLOR_MODE.ORIGINAL) {
    return { ...materialSettings };
  }
  const materials = { ...materialSettings, overrideSourceColors: true };
  if (partColor.mode === CAD_PART_COLOR_MODE.SINGLE) {
    materials.defaultColor = partColor.color;
    materials.fillColors = [partColor.color];
    materials.cycleColors = false;
  } else {
    materials.defaultColor = partColor.colors[0] || partColor.color;
    materials.fillColors = [...partColor.colors];
    materials.cycleColors = true;
  }
  return materials;
}

/**
 * Whether a scene is lit by the photographic studio: Render asked for, with its lighting
 * on. A floor or a custom background alone opts the stage into the studio, not the
 * model's surfaces. `renderMode` and `renderConfiguration` are `render.enabled` and
 * `render.configuration` of `resolveViewSceneSettings`.
 */
export function scenePhotographicLighting({ renderMode = false, renderConfiguration = null } = {}) {
  return Boolean(renderMode) && renderConfiguration?.lighting?.enabled !== false;
}

/**
 * The surface LOOK a family's scene wears (`lib/viewer/sceneContract.js`) for resolved
 * scene settings: the finish (the theme's in Inspect, the studio's under photographic
 * Render), the Surfaces section's colour mode, style and opacity, and whether Render keeps
 * what the file authored. The viewer's viewport and the snapshot CLI's headless stage both
 * resolve a look HERE, from the same `resolveViewSceneSettings` output, so one setting is
 * one look wherever a scene is drawn.
 *
 * @param {{ themeSettings?: object | null, displaySettings?: object | null, renderMode?: boolean,
 *   renderConfiguration?: object | null }} scene  `theme`, `display`, `render.enabled` and
 *   `render.configuration` of `resolveViewSceneSettings`.
 * @returns {import("../lib/viewer/sceneContract.js").SurfaceLook}
 */
export function resolveSceneSurfaceLook({ themeSettings = null, displaySettings = null, renderMode = false, renderConfiguration = null } = {}) {
  const photographic = scenePhotographicLighting({ renderMode, renderConfiguration });
  const display = normalizeDisplaySettings(displaySettings);
  // Grouped view resolution already decided the surface policy; normalization must not undo it.
  const surfaces = displaySettings?.surfaces || display.surfaces;
  return {
    materialSettings: resolveDisplayMaterialSettings(
      photographic ? PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS : normalizeThemeSettings(themeSettings || {}).materials,
      display.partColor
    ),
    authored: photographic,
    surface: surfaces ? { style: surfaces.style, opacity: surfaces.opacity } : null
  };
}

function applyPartColor(settings, partColor) {
  return {
    ...settings,
    materials: resolveDisplayMaterialSettings(settings.materials, partColor)
  };
}

/**
 * Resolve shared viewer/snapshot scene policy without retaining app state.
 *
 * Camera, display and model state are common. Inspect supplies `theme`, the CAD
 * workbench lighting recipe. Display mode Render instead supplies
 * `render.configuration`, the photographic lighting recipe; it has no theme,
 * so nothing can reach the CAD rig, floor or background gradients through it.
 */
export function resolveSceneSettings({
  appearance = DEFAULT_SCENE_APPEARANCE,
  prefersDark = false,
  quality = null,
  camera = null,
  display = null
} = {}) {
  const baseAppearance = normalizeSceneAppearance(appearance, { prefersDark });
  const resolvedDisplay = resolveDisplay(DEFAULT_DISPLAY_SETTINGS, display);
  const unifiedRender = resolvedDisplay.mode === CAD_DISPLAY_MODE.RENDER
    ? (resolvedDisplay.render || {})
    : null;
  if (unifiedRender == null) {
    const theme = applyPartColor(cadSceneSettings(baseAppearance), resolvedDisplay.partColor);
    return {
      appearance: baseAppearance,
      render: { enabled: false, configuration: null, payload: null },
      theme,
      // Authored finishes are shared with Render. The workbench recipe supplies
      // fallback channels and lighting, never overrides the model's material.
      materialOverrides: null,
      quality: resolveSceneQuality(quality, { fallback: SCENE_QUALITY.INTERACTIVE }),
      camera: resolveCamera(DEFAULT_NORMAL_CAMERA, camera),
      display: resolvedDisplay
    };
  }

  const payload = normalizeRenderPayload(unifiedRender);
  const cameraSettings = resolveCamera(DEFAULT_NORMAL_CAMERA, camera);
  const configuration = {
    ...resolveRenderConfiguration(payload, baseAppearance),
    camera: cameraSettings
  };
  return {
    appearance: baseAppearance,
    render: { enabled: true, configuration, payload },
    theme: null,
    materialOverrides: null,
    quality: resolveRenderQuality(configuration.quality),
    camera: cameraSettings,
    display: resolvedDisplay
  };
}

/** Public grouped preset policy; historical display modes are draw details. */
export function resolveViewSceneSettings({
  display = {}, appearance = "light", prefersDark = false, camera = null, quality = null,
  lightingQuality = "final", features = undefined
} = {}) {
  const view = resolveViewSettings(display ?? {}, {
    appearance: normalizeSceneAppearance(appearance, { prefersDark }), lightingQuality, features
  });
  const surface = view.surfaces;
  const mode = surface.style === "off" ? CAD_DISPLAY_MODE.WIREFRAME
    : surface.style === "hidden" ? CAD_DISPLAY_MODE.HIDDEN_LINES_REMOVED
      : surface.style === "flat" ? CAD_DISPLAY_MODE.UNSHADED
        : surface.opacity < 1 ? CAD_DISPLAY_MODE.TRANSPARENT
          : view.edges.enabled ? CAD_DISPLAY_MODE.SHADED_EDGES : CAD_DISPLAY_MODE.SHADED;
  const partColor = { mode: surface.colorMode.replace("-", "_"), color: surface.color, colors: surface.colors };
  const resolvedDisplay = normalizeDisplaySettings({
    mode, clip: view.clip, exploded: view.exploded,
    edges: { enabled: view.edges.enabled, visibility: view.edges.visibility, color: view.edges.color },
    guides: { grid: view.grid, axis: view.axes }, partColor,
    surfaces: surface
  });
  const neutralTheme = applyPartColor(cadSceneSettings(view.appearance), partColor);
  neutralTheme.floor.enabled = false;
  const cameraSettings = resolveCamera(DEFAULT_NORMAL_CAMERA, camera, {
    projection: view.camera.projection, focalLength: view.camera.focalLength
  });
  const enabled = view.lighting.enabled || view.background.enabled || view.floor.enabled;
  const configuration = enabled ? {
    studio: view.appearance,
    quality: view.lighting.quality,
    exposure: view.lighting.enabled ? view.lighting.exposure : 0,
    lighting: { ...view.lighting },
    backdrop: {
      enabled: view.background.enabled,
      color: view.background.enabled ? view.background.color : neutralTheme.background.solidColor,
      opacity: view.background.enabled ? view.background.opacity : 1,
      transparent: view.background.enabled && view.background.opacity === 0,
      ground: view.floor.enabled,
      groundPlacement: view.floor.placement,
      groundColor: view.floor.color,
      groundOpacity: view.floor.opacity
    },
    camera: cameraSettings
  } : null;
  return {
    view,
    appearance: view.appearance,
    render: { enabled, configuration, payload: null },
    // A floor or custom background does not opt the model into studio lighting.
    theme: view.lighting.enabled ? null : neutralTheme,
    materialOverrides: null,
    quality: view.lighting.enabled ? resolveRenderQuality(view.lighting.quality)
      : resolveSceneQuality(quality, { fallback: SCENE_QUALITY.INTERACTIVE }),
    camera: cameraSettings,
    display: resolvedDisplay
  };
}
