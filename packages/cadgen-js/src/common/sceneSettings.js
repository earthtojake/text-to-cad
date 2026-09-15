import {
  CAMERA_PROJECTION,
  normalizeCameraSpec
} from "./camera.js";
import {
  CAD_DISPLAY_MODE,
  CAD_PART_COLOR_MODE,
  DEFAULT_DISPLAY_SETTINGS,
  DISABLED_DISPLAY_EDGE_SETTINGS,
  DISABLED_DISPLAY_GUIDE_SETTINGS,
  normalizePartColorSettings,
  normalizeDisplaySettings,
  validateDisplaySettings
} from "./displaySettings.js";
import {
  cloneThemePresetSettings,
  normalizeThemeSettings
} from "./themeSettings.js";

export const SCENE_APPEARANCE = Object.freeze({
  SYSTEM: "system",
  LIGHT: "light",
  DARK: "dark"
});

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

export const SCENE_QUALITY_PRESETS = Object.freeze([
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
  "backdrop",
  "camera"
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
  "groundPlacement"
]);

const RENDER_STUDIO_IDS = new Set(RENDER_STUDIO_PRESETS.map((preset) => preset.id));
const RENDER_QUALITY_BY_ID = new Map(RENDER_QUALITY_PRESETS.map((preset) => [preset.id, preset]));
const SCENE_QUALITY_BY_ID = new Map(SCENE_QUALITY_PRESETS.map((preset) => [preset.id, preset]));

export const DEFAULT_RENDER_LIGHTING = Object.freeze({
  rotation: 0,
  size: 1,
  fill: 0.25
});

export const DEFAULT_RENDER_BACKDROP = Object.freeze({
  transparent: false,
  ground: true,
  groundPlacement: "origin"
});

const STUDIO_BACKDROP_COLORS = Object.freeze({
  [RENDER_STUDIO.LIGHT]: "#e7e7e5",
  [RENDER_STUDIO.DARK]: "#121315"
});

const STUDIO_MATERIAL_SETTINGS = Object.freeze({
  defaultColor: "#b9bdc3",
  fillColors: Object.freeze(["#b9bdc3"]),
  cycleColors: false,
  overrideSourceColors: false,
  tintMode: "blend",
  tintStrength: 0,
  saturation: 1,
  contrast: 1,
  brightness: 1,
  roughness: 0.42,
  metalness: 0.03,
  clearcoat: 0,
  clearcoatRoughness: 0.26,
  opacity: 1,
  envMapIntensity: 1,
  emissiveIntensity: 0
});

const EXPLICIT_PBR_MATERIAL_KEYS = Object.freeze([
  "roughness",
  "metalness",
  "clearcoat",
  "clearcoatRoughness"
]);
const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}){1,2}$/;

const DEFAULT_NORMAL_CAMERA = Object.freeze({
  preset: "iso",
  projection: CAMERA_PROJECTION.ORTHOGRAPHIC
});

const DEFAULT_RENDER_CAMERA = Object.freeze({
  preset: "iso",
  projection: CAMERA_PROJECTION.PERSPECTIVE,
  focalLength: 50
});

export const DEFAULT_RENDER_DISPLAY_SETTINGS = Object.freeze({
  ...DEFAULT_DISPLAY_SETTINGS,
  mode: CAD_DISPLAY_MODE.SHADED,
  edges: DISABLED_DISPLAY_EDGE_SETTINGS,
  guides: DISABLED_DISPLAY_GUIDE_SETTINGS
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
  if (Object.hasOwn(value, "transparent")) validateBoolean(value.transparent, "render.backdrop.transparent");
  if (Object.hasOwn(value, "ground")) validateBoolean(value.ground, "render.backdrop.ground");
  if (Object.hasOwn(value, "groundPlacement") && !["origin", "lowest"].includes(value.groundPlacement)) {
    throw new Error("render.backdrop.groundPlacement must be origin or lowest");
  }
}

export function normalizeSceneAppearance(value = SCENE_APPEARANCE.SYSTEM, {
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

export function normalizeRenderStudioId(value) {
  if (typeof value !== "string" || !RENDER_STUDIO_IDS.has(value)) {
    throw new Error(`Unknown render studio '${value}'. Expected one of: ${[...RENDER_STUDIO_IDS].join(", ")}`);
  }
  return value;
}

export function normalizeRenderQuality(value = RENDER_QUALITY.FINAL) {
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
  if (Object.prototype.hasOwnProperty.call(render, "camera")) {
    normalizeCameraSpec(render.camera, {
      strict: true,
      defaultProjection: CAMERA_PROJECTION.PERSPECTIVE
    });
    result.camera = cloneValue(render.camera);
  }
  return result;
}

export function resolveRenderConfiguration(render = {}, appearance = SCENE_APPEARANCE.LIGHT) {
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
      groundPlacement: payload.backdrop?.groundPlacement ?? DEFAULT_RENDER_BACKDROP.groundPlacement
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

function normalSettings(appearance) {
  return normalizeThemeSettings(cloneThemePresetSettings(
    appearance === SCENE_APPEARANCE.DARK ? "workbench-dark" : "workbench-light"
  ));
}

function photographicRenderSettings(configuration) {
  const backgroundColor = configuration.backdrop.color;
  const settings = normalizeThemeSettings({
    materials: STUDIO_MATERIAL_SETTINGS,
    background: {
      type: configuration.backdrop.transparent ? "transparent" : "solid",
      solidColor: backgroundColor,
      linearStart: backgroundColor,
      linearEnd: backgroundColor,
      radialInner: backgroundColor,
      radialOuter: backgroundColor
    },
    // The photographic studio helper owns its physical ground. Keeping the
    // legacy stage disabled prevents a second floor or shadow catcher.
    floor: { mode: "none", enabled: false, followModel: false, color: backgroundColor },
    environment: {
      enabled: true,
      presetId: "photographic-softbox",
      intensity: 1,
      rotationY: 0,
      useAsBackground: false
    },
    // The helper owns the one logical softbox and neutral exposure. Disable every
    // legacy light so generic consumers cannot accidentally double the energy.
    lighting: {
      toneMappingExposure: 2 ** configuration.exposure,
      directional: { enabled: false, intensity: 0 },
      fill: { enabled: false, intensity: 0 },
      rim: { enabled: false, intensity: 0 },
      spot: { enabled: false, intensity: 0 },
      point: { enabled: false, intensity: 0 },
      ambient: { enabled: false, intensity: 0 },
      hemisphere: { enabled: false, intensity: 0 }
    }
  });
  return {
    ...publicRenderSettings(settings),
    renderer: {
      toneMapping: "neutral",
      exposure: configuration.exposure
    }
  };
}

function publicRenderSettings(settings) {
  const normalized = normalizeThemeSettings(settings);
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

function applyPartColor(settings, partColor) {
  return {
    ...settings,
    materials: resolveDisplayMaterialSettings(settings.materials, partColor)
  };
}

function explicitMaterialOverrides(settings = {}) {
  const materials = isPlainObject(settings.materials) ? settings.materials : {};
  return Object.fromEntries(EXPLICIT_PBR_MATERIAL_KEYS
    .filter((key) => Object.prototype.hasOwnProperty.call(materials, key))
    .map((key) => [key, Number(materials[key])]));
}

/**
 * Resolve shared viewer/snapshot scene policy without retaining app state.
 * Top-level camera/display/quality belong to normal CAD. A Render envelope is
 * an isolated photographic scene and resolves only its own camera and quality.
 */
export function resolveSceneSettings({
  appearance = SCENE_APPEARANCE.SYSTEM,
  prefersDark = false,
  render = null,
  quality = null,
  camera = null,
  display = null
} = {}) {
  const baseAppearance = normalizeSceneAppearance(appearance, { prefersDark });
  if (render == null) {
    const resolvedDisplay = resolveDisplay(DEFAULT_DISPLAY_SETTINGS, display);
    const settings = applyPartColor(publicRenderSettings(normalSettings(baseAppearance)), resolvedDisplay.partColor);
    return {
      appearance: baseAppearance,
      render: {
        enabled: false,
        studio: null,
        settings,
        // CAD is an inspection view with no reflection environment. Keep the
        // authored albedo and opacity, but use the workbench's matte PBR
        // channels so authored metals do not collapse to near-black.
        materialOverrides: explicitMaterialOverrides(settings),
        payload: null
      },
      quality: resolveSceneQuality(quality, { fallback: SCENE_QUALITY.INTERACTIVE }),
      camera: resolveCamera(DEFAULT_NORMAL_CAMERA, camera),
      display: resolvedDisplay
    };
  }

  const payload = normalizeRenderPayload(render);
  const configuration = resolveRenderConfiguration(payload, baseAppearance);
  // Render is an isolated photographic scene. CAD inspection camera, quality,
  // clipping, exploded view, guides, edges, and part-colour state do not leak
  // across the mode boundary.
  const resolvedDisplay = resolveDisplay(DEFAULT_RENDER_DISPLAY_SETTINGS);
  const settings = applyPartColor(photographicRenderSettings(configuration), resolvedDisplay.partColor);
  return {
    appearance: baseAppearance,
    render: {
      enabled: true,
      configuration,
      settings,
      materialOverrides: {},
      payload
    },
    quality: resolveRenderQuality(configuration.quality),
    camera: resolveCamera(DEFAULT_RENDER_CAMERA, payload.camera),
    display: resolvedDisplay
  };
}
