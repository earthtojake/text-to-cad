import {
  CAMERA_PROJECTION,
  DEFAULT_DISPLAY_EDGE_SETTINGS,
  DISABLED_DISPLAY_EDGE_SETTINGS,
  normalizeCameraProjection,
  normalizeDisplayEdgeSettings
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
  Object.freeze(["floor", "gridCenterColor"]),
  Object.freeze(["floor", "gridCellColor"]),
  Object.freeze(["floor", "grid", "centerColor"]),
  Object.freeze(["floor", "grid", "cellColor"]),
  Object.freeze(["floor", "axis", "color"]),
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
  gridCenterColor: "#6b7280",
  gridCellColor: "#cbd5e1",
  gridOpacity: 0.18,
  gridDensity: 1,
  centerColor: "#6b7280",
  cellColor: "#cbd5e1",
  opacity: 0.18,
  density: 1
});

// The interactive viewer has always rendered soft fill and rim directionals
// from its structural defaults. Themes that predate the fill/rim settings
// must normalize to these exact values so their lighting stays identical.
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
  if (normalized === "glass") {
    return THEME_FLOOR_MODES.STAGE;
  }
  return Object.values(THEME_FLOOR_MODES).includes(normalized)
    ? normalized
    : fallback;
}

export const ENVIRONMENT_PRESETS = Object.freeze([
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
  },
  {
    id: "colorful-1",
    label: "Colorful 1",
    url: "https://static.morflax.com/textures/env/colorful-1.jpg"
  },
  {
    id: "colorful-dark-1",
    label: "Colorful Dark 1",
    url: "https://static.morflax.com/textures/env/colorful-dark-1.jpg"
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

const BLUE_FILL_COLORS = Object.freeze(["#4cc9f0"]);

const MAGENTA_FILL_COLORS = Object.freeze(["#ff4faf"]);

const CLAY_FILL_COLORS = Object.freeze(["#b9856e"]);

// Deep phosphor green so the neon-green edge outline reads as bright linework
// against the fill — the classic dark-surface / bright-wireframe terminal look.
const TERMINAL_FILL_COLORS = Object.freeze(["#073a20"]);

const TERMINAL_EDGE_COLOR = "#66ff99";
const TERMINAL_EDGE_HIGHLIGHT_COLOR = "#b7ffc9";
const TERMINAL_EDGE_CLASS_SETTINGS = Object.freeze({
  feature: Object.freeze({
    opacity: 1,
    thickness: 1.6
  }),
  tangent: Object.freeze({
    opacity: 0.9,
    thickness: 1.15
  }),
  seam: Object.freeze({
    opacity: 0.92,
    thickness: 1
  }),
  degenerate: Object.freeze({
    opacity: 0.72,
    thickness: 0.8
  })
});

const TERMINAL_THEME_EDGE_SETTINGS = Object.freeze({
  ...CAD_THEME_EDGE_SETTINGS,
  enabled: true,
  color: TERMINAL_EDGE_COLOR,
  classes: TERMINAL_EDGE_CLASS_SETTINGS,
  highlightColor: TERMINAL_EDGE_HIGHLIGHT_COLOR,
  highlightOpacity: 1,
  highlightThickness: 3
});

const CHARCOAL_FILL_COLORS = Object.freeze([
  "#b6c4ce",
  "#8f9aa3",
  "#d3dae0",
  "#68737d"
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

function midpointPalette(primaryColors, secondaryColors) {
  const primary = Array.isArray(primaryColors) ? primaryColors : [];
  const secondary = Array.isArray(secondaryColors) ? secondaryColors : [];
  const colorCount = Math.max(primary.length, secondary.length);
  if (!colorCount) {
    return Object.freeze(["#ffffff"]);
  }

  return Object.freeze(Array.from({ length: colorCount }, (_, index) => {
    const primaryColor = primary[index] || primary.at(-1) || "#ffffff";
    const secondaryColor = secondary[index] || secondary.at(-1) || primaryColor;
    return mixHexColors(primaryColor, secondaryColor);
  }));
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
    gridCenterColor: centerColor,
    gridCellColor: cellColor,
    gridOpacity: opacity,
    gridDensity: density,
    grid: {
      enabled,
      centerColor,
      cellColor,
      opacity,
      density
    },
    centerColor,
    cellColor,
    opacity,
    density
  };
}

// Shared photoreal PBR treatment for the presentation-stage themes; each
// theme layers its own palette and grade on top.
const STUDIO_STAGE_MATERIALS = Object.freeze({
  cycleColors: false,
  overrideSourceColors: false,
  tintMode: "blend",
  tintStrength: 0,
  saturation: 1.05,
  contrast: 1.1,
  brightness: 1.02,
  roughness: 0.32,
  metalness: 0.32,
  clearcoat: 0.5,
  clearcoatRoughness: 0.24,
  opacity: 1,
  envMapIntensity: 1.5,
  emissiveIntensity: 0.02
});

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

const DARK_STUDIO_THEME_SETTINGS = Object.freeze({
  materials: {
    defaultColor: WORKBENCH_FILL_COLORS[0],
    fillColors: WORKBENCH_FILL_COLORS,
    cycleColors: false,
    overrideSourceColors: false,
    tintMode: "blend",
    tintStrength: 0,
    saturation: 1.2,
    contrast: 1.14,
    brightness: 1.06,
    roughness: 0.54,
    metalness: 0.02,
    clearcoat: 0.14,
    clearcoatRoughness: 0.4,
    opacity: 1,
    envMapIntensity: 0.5,
    emissiveIntensity: 0.03
  },
  background: {
    type: "linear",
    solidColor: "#081b2d",
    linearStart: "#18304a",
    linearEnd: "#030914",
    linearAngle: 135,
    radialInner: "#174267",
    radialOuter: "#030914"
  },
  floor: {
    mode: THEME_FLOOR_MODES.STAGE,
    color: "#0a2238",
    roughness: 0.38,
    reflectivity: 0.1,
    shadowOpacity: 0.42,
    horizonBlend: 0.1,
    ...createFloorGridSettings("#0a2238", { opacity: 0.22 }),
    enabled: false
  },
  environment: {
    enabled: true,
    presetId: "studio-hdri-43",
    intensity: 0.18,
    rotationY: -0.25,
    useAsBackground: false
  },
  lighting: {
    toneMappingExposure: 1.22,
    directional: {
      enabled: true,
      color: "#ffffff",
      intensity: 1.42,
      position: {
        x: -210,
        y: 260,
        z: 270
      }
    },
    spot: {
      enabled: true,
      color: "#70c4ff",
      intensity: 0.24,
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
      color: "#9bd0ff",
      intensity: 0.36,
      distance: 0,
      position: {
        x: -240,
        y: 110,
        z: -210
      }
    },
    ambient: {
      enabled: true,
      color: "#c6d8ea",
      intensity: 0.24
    },
    hemisphere: {
      enabled: true,
      skyColor: "#ffffff",
      groundColor: "#020713",
      intensity: 0.98
    }
  }
});

const CODEX_DARK_STUDIO_THEME_SETTINGS = Object.freeze({
  ...DARK_STUDIO_THEME_SETTINGS,
  materials: {
    ...DARK_STUDIO_THEME_SETTINGS.materials,
    defaultColor: CHARCOAL_FILL_COLORS[0],
    fillColors: CHARCOAL_FILL_COLORS
  },
  background: {
    ...DARK_STUDIO_THEME_SETTINGS.background,
    solidColor: "#151617",
    linearStart: "#2a2b2d",
    linearEnd: "#070809",
    radialInner: "#303133",
    radialOuter: "#070809"
  },
  floor: {
    ...DARK_STUDIO_THEME_SETTINGS.floor,
    color: "#171819",
    ...createFloorGridSettings("#171819", { opacity: 0.22 })
  }
});

const DARKOAL_FILL_COLORS = midpointPalette(
  DARK_STUDIO_THEME_SETTINGS.materials.fillColors,
  CODEX_DARK_STUDIO_THEME_SETTINGS.materials.fillColors
);

const DARKOAL_THEME_SETTINGS = Object.freeze({
  ...DARK_STUDIO_THEME_SETTINGS,
  materials: {
    ...DARK_STUDIO_THEME_SETTINGS.materials,
    defaultColor: DARKOAL_FILL_COLORS[0],
    fillColors: DARKOAL_FILL_COLORS
  },
  background: {
    ...DARK_STUDIO_THEME_SETTINGS.background,
    solidColor: mixHexColors(DARK_STUDIO_THEME_SETTINGS.background.solidColor, CODEX_DARK_STUDIO_THEME_SETTINGS.background.solidColor),
    linearStart: mixHexColors(DARK_STUDIO_THEME_SETTINGS.background.linearStart, CODEX_DARK_STUDIO_THEME_SETTINGS.background.linearStart),
    linearEnd: mixHexColors(DARK_STUDIO_THEME_SETTINGS.background.linearEnd, CODEX_DARK_STUDIO_THEME_SETTINGS.background.linearEnd),
    radialInner: mixHexColors(DARK_STUDIO_THEME_SETTINGS.background.radialInner, CODEX_DARK_STUDIO_THEME_SETTINGS.background.radialInner),
    radialOuter: mixHexColors(DARK_STUDIO_THEME_SETTINGS.background.radialOuter, CODEX_DARK_STUDIO_THEME_SETTINGS.background.radialOuter)
  },
  floor: {
    ...DARK_STUDIO_THEME_SETTINGS.floor,
    color: mixHexColors(DARK_STUDIO_THEME_SETTINGS.floor.color, CODEX_DARK_STUDIO_THEME_SETTINGS.floor.color),
    ...createFloorGridSettings(
      mixHexColors(DARK_STUDIO_THEME_SETTINGS.floor.color, CODEX_DARK_STUDIO_THEME_SETTINGS.floor.color),
      { opacity: 0.22 }
    )
  }
});

const BLUE_STAGE_FLOOR_COLOR = "#062a42";

// Blue keeps its goal — a single cyan fill on a deep-navy canvas — restaged
// as a glossy presentation floor with cyan rim/spot accents.
const BLUE_THEME_SETTINGS = Object.freeze({
  projection: CAMERA_PROJECTION.PERSPECTIVE,
  materials: {
    ...STUDIO_STAGE_MATERIALS,
    defaultColor: BLUE_FILL_COLORS[0],
    fillColors: BLUE_FILL_COLORS,
    saturation: 1.15
  },
  background: {
    type: "radial",
    solidColor: "#04131f",
    linearStart: "#07253a",
    linearEnd: "#020a12",
    linearAngle: 128,
    radialInner: "#0a5e8f",
    radialOuter: "#020a12"
  },
  floor: {
    mode: THEME_FLOOR_MODES.STAGE,
    color: BLUE_STAGE_FLOOR_COLOR,
    roughness: 0.42,
    reflectivity: 0.28,
    shadowOpacity: 0.5,
    horizonBlend: 0.32,
    ...createFloorGridSettings(BLUE_STAGE_FLOOR_COLOR, { enabled: false, opacity: 0.18 }),
    enabled: true
  },
  environment: {
    enabled: true,
    presetId: "studio-hdri-43",
    intensity: 0.6,
    rotationY: -0.35,
    useAsBackground: false
  },
  lighting: {
    toneMappingExposure: 1.22,
    directional: {
      enabled: true,
      color: "#eaf4ff",
      intensity: 2.2,
      position: { x: -190, y: 240, z: 300 }
    },
    fill: {
      enabled: true,
      color: "#9db8cc",
      intensity: 0.38,
      position: { x: 120, y: 80, z: 210 }
    },
    rim: {
      enabled: true,
      color: "#7fd4ff",
      intensity: 1.4,
      position: { x: -320, y: 260, z: 160 }
    },
    spot: {
      enabled: true,
      color: "#59c4ff",
      intensity: 0.5,
      angle: 0.7,
      distance: 0,
      position: { x: 190, y: 210, z: 170 }
    },
    point: {
      enabled: true,
      color: "#9bd0ff",
      intensity: 0.3,
      distance: 0,
      position: { x: -240, y: 110, z: -210 }
    },
    ambient: {
      enabled: true,
      color: "#cfe2f2",
      intensity: 0.2
    },
    hemisphere: {
      enabled: true,
      skyColor: "#dcedfa",
      groundColor: "#03121d",
      intensity: 0.8
    }
  }
});

const PINK_STAGE_FLOOR_COLOR = "#2b0e20";

// Magenta keeps its goal — a saturated magenta fill on a near-black studio —
// with a deep wine stage floor and magenta rim glow.
const PINK_THEME_SETTINGS = Object.freeze({
  projection: CAMERA_PROJECTION.PERSPECTIVE,
  materials: {
    ...STUDIO_STAGE_MATERIALS,
    defaultColor: MAGENTA_FILL_COLORS[0],
    fillColors: MAGENTA_FILL_COLORS,
    saturation: 1.2
  },
  background: {
    type: "radial",
    solidColor: "#1d0a16",
    linearStart: "#7a1a52",
    linearEnd: "#170812",
    linearAngle: 140,
    radialInner: "#6e1348",
    radialOuter: "#12060e"
  },
  floor: {
    mode: THEME_FLOOR_MODES.STAGE,
    color: PINK_STAGE_FLOOR_COLOR,
    roughness: 0.4,
    reflectivity: 0.3,
    shadowOpacity: 0.52,
    horizonBlend: 0.3,
    ...createFloorGridSettings(PINK_STAGE_FLOOR_COLOR, { enabled: false, opacity: 0.18 }),
    enabled: true
  },
  environment: {
    enabled: true,
    presetId: "studio-hdri-43",
    intensity: 0.6,
    rotationY: -0.35,
    useAsBackground: false
  },
  lighting: {
    toneMappingExposure: 1.22,
    directional: {
      enabled: true,
      color: "#fff0f6",
      intensity: 2.2,
      position: { x: -190, y: 240, z: 300 }
    },
    fill: {
      enabled: true,
      color: "#b295a6",
      intensity: 0.36,
      position: { x: 120, y: 80, z: 210 }
    },
    rim: {
      enabled: true,
      color: "#ff8fd0",
      intensity: 1.4,
      position: { x: -320, y: 260, z: 160 }
    },
    spot: {
      enabled: true,
      color: "#ff5fb0",
      intensity: 0.5,
      angle: 0.7,
      distance: 0,
      position: { x: 190, y: 210, z: 170 }
    },
    point: {
      enabled: true,
      color: "#d998ff",
      intensity: 0.28,
      distance: 0,
      position: { x: -240, y: 110, z: -210 }
    },
    ambient: {
      enabled: true,
      color: "#e8d3de",
      intensity: 0.2
    },
    hemisphere: {
      enabled: true,
      skyColor: "#f4dcea",
      groundColor: "#170812",
      intensity: 0.78
    }
  }
});

const CLAY_STAGE_FLOOR_COLOR = "#d9a97c";

// Clay keeps its goal — a warm terracotta presentation — with a satin clay
// stage, golden-hour key light, and soft warm bounce.
const CLAY_SUNRISE_THEME_SETTINGS = Object.freeze({
  projection: CAMERA_PROJECTION.PERSPECTIVE,
  materials: {
    ...STUDIO_STAGE_MATERIALS,
    defaultColor: CLAY_FILL_COLORS[0],
    fillColors: CLAY_FILL_COLORS,
    saturation: 1.1,
    roughness: 0.38,
    metalness: 0.22,
    envMapIntensity: 1.2
  },
  background: {
    type: "linear",
    solidColor: "#f3eadc",
    linearStart: "#f7ead8",
    linearEnd: "#c88d5d",
    linearAngle: 162,
    radialInner: "#f7ead8",
    radialOuter: "#b06c43"
  },
  floor: {
    mode: THEME_FLOOR_MODES.STAGE,
    color: CLAY_STAGE_FLOOR_COLOR,
    roughness: 0.5,
    reflectivity: 0.22,
    shadowOpacity: 0.42,
    horizonBlend: 0.26,
    ...createFloorGridSettings(CLAY_STAGE_FLOOR_COLOR, { enabled: false, opacity: 0.18 }),
    enabled: true
  },
  environment: {
    enabled: true,
    presetId: "studio-hdri-43",
    intensity: 0.55,
    rotationY: -0.25,
    useAsBackground: false
  },
  lighting: {
    toneMappingExposure: 1.16,
    directional: {
      enabled: true,
      color: "#fff0dc",
      intensity: 2.1,
      position: { x: -190, y: 240, z: 300 }
    },
    fill: {
      enabled: true,
      color: "#d8b795",
      intensity: 0.45,
      position: { x: 120, y: 80, z: 210 }
    },
    rim: {
      enabled: true,
      color: "#ffd7ad",
      intensity: 0.85,
      position: { x: -320, y: 260, z: 160 }
    },
    spot: {
      enabled: true,
      color: "#ffe3c4",
      intensity: 0.4,
      angle: 0.7,
      distance: 0,
      position: { x: 190, y: 210, z: 170 }
    },
    point: {
      enabled: true,
      color: "#ff9e63",
      intensity: 0.25,
      distance: 0,
      position: { x: -240, y: 110, z: -210 }
    },
    ambient: {
      enabled: true,
      color: "#f5e7d5",
      intensity: 0.28
    },
    hemisphere: {
      enabled: true,
      skyColor: "#fff4e4",
      groundColor: "#a86b40",
      intensity: 0.9
    }
  }
});

const TERMINAL_STAGE_FLOOR_COLOR = "#02120a";

// Terminal keeps its goal — phosphor-green CRT linework — restaged on a
// glossy black floor whose grid keeps the green scanline identity.
const TERMINAL_THEME_SETTINGS = Object.freeze({
  projection: CAMERA_PROJECTION.PERSPECTIVE,
  materials: {
    ...STUDIO_STAGE_MATERIALS,
    defaultColor: TERMINAL_FILL_COLORS[0],
    fillColors: TERMINAL_FILL_COLORS,
    saturation: 1.15,
    roughness: 0.4,
    metalness: 0.25,
    envMapIntensity: 0.9,
    emissiveIntensity: 0.04
  },
  edges: {
    ...TERMINAL_THEME_EDGE_SETTINGS
  },
  background: {
    type: "radial",
    solidColor: "#020403",
    linearStart: "#031109",
    linearEnd: "#000000",
    linearAngle: 180,
    radialInner: "#06301b",
    radialOuter: "#000201"
  },
  // Transparent floor: no solid stage plane or shadow catcher, just a neon
  // green grid floating over the dark backdrop — the classic terminal look.
  floor: {
    mode: THEME_FLOOR_MODES.GRID,
    color: TERMINAL_STAGE_FLOOR_COLOR,
    roughness: 0.35,
    reflectivity: 0.32,
    shadowOpacity: 0.55,
    horizonBlend: 0.24,
    ...createFloorGridSettings(TERMINAL_STAGE_FLOOR_COLOR, {
      enabled: true,
      centerColor: TERMINAL_EDGE_COLOR,
      cellColor: "#0f5230",
      opacity: 0.42,
      density: 1.15
    }),
    enabled: false
  },
  environment: {
    enabled: true,
    presetId: "studio-hdri-43",
    intensity: 0.35,
    rotationY: -0.35,
    useAsBackground: false
  },
  lighting: {
    toneMappingExposure: 1.2,
    directional: {
      enabled: true,
      color: "#eafff2",
      intensity: 2,
      position: { x: -190, y: 240, z: 300 }
    },
    fill: {
      enabled: true,
      color: "#7da98d",
      intensity: 0.35,
      position: { x: 120, y: 80, z: 210 }
    },
    rim: {
      enabled: true,
      color: "#66ff99",
      intensity: 1.2,
      position: { x: -320, y: 260, z: 160 }
    },
    spot: {
      enabled: true,
      color: "#4dff8a",
      intensity: 0.45,
      angle: 0.7,
      distance: 0,
      position: { x: 190, y: 210, z: 170 }
    },
    point: {
      enabled: true,
      color: "#9dffc0",
      intensity: 0.25,
      distance: 0,
      position: { x: -240, y: 110, z: -210 }
    },
    ambient: {
      enabled: true,
      color: "#cfe8d8",
      intensity: 0.2
    },
    hemisphere: {
      enabled: true,
      skyColor: "#d8ffe8",
      groundColor: "#01130a",
      intensity: 0.75
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

// Workbench dark mode treatment: a deep, slightly muted blue-slate. Mode
// overrides can only swap colors, not light intensities, so dark-part
// visibility is tuned entirely through these colors: lifted ambient and
// hemisphere-ground fill so shaded faces of dark parts keep their form and
// a canvas/floor luminance step for silhouette separation. Edges stay deep
// navy so they read as subtle technical linework on light fills; wireframe
// display relies on the automatic light-edge contrast fallback.
const WORKBENCH_DARK_FLOOR_COLOR = "#202832";

const WORKBENCH_DARK_THEME_SETTINGS = Object.freeze({
  ...DARKOAL_THEME_SETTINGS,
  background: {
    ...DARKOAL_THEME_SETTINGS.background,
    solidColor: "#181f28",
    linearStart: "#242e3a",
    linearEnd: "#0c1016",
    radialInner: "#293443",
    radialOuter: "#0c1016"
  },
  floor: {
    ...DARKOAL_THEME_SETTINGS.floor,
    color: WORKBENCH_DARK_FLOOR_COLOR,
    enabled: false,
    // Only the colors here reach the dark preset: mode overrides swap colors,
    // not booleans or opacities, so enablement and opacity come from the light
    // base above and are deliberately not restated.
    ...createFloorGridSettings(WORKBENCH_DARK_FLOOR_COLOR, { enabled: true, opacity: 0.16 }),
    ...createFloorAxisSettings(WORKBENCH_DARK_FLOOR_COLOR, { enabled: true, opacity: 0.28 })
  },
  lighting: {
    ...DARKOAL_THEME_SETTINGS.lighting,
    spot: {
      ...DARKOAL_THEME_SETTINGS.lighting.spot,
      color: "#b3d4f2"
    },
    point: {
      ...DARKOAL_THEME_SETTINGS.lighting.point,
      color: "#bfd8f0"
    },
    ambient: {
      ...DARKOAL_THEME_SETTINGS.lighting.ambient,
      color: "#dfe7f0"
    },
    hemisphere: {
      ...DARKOAL_THEME_SETTINGS.lighting.hemisphere,
      groundColor: "#333d4b"
    }
  }
});

// Workbench ships as two distinct, single-palette themes (light + dark) rather
// than one system-adaptive theme. App light/dark is inferred from the active
// theme's background, so each Workbench variant is pinned to its own palette.
const WORKBENCH_LIGHT_THEME_PRESET_SETTINGS = withThemeColorMode(
  WORKBENCH_BASE_THEME_SETTINGS,
  THEME_COLOR_MODES.LIGHT
);
// Workbench Dark keeps the shared Workbench materials and lighting intensities,
// swapping in the dark canvas/floor/light colors (the same color set the old
// system theme applied for its dark mode) so the two variants read as one theme
// on two canvases.
const WORKBENCH_DARK_BAKED_SETTINGS = deepClone(WORKBENCH_BASE_THEME_SETTINGS);
applyThemeModeColorOverrides(
  WORKBENCH_DARK_BAKED_SETTINGS,
  createThemeModeColors(WORKBENCH_BASE_THEME_SETTINGS, WORKBENCH_DARK_THEME_SETTINGS).dark
);
const WORKBENCH_DARK_THEME_PRESET_SETTINGS = withThemeColorMode(
  WORKBENCH_DARK_BAKED_SETTINGS,
  THEME_COLOR_MODES.DARK
);
// Back-compat: the migration fallback and any "workbench" id resolve to light.
const WORKBENCH_THEME_SETTINGS = WORKBENCH_LIGHT_THEME_PRESET_SETTINGS;

// Cinematic: a filmic product-shot stage. Warm charcoal backdrop with a soft
// radial falloff, satin PBR finish with studio-HDRI reflections, a warm key
// with cool rim separation, an amber spot glow pooling on a faintly gridded
// glossy floor. Colors follow a warm silver / copper grade; source part
// colors pass through with a gentle contrast lift. Distinct from the legacy
// CINEMATIC_THEME_SETTINGS above, which survives only to seed the Workbench
// presets and the stored-settings migration matchers.
const CINEMATIC_FILL_COLORS = Object.freeze([
  "#c9c2bb",
  "#c98d55",
  "#8e969e",
  "#a9784e"
]);

const CINEMATIC_STUDIO_FLOOR_COLOR = "#131418";

const CINEMATIC_STUDIO_THEME_SETTINGS = Object.freeze({
  projection: CAMERA_PROJECTION.PERSPECTIVE,
  materials: {
    ...STUDIO_STAGE_MATERIALS,
    defaultColor: CINEMATIC_FILL_COLORS[0],
    fillColors: CINEMATIC_FILL_COLORS
  },
  background: {
    type: "radial",
    solidColor: "#121317",
    linearStart: "#1c1d22",
    linearEnd: "#0a0a0d",
    linearAngle: 135,
    radialInner: "#191a1f",
    radialOuter: "#0a0a0d"
  },
  floor: {
    mode: THEME_FLOOR_MODES.STAGE,
    color: CINEMATIC_STUDIO_FLOOR_COLOR,
    roughness: 0.55,
    reflectivity: 0.16,
    shadowOpacity: 0.58,
    horizonBlend: 0.34,
    ...createFloorGridSettings(CINEMATIC_STUDIO_FLOOR_COLOR, { enabled: true, opacity: 0.09 }),
    enabled: true
  },
  environment: {
    enabled: true,
    presetId: "studio-hdri-43",
    intensity: 0.65,
    rotationY: -0.35,
    useAsBackground: false
  },
  lighting: {
    toneMappingExposure: 1.24,
    directional: {
      enabled: true,
      color: "#fff3e4",
      intensity: 2.5,
      position: {
        x: -190,
        y: 240,
        z: 300
      }
    },
    fill: {
      enabled: true,
      color: "#a6a9ad",
      intensity: 0.42,
      position: {
        x: 120,
        y: 80,
        z: 210
      }
    },
    rim: {
      enabled: true,
      color: "#d9e6f5",
      intensity: 1.3,
      position: {
        x: -320,
        y: 260,
        z: 160
      }
    },
    spot: {
      enabled: true,
      color: "#e8e5df",
      intensity: 0.35,
      angle: 0.7,
      distance: 0,
      position: {
        x: 190,
        y: 210,
        z: 170
      }
    },
    point: {
      enabled: true,
      color: "#9fc4e8",
      intensity: 0.3,
      distance: 0,
      position: {
        x: -240,
        y: 110,
        z: -210
      }
    },
    ambient: {
      enabled: true,
      color: "#d5d7da",
      intensity: 0.24
    },
    hemisphere: {
      enabled: true,
      skyColor: "#e5e7ea",
      groundColor: "#1b1c1f",
      intensity: 0.85
    }
  }
});

const CINEMATIC_STUDIO_THEME_PRESET_SETTINGS = withThemeColorMode(
  CINEMATIC_STUDIO_THEME_SETTINGS,
  THEME_COLOR_MODES.DARK
);

// Vibrant: the cinematic stage flipped to a bright infinity cove. Crisp
// white key and rim, strong studio reflections, and a saturation lift so
// source colors read punchy; uncolored parts cycle a vivid palette.
const VIBRANT_FILL_COLORS = Object.freeze([
  "#3b82f6",
  "#f97352",
  "#fbbf24",
  "#34d399",
  "#a78bfa",
  "#f472b6"
]);

const VIBRANT_STUDIO_FLOOR_COLOR = "#eef1f5";

const VIBRANT_STUDIO_THEME_SETTINGS = Object.freeze({
  projection: CAMERA_PROJECTION.PERSPECTIVE,
  materials: {
    ...STUDIO_STAGE_MATERIALS,
    defaultColor: VIBRANT_FILL_COLORS[0],
    // Palette kept for the picker/custom edits but not cycled: Vibrant shows
    // off each model's own colors, just with a punchier photoreal grade.
    fillColors: VIBRANT_FILL_COLORS,
    cycleColors: false,
    saturation: 1.32,
    contrast: 1.12,
    brightness: 1.04,
    roughness: 0.3,
    metalness: 0.26,
    clearcoat: 0.55,
    clearcoatRoughness: 0.2,
    envMapIntensity: 1.2
  },
  background: {
    type: "radial",
    solidColor: "#f2f4f7",
    linearStart: "#ffffff",
    linearEnd: "#dde2e9",
    linearAngle: 135,
    radialInner: "#ffffff",
    radialOuter: "#dbe0e7"
  },
  floor: {
    mode: THEME_FLOOR_MODES.STAGE,
    color: VIBRANT_STUDIO_FLOOR_COLOR,
    roughness: 0.3,
    reflectivity: 0.34,
    shadowOpacity: 0.3,
    horizonBlend: 0.42,
    ...createFloorGridSettings(VIBRANT_STUDIO_FLOOR_COLOR, { enabled: false, opacity: 0.12 }),
    enabled: true
  },
  environment: {
    enabled: true,
    presetId: "studio-hdri-43",
    intensity: 0.9,
    rotationY: -0.35,
    useAsBackground: false
  },
  lighting: {
    toneMappingExposure: 1.12,
    directional: {
      enabled: true,
      color: "#ffffff",
      intensity: 2.2,
      position: { x: -190, y: 240, z: 300 }
    },
    fill: {
      enabled: true,
      color: "#dfe6ee",
      intensity: 0.5,
      position: { x: 120, y: 80, z: 210 }
    },
    rim: {
      enabled: true,
      color: "#ffffff",
      intensity: 0.9,
      position: { x: -320, y: 260, z: 160 }
    },
    spot: {
      enabled: true,
      color: "#ffffff",
      intensity: 0.3,
      angle: 0.7,
      distance: 0,
      position: { x: 190, y: 210, z: 170 }
    },
    point: {
      enabled: true,
      color: "#ffd9a8",
      intensity: 0.25,
      distance: 0,
      position: { x: -240, y: 110, z: -210 }
    },
    ambient: {
      enabled: true,
      color: "#ffffff",
      intensity: 0.3
    },
    hemisphere: {
      enabled: true,
      skyColor: "#ffffff",
      groundColor: "#c9d2dc",
      intensity: 0.9
    }
  }
});

const VIBRANT_STUDIO_THEME_PRESET_SETTINGS = withThemeColorMode(
  VIBRANT_STUDIO_THEME_SETTINGS,
  THEME_COLOR_MODES.LIGHT
);

const BLUE_THEME_PRESET_SETTINGS = withThemeColorMode(BLUE_THEME_SETTINGS, THEME_COLOR_MODES.DARK);
const PINK_THEME_PRESET_SETTINGS = withThemeColorMode(PINK_THEME_SETTINGS, THEME_COLOR_MODES.DARK);
const CLAY_SUNRISE_THEME_PRESET_SETTINGS = withThemeColorMode(CLAY_SUNRISE_THEME_SETTINGS, THEME_COLOR_MODES.LIGHT);
const TERMINAL_THEME_PRESET_SETTINGS = withThemeColorMode(TERMINAL_THEME_SETTINGS, THEME_COLOR_MODES.DARK);

export const THEME_PRESETS = Object.freeze([
  {
    id: "workbench-light",
    label: "Light",
    description: "Balanced CAD workbench lighting on a light canvas.",
    preview: {
      background: "#f0f4f9",
      modelColor: "#b6c4ce",
      accentColor: "#4ea7d8"
    },
    settings: WORKBENCH_LIGHT_THEME_PRESET_SETTINGS
  },
  {
    id: "workbench-dark",
    label: "Dark",
    description: "Balanced CAD workbench lighting on a deep blue-slate canvas.",
    preview: {
      background: "#181f28",
      modelColor: "#b6c4ce",
      accentColor: "#4ea7d8"
    },
    settings: WORKBENCH_DARK_THEME_PRESET_SETTINGS
  },
  {
    id: "cinematic",
    label: "Cinematic",
    description: "Filmic studio stage with warm key lighting, copper accents, and a glossy charcoal floor.",
    preview: {
      background: "radial-gradient(circle at 42% 32%, #23242a 0%, #0a0a0d 78%)",
      modelColor: "#c9c2bb",
      accentColor: "#c98d55"
    },
    settings: CINEMATIC_STUDIO_THEME_PRESET_SETTINGS
  },
  {
    id: "vibrant",
    label: "Vibrant",
    description: "Bright studio cove with punchy color and photoreal reflections.",
    preview: {
      background: "radial-gradient(circle at 42% 32%, #ffffff 0%, #dbe0e7 78%)",
      modelColor: "#3b82f6",
      accentColor: "#f97352"
    },
    settings: VIBRANT_STUDIO_THEME_PRESET_SETTINGS
  },
  {
    id: "blue",
    label: "Blue",
    description: "Single cyan fill on a deep-navy stage with cyan rim lighting.",
    preview: {
      background: BLUE_FILL_COLORS[0],
      modelColor: BLUE_FILL_COLORS[0],
      accentColor: BLUE_FILL_COLORS[0]
    },
    settings: BLUE_THEME_PRESET_SETTINGS
  },
  {
    id: "pink",
    label: "Magenta",
    description: "Saturated magenta fill on a near-black stage with magenta rim glow.",
    preview: {
      background: MAGENTA_FILL_COLORS[0],
      modelColor: MAGENTA_FILL_COLORS[0],
      accentColor: MAGENTA_FILL_COLORS[0]
    },
    settings: PINK_THEME_PRESET_SETTINGS
  },
  {
    id: "clay-sunrise",
    label: "Clay",
    description: "Warm clay fill on a satin terracotta stage with golden-hour light.",
    preview: {
      background: CLAY_FILL_COLORS[0],
      modelColor: CLAY_FILL_COLORS[0],
      accentColor: CLAY_FILL_COLORS[0]
    },
    settings: CLAY_SUNRISE_THEME_PRESET_SETTINGS
  },
  {
    id: "terminal",
    label: "Terminal",
    description: "Phosphor-green linework on a glossy black stage with a green grid floor.",
    preview: {
      background: TERMINAL_FILL_COLORS[0],
      modelColor: TERMINAL_FILL_COLORS[0],
      accentColor: TERMINAL_FILL_COLORS[0]
    },
    settings: TERMINAL_THEME_PRESET_SETTINGS
  }
]);

const THEME_PRESET_ID_ALIASES = Object.freeze({
  workbench: "workbench-light",
  light: "workbench-light",
  dark: "workbench-dark"
});

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
  description: "Workbench Light with the grid and origin axis removed, for headless renders.",
  preview: {
    background: "#f0f4f9",
    modelColor: "#b6c4ce",
    accentColor: "#4ea7d8"
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
    projection: value?.projection || "",
    modeColors: value?.modeColors || {},
    materials: value?.materials || {},
    background: value?.background || {},
    floor: value?.floor || {},
    environment: value?.environment || {},
    lighting: value?.lighting || {},
    edges: value?.edges || null
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
    materials.defaultColor || materials.tintColor,
    DEFAULT_THEME_SETTINGS.materials.defaultColor
  );
  const fillColors = normalizeThemeFillColors(materials.fillColors, normalizedDefaultColor);
  const normalizedFloorColor = normalizeColor(floor.color, DEFAULT_THEME_SETTINGS.floor?.color || "#141416");
  const normalizedFloorMode = normalizeFloorMode(floor.mode, DEFAULT_THEME_SETTINGS.floor?.mode || THEME_FLOOR_MODES.STAGE);
  const grid = floor.grid && typeof floor.grid === "object" && !Array.isArray(floor.grid)
    ? floor.grid
    : {};
  const axis = floor.axis && typeof floor.axis === "object" && !Array.isArray(floor.axis)
    ? floor.axis
    : {};
  const fallbackGridSettings = createFloorGridSettings(normalizedFloorColor);
  const normalizedGridCenterColor = normalizeColor(
    grid.centerColor ?? floor.gridCenterColor ?? floor.gridCenter,
    fallbackGridSettings.centerColor
  );
  const normalizedGridCellColor = normalizeColor(
    grid.cellColor ?? floor.gridCellColor ?? floor.gridCell,
    fallbackGridSettings.cellColor
  );
  const normalizedGridOpacity = normalizeNumber(
    grid.opacity ?? floor.gridOpacity,
    fallbackGridSettings.opacity,
    0,
    1
  );
  const normalizedGridDensity = normalizeNumber(
    grid.density ?? floor.gridDensity,
    fallbackGridSettings.density,
    MIN_FLOOR_GRID_DENSITY,
    MAX_FLOOR_GRID_DENSITY
  );
  const colorMode = normalizeThemeColorMode(
    source.colorMode,
    DEFAULT_THEME_SETTINGS?.colorMode || THEME_COLOR_MODES.SYSTEM
  );

  const normalized = {
    colorMode,
    // The camera projection is a theme trait: presentation stages read best in
    // perspective, engineering canvases in orthographic. Themes that predate
    // the setting normalize to the historical orthographic default.
    projection: normalizeCameraProjection(
      source.projection,
      DEFAULT_THEME_SETTINGS?.projection || CAMERA_PROJECTION.ORTHOGRAPHIC
    ),
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
      followModel: normalizeBoolean(floor.followModel, DEFAULT_THEME_SETTINGS.floor?.followModel ?? true),
      color: normalizedFloorColor,
      roughness: normalizeNumber(floor.roughness, DEFAULT_THEME_SETTINGS.floor?.roughness ?? 0.72, 0, 1),
      reflectivity: normalizeNumber(floor.reflectivity, DEFAULT_THEME_SETTINGS.floor?.reflectivity ?? 0.12, 0, 1),
      shadowOpacity: normalizeNumber(floor.shadowOpacity, DEFAULT_THEME_SETTINGS.floor?.shadowOpacity ?? 0.45, 0, 1),
      horizonBlend: normalizeNumber(floor.horizonBlend, DEFAULT_THEME_SETTINGS.floor?.horizonBlend ?? 0, 0, 1),
      gridCenterColor: normalizedGridCenterColor,
      gridCellColor: normalizedGridCellColor,
      gridOpacity: normalizedGridOpacity,
      gridDensity: normalizedGridDensity,
      grid: {
        enabled: normalizeBoolean(grid.enabled, normalizedFloorMode === THEME_FLOOR_MODES.GRID),
        centerColor: normalizedGridCenterColor,
        cellColor: normalizedGridCellColor,
        opacity: normalizedGridOpacity,
        density: normalizedGridDensity
      },
      axis: {
        enabled: normalizeBoolean(axis.enabled, DEFAULT_FLOOR_AXIS_SETTINGS.enabled),
        color: normalizeColor(axis.color, normalizedGridCenterColor),
        opacity: normalizeNumber(axis.opacity, DEFAULT_FLOOR_AXIS_SETTINGS.opacity, 0, 1)
      }
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
  // Edge styling normally lives in per-file display settings, so themes stay
  // edge-agnostic by default. A theme MAY opt in to its own outline (e.g.
  // Terminal's neon-green linework); when it does, the viewer/snapshot use it
  // as the base edge appearance. Only carry it when explicitly declared.
  if (source.edges && typeof source.edges === "object" && !Array.isArray(source.edges)) {
    normalized.edges = normalizeDisplayEdgeSettings(source.edges);
  }
  normalized.modeColors = normalizeThemeModeColors(source.modeColors, normalized);

  return normalized;
}

function cloneNormalizedThemeSettings(value = DEFAULT_THEME_SETTINGS) {
  return normalizeThemeSettings(JSON.parse(JSON.stringify(value)));
}

export function normalizeThemePresetId(presetId) {
  const normalized = String(presetId || "").trim();
  const canonical = THEME_PRESET_ID_ALIASES[normalized] || normalized;
  if (THEME_PRESETS.some((preset) => preset.id === canonical)) {
    return canonical;
  }
  // Render-only ids normalize too, so a snapshot can name one. They are excluded from the
  // picker by not being in THEME_PRESETS, not by failing to resolve.
  return RENDER_ONLY_THEME_PRESETS.some((preset) => preset.id === canonical) ? canonical : "";
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

export function cloneThemeSettings(themeId) {
  return cloneThemePresetSettings(themeId);
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

// The dominant background color drives the app's light/dark chrome, because the
// nav/sidebars float over the (transparent) viewport: their contrast depends on
// what is behind them, not on the floor or fills.
function dominantBackgroundLuminance(themeSettings = {}) {
  const background = themeSettings.background || {};
  const type = background.type || "solid";
  const fallback =
    DEFAULT_THEME_SETTINGS?.background?.solidColor || "#ffffff";
  if (type === "linear") {
    return (
      relativeLuminance(background.linearStart, fallback) +
      relativeLuminance(background.linearEnd, fallback)
    ) / 2;
  }
  if (type === "radial") {
    return (
      relativeLuminance(background.radialInner, fallback) +
      relativeLuminance(background.radialOuter, fallback)
    ) / 2;
  }
  return relativeLuminance(background.solidColor, fallback);
}

export function inferThemeSettingsSceneTone(themeSettings, options = {}) {
  const normalized = resolveThemeSettingsForColorMode(themeSettings, options);
  return dominantBackgroundLuminance(normalized) >= 0.3 ? "light" : "dark";
}

export function inferThemeSceneTone(themeSettings) {
  return inferThemeSettingsSceneTone(themeSettings);
}

// The dominant backdrop color as a hex value, for UI chrome that tints toward
// the active scene (glass surfaces). Mirrors the gradient handling of
// dominantBackgroundLuminance.
export function resolveThemeSettingsBackdropColor(themeSettings = {}, options = {}) {
  const normalized = resolveThemeSettingsForColorMode(themeSettings, options);
  const background = normalized.background || {};
  if (background.type === "linear") {
    return mixHexColors(background.linearStart, background.linearEnd);
  }
  if (background.type === "radial") {
    return mixHexColors(background.radialInner, background.radialOuter);
  }
  return normalizeColor(
    background.solidColor,
    DEFAULT_THEME_SETTINGS?.background?.solidColor || "#ffffff"
  );
}

export function getEnvironmentPresetById(presetId) {
  return ENVIRONMENT_PRESETS.find((preset) => preset.id === presetId) || ENVIRONMENT_PRESETS[0];
}
