import {
  CAMERA_PROJECTION,
  normalizeCameraSpec
} from "./camera.js";
import {
  CAD_DISPLAY_MODE,
  CAD_PART_COLOR_MODE,
  normalizePartColorSettings,
  normalizeDisplaySettings
} from "./displaySettings.js";
import { PHOTOGRAPHIC_STUDIO_MATERIAL_SETTINGS } from "./photographicStudioRig.js";
import {
  cloneThemePresetSettings,
  normalizeThemeSettings
} from "./themeSettings.js";
import { RENDER_FLOOR_PLACEMENT, resolveViewSettings } from "./viewSettings.js";

const SCENE_APPEARANCE = Object.freeze({
  SYSTEM: "system",
  LIGHT: "light",
  DARK: "dark"
});

// The quality ladder and the lighting and backdrop defaults are the Render contract the viewer's
// settings and a snapshot job share. Keep them exported and frozen.
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
    idlePixelRatioCap: 1.5,
    renderScale: 1,
    shadowMapSize: 2048,
    environmentMapSize: 256
  }),
  Object.freeze({
    id: SCENE_QUALITY.STANDARD,
    label: "Standard",
    idlePixelRatioCap: 2,
    renderScale: 1,
    shadowMapSize: 2048,
    environmentMapSize: 256
  }),
  Object.freeze({
    id: SCENE_QUALITY.HIGH,
    label: "High",
    idlePixelRatioCap: 2,
    renderScale: 2,
    shadowMapSize: 4096,
    environmentMapSize: 512
  })
]);

const RENDER_QUALITY_BY_ID = new Map(RENDER_QUALITY_PRESETS.map((preset) => [preset.id, preset]));
const SCENE_QUALITY_BY_ID = new Map(SCENE_QUALITY_PRESETS.map((preset) => [preset.id, preset]));

export const DEFAULT_RENDER_LIGHTING = Object.freeze({
  rotation: 0,
  size: 1,
  fill: 0.25
});

// Render's floor stands at the model's lowest point, as Preview's does (`RENDER_FLOOR_PLACEMENT`),
// following the current model bounds; "origin" pins it to the authored Z=0 plane instead, its
// opacity letting geometry below that plane remain visible.
export const DEFAULT_RENDER_BACKDROP = Object.freeze({
  transparent: false,
  ground: true,
  groundPlacement: RENDER_FLOOR_PLACEMENT,
  groundOpacity: 0.6,
  groundFinish: "matte"
});

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
 * what the file authored. The viewer's viewport and the parity page's headless stage both
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
 * Public grouped preset policy; historical display modes are draw details. `preview` asks for
 * Preview's photographic look (Render) over the same display, with Preview's own settings
 * (`previewSettings`). No file is in Render.
 */
export function resolveViewSceneSettings({
  display = {}, appearance = "light", prefersDark = false, camera = null, quality = null,
  lightingQuality = "final", features = undefined, preview = false, previewSettings = {}
} = {}) {
  const view = resolveViewSettings(display ?? {}, {
    appearance: normalizeSceneAppearance(appearance, { prefersDark }), lightingQuality, features, preview, previewSettings
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
      groundOpacity: view.floor.opacity,
      groundFinish: view.floor.finish
    },
    camera: cameraSettings
  } : null;
  return {
    view,
    appearance: view.appearance,
    render: { enabled, configuration },
    // A floor or custom background does not opt the model into studio lighting.
    theme: view.lighting.enabled ? null : neutralTheme,
    materialOverrides: null,
    quality: view.lighting.enabled ? resolveRenderQuality(view.lighting.quality)
      : resolveSceneQuality(quality, { fallback: SCENE_QUALITY.INTERACTIVE }),
    camera: cameraSettings,
    display: resolvedDisplay
  };
}
