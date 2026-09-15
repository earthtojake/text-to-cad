import {
  CAMERA_PROJECTION,
  DEFAULT_DISPLAY_EDGE_SETTINGS,
  DISABLED_DISPLAY_EDGE_SETTINGS
} from "./displaySettings.js";

export {
  CAD_EDGE_CLASS_IDS,
  CAD_EDGE_COLOR,
  CAD_EDGE_HIGHLIGHT_COLOR,
  CAMERA_PROJECTION,
  normalizeCameraProjection
} from "./displaySettings.js";

const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}){1,2}$/;
export const MAX_THEME_FILL_COLORS = 50;
const CAD_THEME_EDGE_SETTINGS = DEFAULT_DISPLAY_EDGE_SETTINGS;
const DISABLED_THEME_EDGE_SETTINGS = DISABLED_DISPLAY_EDGE_SETTINGS;

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function normalizeNumber(value, fallback, min = -Infinity, max = Infinity) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return fallback;
  }
  return clamp(numericValue, min, max);
}

function normalizeColor(value, fallback) {
  const normalized = String(value || "").trim();
  if (!HEX_COLOR_PATTERN.test(normalized)) {
    return fallback;
  }
  return normalized.length === 4
    ? `#${normalized[1]}${normalized[1]}${normalized[2]}${normalized[2]}${normalized[3]}${normalized[3]}`.toLowerCase()
    : normalized.toLowerCase();
}

export function normalizeThemeFillColors(value, fallback = DEFAULT_THEME_SETTINGS?.materials?.defaultColor || "#ffffff") {
  const values = Array.isArray(value) ? value : [value];
  const fillColors = values
    .map((entry) => normalizeColor(entry, ""))
    .filter(Boolean)
    .slice(0, MAX_THEME_FILL_COLORS);
  if (fillColors.length) {
    return fillColors;
  }
  return [normalizeColor(fallback, "#ffffff")];
}

export function resolveThemeFillColor(materials = {}, index = 0) {
  const fillColors = normalizeThemeFillColors(
    materials.fillColors,
    materials.defaultColor || DEFAULT_THEME_SETTINGS?.materials?.defaultColor || "#ffffff"
  );
  const cycleColors = normalizeBoolean(
    materials.cycleColors,
    DEFAULT_THEME_SETTINGS?.materials?.cycleColors || false
  );
  const colorIndex = cycleColors ? Math.max(Math.floor(Number(index) || 0), 0) % fillColors.length : 0;
  return fillColors[colorIndex];
}

function hexColorToLinearRgb(value, fallback = "#000000") {
  const hex = normalizeColor(value, fallback);
  const expanded = hex.length === 4
    ? `#${hex[1]}${hex[1]}${hex[2]}${hex[2]}${hex[3]}${hex[3]}`
    : hex;
  const channel = (offset) => {
    const srgb = parseInt(expanded.slice(offset, offset + 2), 16) / 255;
    return srgb <= 0.03928
      ? srgb / 12.92
      : ((srgb + 0.055) / 1.055) ** 2.4;
  };
  return {
    r: channel(1),
    g: channel(3),
    b: channel(5)
  };
}

function relativeLuminance(value, fallback = "#000000") {
  const rgb = hexColorToLinearRgb(value, fallback);
  return (0.2126 * rgb.r) + (0.7152 * rgb.g) + (0.0722 * rgb.b);
}

function normalizeBoolean(value, fallback = false) {
  if (typeof value === "boolean") {
    return value;
  }
  return fallback;
}

function normalizeBackgroundType(value, fallback = "solid") {
  const normalized = String(value || "").trim().toLowerCase();
  return ["solid", "linear", "radial", "transparent"].includes(normalized)
    ? normalized
    : fallback;
}

function normalizeMaterialTintMode(value, fallback = "multiply") {
  const normalized = String(value || "").trim().toLowerCase();
  return ["multiply", "blend"].includes(normalized)
    ? normalized
    : fallback;
}

export const THEME_FLOOR_MODES = Object.freeze({
  STAGE: "stage",
  GRID: "grid",
  NONE: "none"
});

export const THEME_COLOR_MODES = Object.freeze({
  SYSTEM: "system",
  LIGHT: "light",
  DARK: "dark"
});

const THEME_COLOR_MODE_VALUES = Object.freeze(Object.values(THEME_COLOR_MODES));

function normalizeThemeColorMode(value, fallback = THEME_COLOR_MODES.SYSTEM) {
  const normalized = String(value || "").trim().toLowerCase();
  return THEME_COLOR_MODE_VALUES.includes(normalized) ? normalized : fallback;
}

const THEME_MODE_COLOR_PATHS = Object.freeze([
  Object.freeze(["background", "solidColor"]),
  Object.freeze(["background", "linearStart"]),
  Object.freeze(["background", "linearEnd"]),
  Object.freeze(["background", "radialInner"]),
  Object.freeze(["background", "radialOuter"]),
  Object.freeze(["floor", "color"]),
  Object.freeze(["lighting", "directional", "color"]),
  Object.freeze(["lighting", "spot", "color"]),
  Object.freeze(["lighting", "point", "color"]),
  Object.freeze(["lighting", "ambient", "color"]),
  Object.freeze(["lighting", "hemisphere", "skyColor"]),
  Object.freeze(["lighting", "hemisphere", "groundColor"])
]);

function getPathValue(source, path) {
  return path.reduce((value, key) => (
    value && typeof value === "object" ? value[key] : undefined
  ), source);
}

function setPathValue(target, path, value) {
  let cursor = target;
  for (let index = 0; index < path.length - 1; index += 1) {
    const key = path[index];
    if (!cursor[key] || typeof cursor[key] !== "object" || Array.isArray(cursor[key])) {
      cursor[key] = {};
    }
    cursor = cursor[key];
  }
  cursor[path[path.length - 1]] = value;
}

function deepClone(value) {
  return JSON.parse(JSON.stringify(value));
}

function createThemeModeColorOverridesFromSettings(settings = {}, fallbackSettings = settings) {
  const result = {};
  for (const path of THEME_MODE_COLOR_PATHS) {
    const fallback = getPathValue(fallbackSettings, path) || "#ffffff";
    setPathValue(result, path, normalizeColor(getPathValue(settings, path), fallback));
  }
  return result;
}

function createThemeModeColors(lightSettings = {}, darkSettings = lightSettings) {
  return Object.freeze({
    light: createThemeModeColorOverridesFromSettings(lightSettings, lightSettings),
    dark: createThemeModeColorOverridesFromSettings(darkSettings, lightSettings)
  });
}

function withThemeColorMode(settings, colorMode, modeColors = createThemeModeColors(settings, settings)) {
  return Object.freeze({
    ...settings,
    colorMode: normalizeThemeColorMode(colorMode),
    modeColors
  });
}

function normalizeThemeModeColors(value = {}, fallbackSettings = DEFAULT_THEME_SETTINGS) {
  const source = value && typeof value === "object" ? value : {};
  const fallback = fallbackSettings && typeof fallbackSettings === "object"
    ? fallbackSettings
    : DEFAULT_THEME_SETTINGS;
  const fallbackModeColors = fallback?.modeColors && typeof fallback.modeColors === "object"
    ? fallback.modeColors
    : createThemeModeColors(fallback, fallback);
  return {
    light: createThemeModeColorOverridesFromSettings(source.light, fallbackModeColors.light || fallback),
    dark: createThemeModeColorOverridesFromSettings(source.dark, fallbackModeColors.dark || fallback)
  };
}

function applyThemeModeColorOverrides(target, overrides = {}) {
  for (const path of THEME_MODE_COLOR_PATHS) {
    const value = getPathValue(overrides, path);
    if (value) {
      setPathValue(target, path, value);
    }
  }
}

export const MIN_FLOOR_GRID_DENSITY = 0.25;
export const MAX_FLOOR_GRID_DENSITY = 4;
// The vertical line through the world origin, running the full height of the
// scene in both directions -- up from the floor and down through it. A ground
// grid says where the floor is; this says where 0,0 is on it, which is what you
// actually align parts against. It has no length setting: it is meant to read as
// an infinite construction line, so it is sized off the scene radius to always
// leave frame.
export const DEFAULT_FLOOR_AXIS_SETTINGS = Object.freeze({
  enabled: false,
  color: "#6b7280",
  opacity: 0.5
});
// Half-length as a multiple of scene radius. Large enough to exit any sane
// framing; the camera's far plane trims the rest, which is what makes it read as
// unbounded rather than as a very tall stick.
export const FLOOR_AXIS_RADIUS_MULTIPLE = 1000;

export const DEFAULT_FLOOR_GRID_SETTINGS = Object.freeze({
  enabled: true,
  centerColor: "#6b7280",
  cellColor: "#cbd5e1",
  opacity: 0.18,
  density: 1
});

// CAD inspection's soft fill and rim directionals. Internal scene settings
// normalize absent fill/rim blocks to these structural defaults.
export const DEFAULT_FILL_LIGHT_SETTINGS = Object.freeze({
  enabled: true,
  color: "#6b7f95",
  intensity: 0.46,
  position: Object.freeze({ x: 120, y: 80, z: 210 })
});
export const DEFAULT_RIM_LIGHT_SETTINGS = Object.freeze({
  enabled: true,
  color: "#6db6e8",
  intensity: 0.04,
  position: Object.freeze({ x: -260, y: 240, z: 180 })
});

function normalizeFloorMode(value, fallback = THEME_FLOOR_MODES.STAGE) {
  const normalized = String(value || "").trim().toLowerCase();
  return Object.values(THEME_FLOOR_MODES).includes(normalized)
    ? normalized
    : fallback;
}

export const ENVIRONMENT_PRESETS = Object.freeze([
  {
    id: "studio-softbox",
    label: "Studio softbox",
    kind: "procedural",
    url: ""
  },
  {
    id: "studio-hdri-43",
    label: "Studio HDRI 43",
    url: "https://static.morflax.com/textures/env/Studio_HDRI_43.jpg"
  },
  {
    id: "studio-hdri-41",
    label: "Studio HDRI 41",
    url: "https://static.morflax.com/textures/env/Studio_HDRI_41.jpg"
  },
  {
    id: "studio-hdri-12",
    label: "Studio HDRI 12",
    url: "https://static.morflax.com/textures/env/Studio_HDRI_12.jpg"
  },
  {
    id: "studio-hdri-17",
    label: "Studio HDRI 17",
    url: "https://static.morflax.com/textures/env/Studio_HDRI_17.jpg"
  },
  {
    id: "studio-hdri-22",
    label: "Studio HDRI 22",
    url: "https://static.morflax.com/textures/env/Studio_HDRI_22.jpg"
  }
]);

const WORKBENCH_FILL_COLORS = Object.freeze([
  "#b6c4ce",
  "#f4a7a7",
  "#f8c77e",
  "#f7e38d",
  "#b9e88f",
  "#8fe3c0",
  "#92d7f5",
  "#a9b8ff",
  "#c7a8ff",
  "#f2a7d9"
]);

function mixHexColors(colorA, colorB, amount = 0.5) {
  const from = normalizeColor(colorA, "#000000");
  const to = normalizeColor(colorB, from);
  const clampedAmount = clamp(Number(amount), 0, 1);
  const channel = (offset) => {
    const fromChannel = parseInt(from.slice(offset, offset + 2), 16);
    const toChannel = parseInt(to.slice(offset, offset + 2), 16);
    return Math.round(fromChannel + ((toChannel - fromChannel) * clampedAmount))
      .toString(16)
      .padStart(2, "0");
  };
  return `#${channel(1)}${channel(3)}${channel(5)}`;
}

function createFloorAxisSettings(floorColor, options = {}) {
  const normalizedFloorColor = normalizeColor(floorColor, "#f1f5f9");
  const lightFloor = relativeLuminance(normalizedFloorColor) >= 0.36;
  return {
    axis: {
      enabled: normalizeBoolean(options.enabled, false),
      color: normalizeColor(
        options.color,
        lightFloor
          ? mixHexColors(normalizedFloorColor, "#0f172a", 0.62)
          : mixHexColors(normalizedFloorColor, "#f8fafc", 0.58)
      ),
      opacity: normalizeNumber(options.opacity, DEFAULT_FLOOR_AXIS_SETTINGS.opacity, 0, 1)
    }
  };
}

function createFloorGridSettings(floorColor, options = {}) {
  const normalizedFloorColor = normalizeColor(floorColor, "#f1f5f9");
  const enabled = normalizeBoolean(options.enabled, false);
  const lightFloor = relativeLuminance(normalizedFloorColor) >= 0.36;
  const centerColor = normalizeColor(
    options.centerColor,
    lightFloor
      ? mixHexColors(normalizedFloorColor, "#0f172a", 0.48)
      : mixHexColors(normalizedFloorColor, "#f8fafc", 0.46)
  );
  const cellColor = normalizeColor(
    options.cellColor,
    lightFloor
      ? mixHexColors(normalizedFloorColor, "#475569", 0.26)
      : mixHexColors(normalizedFloorColor, "#cbd5e1", 0.22)
  );
  const opacity = normalizeNumber(options.opacity, DEFAULT_FLOOR_GRID_SETTINGS.opacity, 0, 1);
  const density = normalizeNumber(
    options.density,
    DEFAULT_FLOOR_GRID_SETTINGS.density,
    MIN_FLOOR_GRID_DENSITY,
    MAX_FLOOR_GRID_DENSITY
  );
  return {
    grid: {
      enabled,
      centerColor,
      cellColor,
      opacity,
      density
    }
  };
}

const CINEMATIC_THEME_SETTINGS = Object.freeze({
  materials: {
    defaultColor: WORKBENCH_FILL_COLORS[0],
    fillColors: WORKBENCH_FILL_COLORS,
    cycleColors: false,
    overrideSourceColors: false,
    tintMode: "blend",
    tintStrength: 0,
    saturation: 1.18,
    contrast: 1.12,
    brightness: 1.02,
    roughness: 0.58,
    metalness: 0.02,
    clearcoat: 0.12,
    clearcoatRoughness: 0.42,
    opacity: 1,
    envMapIntensity: 0.42,
    emissiveIntensity: 0.02
  },
  background: {
    type: "linear",
    solidColor: "#edf5fb",
    linearStart: "#fbfdff",
    linearEnd: "#b8cadb",
    linearAngle: 135,
    radialInner: "#ffffff",
    radialOuter: "#b3c4d4"
  },
  floor: {
    mode: THEME_FLOOR_MODES.STAGE,
    color: "#edf3f8",
    roughness: 0.7,
    reflectivity: 0.14,
    shadowOpacity: 0.16,
    horizonBlend: 0.18,
    ...createFloorGridSettings("#edf3f8", { opacity: 0.2 }),
    enabled: false
  },
  environment: {
    enabled: true,
    presetId: "studio-hdri-43",
    intensity: 0.32,
    rotationY: -0.25,
    useAsBackground: false
  },
  lighting: {
    toneMappingExposure: 1.16,
    directional: {
      enabled: true,
      color: "#ffffff",
      intensity: 1.16,
      position: {
        x: -210,
        y: 260,
        z: 270
      }
    },
    spot: {
      enabled: true,
      color: "#f4fbff",
      intensity: 0.52,
      angle: 0.74,
      distance: 0,
      position: {
        x: 190,
        y: 210,
        z: 170
      }
    },
    point: {
      enabled: true,
      color: "#ffe2ba",
      intensity: 0.28,
      distance: 0,
      position: {
        x: -240,
        y: 110,
        z: -210
      }
    },
    ambient: {
      enabled: true,
      color: "#ffffff",
      intensity: 0.4
    },
    hemisphere: {
      enabled: true,
      skyColor: "#ffffff",
      groundColor: "#d6e2ee",
      intensity: 1.12
    }
  }
});

// Workbench light mode counterpart to the dark treatment below: the canvas
// sits a few steps below pure white and the floor a step below that, so
// white parts (which light toward pure white under the shared exposure)
// keep a silhouette and the horizon reads as an intentional stage break.
// The deeper hemisphere ground keeps shading gradation on white undersides.
const WORKBENCH_LIGHT_CANVAS_COLOR = "#f0f4f9";
const WORKBENCH_LIGHT_FLOOR_COLOR = "#e2e9f0";

const WORKBENCH_BASE_THEME_SETTINGS = Object.freeze({
  ...CINEMATIC_THEME_SETTINGS,
  projection: CAMERA_PROJECTION.ORTHOGRAPHIC,
  background: {
    ...CINEMATIC_THEME_SETTINGS.background,
    type: "solid",
    solidColor: WORKBENCH_LIGHT_CANVAS_COLOR,
    linearStart: WORKBENCH_LIGHT_CANVAS_COLOR,
    linearEnd: WORKBENCH_LIGHT_CANVAS_COLOR,
    radialInner: WORKBENCH_LIGHT_CANVAS_COLOR,
    radialOuter: WORKBENCH_LIGHT_CANVAS_COLOR
  },
  // Workbench is a clean engineering canvas: no stage floor plane, but a faint
  // ground grid and a line up the origin give parts something to read position
  // against. Both are deliberately low-contrast so they sit under the model
  // rather than competing with it.
  floor: {
    ...CINEMATIC_THEME_SETTINGS.floor,
    color: WORKBENCH_LIGHT_FLOOR_COLOR,
    enabled: false,
    ...createFloorGridSettings(WORKBENCH_LIGHT_FLOOR_COLOR, { enabled: true, opacity: 0.16 }),
    ...createFloorAxisSettings(WORKBENCH_LIGHT_FLOOR_COLOR, { enabled: true, opacity: 0.28 })
  },
  environment: {
    ...CINEMATIC_THEME_SETTINGS.environment,
    enabled: false
  },
  lighting: {
    ...CINEMATIC_THEME_SETTINGS.lighting,
    hemisphere: {
      ...CINEMATIC_THEME_SETTINGS.lighting.hemisphere,
      groundColor: "#c7d5e3"
    }
  }
});

// Inspect appearance changes the canvas and guide contrast, never the model's
// materials or illumination. Both presets inherit the same workbench rig.
const WORKBENCH_DARK_FLOOR_COLOR = "#383838";

const WORKBENCH_DARK_THEME_SETTINGS = Object.freeze({
  ...WORKBENCH_BASE_THEME_SETTINGS,
  background: {
    ...WORKBENCH_BASE_THEME_SETTINGS.background,
    solidColor: "#333333",
    linearStart: "#3b3b3b",
    linearEnd: "#2b2b2b",
    radialInner: "#404040",
    radialOuter: "#2b2b2b"
  },
  floor: {
    ...WORKBENCH_BASE_THEME_SETTINGS.floor,
    color: WORKBENCH_DARK_FLOOR_COLOR,
    ...createFloorGridSettings(WORKBENCH_DARK_FLOOR_COLOR, { enabled: true, opacity: 0.16 }),
    ...createFloorAxisSettings(WORKBENCH_DARK_FLOOR_COLOR, { enabled: true, opacity: 0.28 })
  }
});

// Workbench ships as two distinct, single-palette themes (light + dark) rather
// than one system-adaptive theme. App light/dark is inferred from the active
// theme's background, so each Workbench variant is pinned to its own palette.
const WORKBENCH_LIGHT_THEME_PRESET_SETTINGS = withThemeColorMode(
  WORKBENCH_BASE_THEME_SETTINGS,
  THEME_COLOR_MODES.LIGHT
);
// Dark changes only the canvas/floor colors of the shared Workbench rig.
const WORKBENCH_DARK_BAKED_SETTINGS = deepClone(WORKBENCH_BASE_THEME_SETTINGS);
applyThemeModeColorOverrides(
  WORKBENCH_DARK_BAKED_SETTINGS,
  createThemeModeColors(WORKBENCH_BASE_THEME_SETTINGS, WORKBENCH_DARK_THEME_SETTINGS).dark
);
const WORKBENCH_DARK_THEME_PRESET_SETTINGS = withThemeColorMode(
  WORKBENCH_DARK_BAKED_SETTINGS,
  THEME_COLOR_MODES.DARK
);

export const THEME_PRESETS = Object.freeze([
  {
    id: "workbench-light",
    label: "Light",
    preview: {
      background: "#f0f4f9",
      modelColor: "#b6c4ce"
    },
    settings: WORKBENCH_LIGHT_THEME_PRESET_SETTINGS
  },
  {
    id: "workbench-dark",
    label: "Dark",
    preview: {
      background: "#333333",
      modelColor: "#b6c4ce"
    },
    settings: WORKBENCH_DARK_THEME_PRESET_SETTINGS
  }
]);

// --- render-only themes -------------------------------------------------------------
// Themes that exist for HEADLESS SNAPSHOTS and are deliberately absent from THEME_PRESETS,
// which is what the viewer's theme picker lists. A snapshot is usually read by an agent
// rather than looked at by a person, and the two want different things from a scene.
//
// Workbench gives a part "something to read position against": a faint ground grid and a
// line up the origin. In the viewport that is orientation you can ignore. In a still image
// it is geometry-shaped contrast that is not geometry -- straight lines crossing the model
// and the background, at the same low contrast as a real silhouette edge, with nothing
// (motion, interaction, the rest of the UI) to say otherwise. Everything else is inherited
// from Workbench Light unchanged, so a part's colour, material and lighting read exactly as
// they do in the viewer; only the furniture that is not the model is removed.
export const SNAPSHOT_THEME_ID = "snapshot";

const SNAPSHOT_THEME_SETTINGS = Object.freeze({
  ...WORKBENCH_LIGHT_THEME_PRESET_SETTINGS,
  floor: {
    ...WORKBENCH_LIGHT_THEME_PRESET_SETTINGS.floor,
    // Stated, not inherited. Workbench already disables the floor plane, so nothing
    // catches a shadow and this is inert today -- but "a snapshot casts no shadow" is a
    // property of THIS theme, and a theme that holds it only by accident of another
    // setting loses it silently the moment that setting changes.
    shadowOpacity: 0,
    ...createFloorGridSettings(WORKBENCH_LIGHT_FLOOR_COLOR, { enabled: false, opacity: 0 }),
    ...createFloorAxisSettings(WORKBENCH_LIGHT_FLOOR_COLOR, { enabled: false, opacity: 0 })
  }
});

const SNAPSHOT_THEME_PRESET = Object.freeze({
  id: SNAPSHOT_THEME_ID,
  label: "Snapshot",
  preview: {
    background: "#f0f4f9",
    modelColor: "#b6c4ce"
  },
  settings: SNAPSHOT_THEME_SETTINGS
});

// Resolvable by id, never offered in the picker. getThemePresetById consults this AFTER
// THEME_PRESETS, so a render can name it and the viewer cannot land on it by accident.
export const RENDER_ONLY_THEME_PRESETS = Object.freeze([SNAPSHOT_THEME_PRESET]);

export const DEFAULT_THEME_PRESET_ID = "workbench-light";

// The two ids that are not presets. "system" follows prefers-color-scheme;
// "custom" is the single slot holding whatever the user has edited. Everything
// else is a built-in preset, and presets are read-only.
export const SYSTEM_THEME_ID = "system";
export const CUSTOM_THEME_ID = "custom";
export const DEFAULT_THEME_ID = SYSTEM_THEME_ID;

export const DEFAULT_THEME_PRESET = Object.freeze(
  THEME_PRESETS.find((preset) => preset.id === DEFAULT_THEME_PRESET_ID) || THEME_PRESETS[0]
);

export const DEFAULT_THEME_SETTINGS = Object.freeze(DEFAULT_THEME_PRESET.settings);

export function resolveSystemThemePresetId({ prefersDark = false } = {}) {
  return prefersDark === true ? "workbench-dark" : "workbench-light";
}

// The id the UI shows as selected, and the only ids that may be stored.
export function normalizeThemeId(themeId) {
  const normalized = String(themeId || "").trim();
  if (normalized === SYSTEM_THEME_ID || normalized === CUSTOM_THEME_ID) {
    return normalized;
  }
  return normalizeThemePresetId(normalized);
}

// Resolve an active theme id to the settings it renders with. "custom" uses the
// stored custom settings; "system" and presets resolve to preset settings, which
// is why selecting a preset is all it takes to reset a customized theme.
export function resolveThemeSettingsForId(themeId, { custom = null, prefersDark = false } = {}) {
  const normalizedThemeId = normalizeThemeId(themeId) || DEFAULT_THEME_ID;
  if (normalizedThemeId === CUSTOM_THEME_ID && custom) {
    return normalizeThemeSettings(custom);
  }
  const presetId = normalizedThemeId === CUSTOM_THEME_ID || normalizedThemeId === SYSTEM_THEME_ID
    ? resolveSystemThemePresetId({ prefersDark })
    : normalizedThemeId;
  return cloneThemePresetSettings(presetId);
}

const PRESET_ID_SET = new Set(ENVIRONMENT_PRESETS.map((preset) => preset.id));

function normalizeEnvironmentPresetId(value) {
  const normalized = String(value || "").trim();
  if (PRESET_ID_SET.has(normalized)) {
    return normalized;
  }
  return DEFAULT_THEME_SETTINGS.environment.presetId;
}

function normalizePosition(value, fallback) {
  return {
    x: normalizeNumber(value?.x, fallback.x, -5000, 5000),
    y: normalizeNumber(value?.y, fallback.y, -5000, 5000),
    z: normalizeNumber(value?.z, fallback.z, -5000, 5000)
  };
}

function createThemeSettingsSignature(value = {}) {
  return JSON.stringify({
    colorMode: value?.colorMode || THEME_COLOR_MODES.SYSTEM,
    modeColors: value?.modeColors || {},
    materials: value?.materials || {},
    background: value?.background || {},
    floor: value?.floor || {},
    environment: value?.environment || {},
    lighting: value?.lighting || {}
  });
}

export function normalizeThemeSettings(value = {}) {
  const source = value && typeof value === "object" ? value : {};
  const materials = source.materials && typeof source.materials === "object"
    ? source.materials
    : {};
  const background = source.background && typeof source.background === "object"
    ? source.background
    : {};
  const environment = source.environment && typeof source.environment === "object"
    ? source.environment
    : {};
  const floor = source.floor && typeof source.floor === "object"
    ? source.floor
    : {};
  const lighting = source.lighting && typeof source.lighting === "object"
    ? source.lighting
    : {};
  const normalizedDefaultColor = normalizeColor(
    materials.defaultColor,
    DEFAULT_THEME_SETTINGS.materials.defaultColor
  );
  const fillColors = normalizeThemeFillColors(materials.fillColors, normalizedDefaultColor);
  const normalizedFloorColor = normalizeColor(floor.color, DEFAULT_THEME_SETTINGS.floor?.color || "#141416");
  const normalizedFloorMode = normalizeFloorMode(floor.mode, DEFAULT_THEME_SETTINGS.floor?.mode || THEME_FLOOR_MODES.STAGE);
  const colorMode = normalizeThemeColorMode(
    source.colorMode,
    DEFAULT_THEME_SETTINGS?.colorMode || THEME_COLOR_MODES.SYSTEM
  );

  const normalized = {
    colorMode,
    materials: {
      defaultColor: fillColors[0] || normalizedDefaultColor,
      fillColors,
      cycleColors: normalizeBoolean(
        materials.cycleColors,
        DEFAULT_THEME_SETTINGS.materials.cycleColors || false
      ),
      overrideSourceColors: normalizeBoolean(
        materials.overrideSourceColors,
        DEFAULT_THEME_SETTINGS.materials.overrideSourceColors || false
      ),
      tintMode: normalizeMaterialTintMode(
        materials.tintMode,
        DEFAULT_THEME_SETTINGS.materials.tintMode
      ),
      tintStrength: normalizeNumber(materials.tintStrength, DEFAULT_THEME_SETTINGS.materials.tintStrength, 0, 1),
      saturation: normalizeNumber(materials.saturation, DEFAULT_THEME_SETTINGS.materials.saturation, 0, 2.5),
      contrast: normalizeNumber(materials.contrast, DEFAULT_THEME_SETTINGS.materials.contrast, 0, 2.5),
      brightness: normalizeNumber(materials.brightness, DEFAULT_THEME_SETTINGS.materials.brightness, 0, 2),
      roughness: normalizeNumber(materials.roughness, DEFAULT_THEME_SETTINGS.materials.roughness, 0, 1),
      metalness: normalizeNumber(materials.metalness, DEFAULT_THEME_SETTINGS.materials.metalness, 0, 1),
      clearcoat: normalizeNumber(materials.clearcoat, DEFAULT_THEME_SETTINGS.materials.clearcoat, 0, 1),
      clearcoatRoughness: normalizeNumber(
        materials.clearcoatRoughness,
        DEFAULT_THEME_SETTINGS.materials.clearcoatRoughness,
        0,
        1
      ),
      opacity: normalizeNumber(materials.opacity, DEFAULT_THEME_SETTINGS.materials.opacity, 0, 1),
      envMapIntensity: normalizeNumber(materials.envMapIntensity, DEFAULT_THEME_SETTINGS.materials.envMapIntensity, 0, 4),
      emissiveIntensity: normalizeNumber(
        materials.emissiveIntensity,
        DEFAULT_THEME_SETTINGS.materials.emissiveIntensity,
        0,
        2
      )
    },
    background: {
      type: normalizeBackgroundType(background.type, DEFAULT_THEME_SETTINGS.background.type),
      solidColor: normalizeColor(background.solidColor, DEFAULT_THEME_SETTINGS.background.solidColor),
      linearStart: normalizeColor(background.linearStart, DEFAULT_THEME_SETTINGS.background.linearStart),
      linearEnd: normalizeColor(background.linearEnd, DEFAULT_THEME_SETTINGS.background.linearEnd),
      linearAngle: normalizeNumber(background.linearAngle, DEFAULT_THEME_SETTINGS.background.linearAngle, -360, 360),
      radialInner: normalizeColor(background.radialInner, DEFAULT_THEME_SETTINGS.background.radialInner),
      radialOuter: normalizeColor(background.radialOuter, DEFAULT_THEME_SETTINGS.background.radialOuter)
    },
    floor: {
      mode: normalizedFloorMode,
      enabled: normalizeBoolean(floor.enabled, normalizedFloorMode !== THEME_FLOOR_MODES.NONE),
      // Floor-dependent placement is COUPLED to the floor: with the stage
      // floor disabled, followModel is inert (normalized false), so grid/axis
      // canvases stay pinned to world z=0 and a hidden setting can never move
      // the stage under the model. Enabling the floor re-exposes the trait.
      followModel: normalizeBoolean(floor.enabled, normalizedFloorMode !== THEME_FLOOR_MODES.NONE)
        && normalizeBoolean(floor.followModel, DEFAULT_THEME_SETTINGS.floor?.followModel ?? true),
      color: normalizedFloorColor,
      roughness: normalizeNumber(floor.roughness, DEFAULT_THEME_SETTINGS.floor?.roughness ?? 0.72, 0, 1),
      reflectivity: normalizeNumber(floor.reflectivity, DEFAULT_THEME_SETTINGS.floor?.reflectivity ?? 0.12, 0, 1),
      shadowOpacity: normalizeNumber(floor.shadowOpacity, DEFAULT_THEME_SETTINGS.floor?.shadowOpacity ?? 0.45, 0, 1),
      horizonBlend: normalizeNumber(floor.horizonBlend, DEFAULT_THEME_SETTINGS.floor?.horizonBlend ?? 0, 0, 1)
    },
    environment: {
      enabled: normalizeBoolean(environment.enabled, DEFAULT_THEME_SETTINGS.environment.enabled),
      presetId: normalizeEnvironmentPresetId(environment.presetId),
      intensity: normalizeNumber(environment.intensity, DEFAULT_THEME_SETTINGS.environment.intensity, 0, 4),
      rotationY: normalizeNumber(environment.rotationY, DEFAULT_THEME_SETTINGS.environment.rotationY, -Math.PI * 2, Math.PI * 2),
      useAsBackground: normalizeBoolean(environment.useAsBackground, DEFAULT_THEME_SETTINGS.environment.useAsBackground)
    },
    lighting: {
      toneMappingExposure: normalizeNumber(
        lighting.toneMappingExposure,
        DEFAULT_THEME_SETTINGS.lighting.toneMappingExposure,
        0.05,
        6
      ),
      directional: {
        enabled: normalizeBoolean(lighting.directional?.enabled, DEFAULT_THEME_SETTINGS.lighting.directional.enabled),
        color: normalizeColor(lighting.directional?.color, DEFAULT_THEME_SETTINGS.lighting.directional.color),
        intensity: normalizeNumber(lighting.directional?.intensity, DEFAULT_THEME_SETTINGS.lighting.directional.intensity, 0, 20),
        position: normalizePosition(lighting.directional?.position, DEFAULT_THEME_SETTINGS.lighting.directional.position)
      },
      fill: {
        enabled: normalizeBoolean(
          lighting.fill?.enabled,
          DEFAULT_THEME_SETTINGS.lighting.fill?.enabled ?? DEFAULT_FILL_LIGHT_SETTINGS.enabled
        ),
        color: normalizeColor(
          lighting.fill?.color,
          DEFAULT_THEME_SETTINGS.lighting.fill?.color || DEFAULT_FILL_LIGHT_SETTINGS.color
        ),
        intensity: normalizeNumber(
          lighting.fill?.intensity,
          DEFAULT_THEME_SETTINGS.lighting.fill?.intensity ?? DEFAULT_FILL_LIGHT_SETTINGS.intensity,
          0,
          20
        ),
        position: normalizePosition(
          lighting.fill?.position,
          DEFAULT_THEME_SETTINGS.lighting.fill?.position || DEFAULT_FILL_LIGHT_SETTINGS.position
        )
      },
      rim: {
        enabled: normalizeBoolean(
          lighting.rim?.enabled,
          DEFAULT_THEME_SETTINGS.lighting.rim?.enabled ?? DEFAULT_RIM_LIGHT_SETTINGS.enabled
        ),
        color: normalizeColor(
          lighting.rim?.color,
          DEFAULT_THEME_SETTINGS.lighting.rim?.color || DEFAULT_RIM_LIGHT_SETTINGS.color
        ),
        intensity: normalizeNumber(
          lighting.rim?.intensity,
          DEFAULT_THEME_SETTINGS.lighting.rim?.intensity ?? DEFAULT_RIM_LIGHT_SETTINGS.intensity,
          0,
          20
        ),
        position: normalizePosition(
          lighting.rim?.position,
          DEFAULT_THEME_SETTINGS.lighting.rim?.position || DEFAULT_RIM_LIGHT_SETTINGS.position
        )
      },
      spot: {
        enabled: normalizeBoolean(lighting.spot?.enabled, DEFAULT_THEME_SETTINGS.lighting.spot.enabled),
        color: normalizeColor(lighting.spot?.color, DEFAULT_THEME_SETTINGS.lighting.spot.color),
        intensity: normalizeNumber(lighting.spot?.intensity, DEFAULT_THEME_SETTINGS.lighting.spot.intensity, 0, 20),
        angle: normalizeNumber(lighting.spot?.angle, DEFAULT_THEME_SETTINGS.lighting.spot.angle, 0.01, Math.PI / 2),
        distance: normalizeNumber(lighting.spot?.distance, DEFAULT_THEME_SETTINGS.lighting.spot.distance, 0, 5000),
        position: normalizePosition(lighting.spot?.position, DEFAULT_THEME_SETTINGS.lighting.spot.position)
      },
      point: {
        enabled: normalizeBoolean(lighting.point?.enabled, DEFAULT_THEME_SETTINGS.lighting.point.enabled),
        color: normalizeColor(lighting.point?.color, DEFAULT_THEME_SETTINGS.lighting.point.color),
        intensity: normalizeNumber(lighting.point?.intensity, DEFAULT_THEME_SETTINGS.lighting.point.intensity, 0, 20),
        distance: normalizeNumber(lighting.point?.distance, DEFAULT_THEME_SETTINGS.lighting.point.distance, 0, 5000),
        position: normalizePosition(lighting.point?.position, DEFAULT_THEME_SETTINGS.lighting.point.position)
      },
      ambient: {
        enabled: normalizeBoolean(lighting.ambient?.enabled, DEFAULT_THEME_SETTINGS.lighting.ambient.enabled),
        color: normalizeColor(lighting.ambient?.color, DEFAULT_THEME_SETTINGS.lighting.ambient.color),
        intensity: normalizeNumber(lighting.ambient?.intensity, DEFAULT_THEME_SETTINGS.lighting.ambient.intensity, 0, 20)
      },
      hemisphere: {
        enabled: normalizeBoolean(lighting.hemisphere?.enabled, DEFAULT_THEME_SETTINGS.lighting.hemisphere.enabled),
        skyColor: normalizeColor(lighting.hemisphere?.skyColor, DEFAULT_THEME_SETTINGS.lighting.hemisphere.skyColor),
        groundColor: normalizeColor(lighting.hemisphere?.groundColor, DEFAULT_THEME_SETTINGS.lighting.hemisphere.groundColor),
        intensity: normalizeNumber(lighting.hemisphere?.intensity, DEFAULT_THEME_SETTINGS.lighting.hemisphere.intensity, 0, 20)
      }
    }
  };
  normalized.modeColors = normalizeThemeModeColors(source.modeColors, normalized);

  return normalized;
}

function cloneNormalizedThemeSettings(value = DEFAULT_THEME_SETTINGS) {
  return normalizeThemeSettings(JSON.parse(JSON.stringify(value)));
}

export function normalizeThemePresetId(presetId) {
  const normalized = String(presetId || "").trim();
  if (THEME_PRESETS.some((preset) => preset.id === normalized)) {
    return normalized;
  }
  // Render-only ids normalize too, so a snapshot can name one. They are excluded from the
  // picker by not being in THEME_PRESETS, not by failing to resolve.
  return RENDER_ONLY_THEME_PRESETS.some((preset) => preset.id === normalized) ? normalized : "";
}

export function getThemePresetById(presetId) {
  const normalizedPresetId = normalizeThemePresetId(presetId);
  return THEME_PRESETS.find((preset) => preset.id === normalizedPresetId)
    || RENDER_ONLY_THEME_PRESETS.find((preset) => preset.id === normalizedPresetId)
    || DEFAULT_THEME_PRESET;
}

export function cloneThemePresetSettings(presetId) {
  return cloneNormalizedThemeSettings(getThemePresetById(presetId).settings);
}

export function getThemePresetIdForSettings(themeSettings) {
  return getMatchingThemePresetId(themeSettings);
}

function getMatchingThemePresetId(themeSettings) {
  const currentSignature = createThemeSettingsSignature(normalizeThemeSettings(themeSettings));
  for (const preset of THEME_PRESETS) {
    const presetSignature = createThemeSettingsSignature(normalizeThemeSettings(preset.settings));
    if (presetSignature === currentSignature) {
      return preset.id;
    }
  }
  return null;
}

export function resolveThemeSettingsColorMode(themeSettings = {}, { prefersDark = false, systemFallback = THEME_COLOR_MODES.LIGHT } = {}) {
  const normalizedColorMode = normalizeThemeColorMode(
    themeSettings?.colorMode,
    DEFAULT_THEME_SETTINGS?.colorMode || THEME_COLOR_MODES.SYSTEM
  );
  if (normalizedColorMode === THEME_COLOR_MODES.SYSTEM) {
    return prefersDark === true
      ? THEME_COLOR_MODES.DARK
      : normalizeThemeColorMode(systemFallback, THEME_COLOR_MODES.LIGHT) === THEME_COLOR_MODES.DARK
        ? THEME_COLOR_MODES.DARK
        : THEME_COLOR_MODES.LIGHT;
  }
  return normalizedColorMode;
}

export function resolveThemeSettingsForColorMode(themeSettings = {}, options = {}) {
  const normalized = normalizeThemeSettings(themeSettings);
  const resolvedColorMode = resolveThemeSettingsColorMode(normalized, options);
  const resolved = deepClone(normalized);
  resolved.colorMode = resolvedColorMode;
  applyThemeModeColorOverrides(resolved, normalized.modeColors?.[resolvedColorMode]);
  return normalizeThemeSettings(resolved);
}

export function themeSettingsSupportsSystemColorMode(themeSettings = {}) {
  const normalized = normalizeThemeSettings(themeSettings);
  return normalized.colorMode === THEME_COLOR_MODES.SYSTEM;
}

export function getEnvironmentPresetById(presetId) {
  return ENVIRONMENT_PRESETS.find((preset) => preset.id === presetId) || ENVIRONMENT_PRESETS[0];
}
