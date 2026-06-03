const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}){1,2}$/;
export const MAX_THEME_FILL_COLORS = 50;
export const CAD_EDGE_COLOR = "#132232";
export const CAD_EDGE_HIGHLIGHT_COLOR = "#8dc5ff";
export const CAD_EDGE_CLASS_IDS = Object.freeze(["feature", "tangent", "seam", "degenerate"]);

const CAD_EDGE_CLASS_SETTINGS = Object.freeze({
  feature: Object.freeze({
    opacity: 1,
    thickness: 1.15
  }),
  tangent: Object.freeze({
    opacity: 0.5,
    thickness: 1.15
  }),
  seam: Object.freeze({
    opacity: 0.85,
    thickness: 1.15
  }),
  degenerate: Object.freeze({
    opacity: 1,
    thickness: 0
  })
});

const CAD_THEME_EDGE_SETTINGS = Object.freeze({
  enabled: true,
  contrastMode: "manual",
  color: CAD_EDGE_COLOR,
  thickness: 1,
  classes: CAD_EDGE_CLASS_SETTINGS,
  highlightColor: CAD_EDGE_HIGHLIGHT_COLOR,
  highlightOpacity: 1,
  highlightThickness: 3,
  silhouette: false,
  silhouetteScale: 0
});

const DISABLED_THEME_EDGE_SETTINGS = Object.freeze({
  ...CAD_THEME_EDGE_SETTINGS,
  enabled: false
});

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

function normalizeEdgeContrastMode(value, fallback = "manual") {
  const normalized = String(value || "").trim().toLowerCase();
  return ["auto", "manual"].includes(normalized)
    ? normalized
    : fallback;
}

function normalizeEdgeClassSettings(value = {}, fallback = CAD_EDGE_CLASS_SETTINGS) {
  const source = value && typeof value === "object" ? value : {};
  return Object.fromEntries(CAD_EDGE_CLASS_IDS.map((classId) => {
    const classSource = source[classId] && typeof source[classId] === "object" ? source[classId] : {};
    const classFallback = fallback?.[classId] || CAD_EDGE_CLASS_SETTINGS[classId];
    const legacyDisabled = classSource.enabled === false;
    return [classId, {
      opacity: normalizeNumber(classSource.opacity, classFallback.opacity, 0, 1),
      thickness: legacyDisabled
        ? 0
        : normalizeNumber(classSource.thickness, classFallback.thickness, 0, 6)
    }];
  }));
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
  Object.freeze(["edges", "color"]),
  Object.freeze(["background", "solidColor"]),
  Object.freeze(["background", "linearStart"]),
  Object.freeze(["background", "linearEnd"]),
  Object.freeze(["background", "radialInner"]),
  Object.freeze(["background", "radialOuter"]),
  Object.freeze(["floor", "color"]),
  Object.freeze(["floor", "gridCenterColor"]),
  Object.freeze(["floor", "gridCellColor"]),
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
export const DEFAULT_FLOOR_GRID_SETTINGS = Object.freeze({
  gridCenterColor: "#6b7280",
  gridCellColor: "#cbd5e1",
  gridOpacity: 0.18,
  gridDensity: 1
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

const BEACH_FILL_COLORS = Object.freeze(["#178f9f", "#ef7459"]);

const TERMINAL_FILL_COLORS = Object.freeze(["#0b7a3f"]);

const TERMINAL_EDGE_COLOR = "#66ff99";
const TERMINAL_EDGE_HIGHLIGHT_COLOR = "#b7ffc9";
const TERMINAL_EDGE_CLASS_SETTINGS = Object.freeze({
  feature: Object.freeze({
    opacity: 1,
    thickness: 1.15
  }),
  tangent: Object.freeze({
    opacity: 0.84,
    thickness: 0.95
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

const STUDIO_SHOWROOM_FILL_COLORS = WORKBENCH_FILL_COLORS;
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

function createFloorGridSettings(floorColor, options = {}) {
  const normalizedFloorColor = normalizeColor(floorColor, "#f1f5f9");
  const lightFloor = relativeLuminance(normalizedFloorColor) >= 0.36;
  return {
    gridCenterColor: lightFloor
      ? mixHexColors(normalizedFloorColor, "#0f172a", 0.48)
      : mixHexColors(normalizedFloorColor, "#f8fafc", 0.46),
    gridCellColor: lightFloor
      ? mixHexColors(normalizedFloorColor, "#475569", 0.26)
      : mixHexColors(normalizedFloorColor, "#cbd5e1", 0.22),
    gridOpacity: normalizeNumber(options.opacity, DEFAULT_FLOOR_GRID_SETTINGS.gridOpacity, 0, 1),
    gridDensity: normalizeNumber(
      options.density,
      DEFAULT_FLOOR_GRID_SETTINGS.gridDensity,
      MIN_FLOOR_GRID_DENSITY,
      MAX_FLOOR_GRID_DENSITY
    )
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
  edges: {
    ...CAD_THEME_EDGE_SETTINGS
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
    ...createFloorGridSettings("#edf3f8", { opacity: 0.2 })
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

const STUDIO_SHOWROOM_BASE_THEME_SETTINGS = Object.freeze({
  materials: {
    defaultColor: STUDIO_SHOWROOM_FILL_COLORS[0],
    fillColors: STUDIO_SHOWROOM_FILL_COLORS,
    cycleColors: false,
    overrideSourceColors: false,
    tintMode: "blend",
    tintStrength: 0,
    saturation: 0.96,
    contrast: 1.02,
    brightness: 1.02,
    roughness: 0.82,
    metalness: 0,
    clearcoat: 0.02,
    clearcoatRoughness: 0.78,
    opacity: 1,
    envMapIntensity: 0.55,
    emissiveIntensity: 0
  },
  edges: {
    ...DISABLED_THEME_EDGE_SETTINGS
  },
  background: {
    type: "linear",
    solidColor: "#f7f7f5",
    linearStart: "#ffffff",
    linearEnd: "#e7e7e2",
    linearAngle: 180,
    radialInner: "#ffffff",
    radialOuter: "#e9e9e4"
  },
  floor: {
    mode: THEME_FLOOR_MODES.STAGE,
    color: "#ececea",
    roughness: 0.58,
    reflectivity: 0.22,
    shadowOpacity: 0.32,
    horizonBlend: 0.12,
    ...createFloorGridSettings("#ececea", { opacity: 0.18 })
  },
  environment: {
    enabled: true,
    presetId: "studio-hdri-41",
    intensity: 0.85,
    rotationY: -0.25,
    useAsBackground: false
  },
  lighting: {
    toneMappingExposure: 1.08,
    directional: {
      enabled: true,
      color: "#ffffff",
      intensity: 1.55,
      position: {
        x: -220,
        y: 260,
        z: 260
      }
    },
    spot: {
      enabled: true,
      color: "#ffffff",
      intensity: 0.85,
      angle: 0.58,
      distance: 0,
      position: {
        x: 200,
        y: 150,
        z: 230
      }
    },
    point: {
      enabled: false,
      color: "#ffffff",
      intensity: 0.2,
      distance: 0,
      position: {
        x: -180,
        y: 80,
        z: 140
      }
    },
    ambient: {
      enabled: true,
      color: "#ffffff",
      intensity: 0.22
    },
    hemisphere: {
      enabled: true,
      skyColor: "#ffffff",
      groundColor: "#d8d8d2",
      intensity: 0.72
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
  edges: {
    ...DISABLED_THEME_EDGE_SETTINGS
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
    ...createFloorGridSettings("#0a2238", { opacity: 0.22 })
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
  edges: {
    ...CAD_THEME_EDGE_SETTINGS
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

const BLUE_THEME_SETTINGS = Object.freeze({
  materials: {
    ...DARK_STUDIO_THEME_SETTINGS.materials,
    defaultColor: BLUE_FILL_COLORS[0],
    fillColors: BLUE_FILL_COLORS,
    cycleColors: false
  },
  edges: {
    ...DISABLED_THEME_EDGE_SETTINGS
  },
  background: {
    type: "radial",
    solidColor: "#04131f",
    linearStart: "#07253a",
    linearEnd: "#0b8edc",
    linearAngle: 128,
    radialInner: "#0b8edc",
    radialOuter: "#02070c"
  },
  floor: {
    mode: THEME_FLOOR_MODES.STAGE,
    color: "#06324f",
    roughness: 0.58,
    reflectivity: 0.2,
    shadowOpacity: 0.3,
    horizonBlend: 0.18,
    ...createFloorGridSettings("#06324f", { opacity: 0.24 })
  },
  environment: DARK_STUDIO_THEME_SETTINGS.environment,
  lighting: DARK_STUDIO_THEME_SETTINGS.lighting
});

const PINK_THEME_SETTINGS = Object.freeze({
  materials: {
    ...DARK_STUDIO_THEME_SETTINGS.materials,
    defaultColor: MAGENTA_FILL_COLORS[0],
    fillColors: MAGENTA_FILL_COLORS,
    cycleColors: false
  },
  edges: {
    ...DISABLED_THEME_EDGE_SETTINGS
  },
  background: {
    type: "radial",
    solidColor: "#281323",
    linearStart: "#7a1a52",
    linearEnd: "#301426",
    linearAngle: 140,
    radialInner: "#7f1a55",
    radialOuter: "#25101f"
  },
  floor: {
    mode: THEME_FLOOR_MODES.STAGE,
    color: "#4a1833",
    roughness: 0.56,
    reflectivity: 0.2,
    shadowOpacity: 0.26,
    horizonBlend: 0.22,
    ...createFloorGridSettings("#4a1833", { opacity: 0.24 })
  },
  environment: DARK_STUDIO_THEME_SETTINGS.environment,
  lighting: DARK_STUDIO_THEME_SETTINGS.lighting
});

const CLAY_SUNRISE_THEME_SETTINGS = Object.freeze({
  materials: {
    ...DARK_STUDIO_THEME_SETTINGS.materials,
    defaultColor: CLAY_FILL_COLORS[0],
    fillColors: CLAY_FILL_COLORS,
    cycleColors: false
  },
  edges: {
    ...DISABLED_THEME_EDGE_SETTINGS
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
    color: "#d4a070",
    roughness: 0.72,
    reflectivity: 0.14,
    shadowOpacity: 0.34,
    horizonBlend: 0.12,
    ...createFloorGridSettings("#d4a070", { opacity: 0.18 })
  },
  environment: DARK_STUDIO_THEME_SETTINGS.environment,
  lighting: DARK_STUDIO_THEME_SETTINGS.lighting
});

const BEACH_THEME_SETTINGS = Object.freeze({
  materials: {
    ...CINEMATIC_THEME_SETTINGS.materials,
    defaultColor: BEACH_FILL_COLORS[0],
    fillColors: BEACH_FILL_COLORS,
    cycleColors: true
  },
  edges: {
    ...DISABLED_THEME_EDGE_SETTINGS
  },
  background: {
    type: "linear",
    solidColor: "#dff7f7",
    linearStart: "#fff4d6",
    linearEnd: "#47c5d6",
    linearAngle: 152,
    radialInner: "#fff8e8",
    radialOuter: "#1a8fb5"
  },
  floor: {
    mode: THEME_FLOOR_MODES.STAGE,
    color: "#f2d59b",
    roughness: 0.74,
    reflectivity: 0.18,
    shadowOpacity: 0.2,
    horizonBlend: 0.2,
    ...createFloorGridSettings("#f2d59b", { opacity: 0.18 })
  },
  environment: {
    enabled: true,
    presetId: "studio-hdri-12",
    intensity: 0.36,
    rotationY: -0.18,
    useAsBackground: false
  },
  lighting: {
    toneMappingExposure: 1.18,
    directional: {
      enabled: true,
      color: "#fff7df",
      intensity: 1.3,
      position: {
        x: -220,
        y: 280,
        z: 250
      }
    },
    spot: {
      enabled: true,
      color: "#e4fbff",
      intensity: 0.36,
      angle: 0.72,
      distance: 0,
      position: {
        x: 190,
        y: 210,
        z: 170
      }
    },
    point: {
      enabled: true,
      color: "#ffd08a",
      intensity: 0.24,
      distance: 0,
      position: {
        x: -240,
        y: 110,
        z: -210
      }
    },
    ambient: {
      enabled: true,
      color: "#fff8e6",
      intensity: 0.34
    },
    hemisphere: {
      enabled: true,
      skyColor: "#bff8ff",
      groundColor: "#f2d59b",
      intensity: 1.04
    }
  }
});

const TERMINAL_THEME_SETTINGS = Object.freeze({
  materials: {
    ...DARK_STUDIO_THEME_SETTINGS.materials,
    defaultColor: TERMINAL_FILL_COLORS[0],
    fillColors: TERMINAL_FILL_COLORS,
    cycleColors: false
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
    radialInner: "#062414",
    radialOuter: "#000201"
  },
  floor: {
    mode: THEME_FLOOR_MODES.GRID,
    color: "#020403",
    roughness: 0.58,
    reflectivity: 0.12,
    shadowOpacity: 0.35,
    horizonBlend: 0,
    gridCenterColor: TERMINAL_EDGE_COLOR,
    gridCellColor: "#0c3d22",
    gridOpacity: 0.34,
    gridDensity: 1.15
  },
  environment: DARK_STUDIO_THEME_SETTINGS.environment,
  lighting: DARK_STUDIO_THEME_SETTINGS.lighting
});

const WORKBENCH_BASE_THEME_SETTINGS = Object.freeze({
  ...CINEMATIC_THEME_SETTINGS,
  background: {
    ...CINEMATIC_THEME_SETTINGS.background,
    type: "solid",
    solidColor: CINEMATIC_THEME_SETTINGS.background.linearStart,
    linearEnd: CINEMATIC_THEME_SETTINGS.background.linearStart,
    radialInner: CINEMATIC_THEME_SETTINGS.background.linearStart,
    radialOuter: CINEMATIC_THEME_SETTINGS.background.linearStart
  },
  edges: {
    ...CAD_THEME_EDGE_SETTINGS
  },
  environment: {
    ...CINEMATIC_THEME_SETTINGS.environment,
    enabled: false
  }
});

const WORKBENCH_THEME_SETTINGS = withThemeColorMode(
  WORKBENCH_BASE_THEME_SETTINGS,
  THEME_COLOR_MODES.SYSTEM,
  createThemeModeColors(WORKBENCH_BASE_THEME_SETTINGS, DARKOAL_THEME_SETTINGS)
);

const STUDIO_SHOWROOM_DARK_THEME_SETTINGS = Object.freeze({
  ...STUDIO_SHOWROOM_BASE_THEME_SETTINGS,
  edges: {
    ...STUDIO_SHOWROOM_BASE_THEME_SETTINGS.edges,
    color: DARKOAL_THEME_SETTINGS.edges.color
  },
  background: {
    ...STUDIO_SHOWROOM_BASE_THEME_SETTINGS.background,
    solidColor: DARKOAL_THEME_SETTINGS.background.solidColor,
    linearStart: DARKOAL_THEME_SETTINGS.background.linearStart,
    linearEnd: DARKOAL_THEME_SETTINGS.background.linearEnd,
    radialInner: DARKOAL_THEME_SETTINGS.background.radialInner,
    radialOuter: DARKOAL_THEME_SETTINGS.background.radialOuter
  },
  floor: {
    ...STUDIO_SHOWROOM_BASE_THEME_SETTINGS.floor,
    color: DARKOAL_THEME_SETTINGS.floor.color,
    gridCenterColor: DARKOAL_THEME_SETTINGS.floor.gridCenterColor,
    gridCellColor: DARKOAL_THEME_SETTINGS.floor.gridCellColor
  },
  lighting: {
    ...STUDIO_SHOWROOM_BASE_THEME_SETTINGS.lighting,
    directional: {
      ...STUDIO_SHOWROOM_BASE_THEME_SETTINGS.lighting.directional,
      color: DARKOAL_THEME_SETTINGS.lighting.directional.color
    },
    spot: {
      ...STUDIO_SHOWROOM_BASE_THEME_SETTINGS.lighting.spot,
      color: DARKOAL_THEME_SETTINGS.lighting.spot.color
    },
    point: {
      ...STUDIO_SHOWROOM_BASE_THEME_SETTINGS.lighting.point,
      color: DARKOAL_THEME_SETTINGS.lighting.point.color
    },
    ambient: {
      ...STUDIO_SHOWROOM_BASE_THEME_SETTINGS.lighting.ambient,
      color: DARKOAL_THEME_SETTINGS.lighting.ambient.color
    },
    hemisphere: {
      ...STUDIO_SHOWROOM_BASE_THEME_SETTINGS.lighting.hemisphere,
      skyColor: DARKOAL_THEME_SETTINGS.lighting.hemisphere.skyColor,
      groundColor: DARKOAL_THEME_SETTINGS.lighting.hemisphere.groundColor
    }
  }
});

const STUDIO_SHOWROOM_THEME_SETTINGS = withThemeColorMode(
  STUDIO_SHOWROOM_BASE_THEME_SETTINGS,
  THEME_COLOR_MODES.SYSTEM,
  createThemeModeColors(STUDIO_SHOWROOM_BASE_THEME_SETTINGS, STUDIO_SHOWROOM_DARK_THEME_SETTINGS)
);

const BLUE_THEME_PRESET_SETTINGS = withThemeColorMode(BLUE_THEME_SETTINGS, THEME_COLOR_MODES.DARK);
const PINK_THEME_PRESET_SETTINGS = withThemeColorMode(PINK_THEME_SETTINGS, THEME_COLOR_MODES.DARK);
const CLAY_SUNRISE_THEME_PRESET_SETTINGS = withThemeColorMode(CLAY_SUNRISE_THEME_SETTINGS, THEME_COLOR_MODES.LIGHT);
const BEACH_THEME_PRESET_SETTINGS = withThemeColorMode(BEACH_THEME_SETTINGS, THEME_COLOR_MODES.LIGHT);
const TERMINAL_THEME_PRESET_SETTINGS = withThemeColorMode(TERMINAL_THEME_SETTINGS, THEME_COLOR_MODES.DARK);

export const THEME_PRESETS = Object.freeze([
  {
    id: "workbench",
    label: "Workbench",
    description: "Balanced CAD workbench lighting with system-aware light and dark canvas colors.",
    preview: {
      background: "#fbfdff",
      modelColor: "#b6c4ce",
      accentColor: "#4ea7d8"
    },
    settings: WORKBENCH_THEME_SETTINGS
  },
  {
    id: "studio-showroom",
    label: "Studio",
    description: "Realistic studio lighting with system-aware light and dark showroom surfaces.",
    preview: {
      background: "linear-gradient(135deg, #ffffff 0%, #f4f4f1 58%, #d9d9d4 100%)",
      modelColor: "#111111",
      accentColor: "#b8c3cc"
    },
    settings: STUDIO_SHOWROOM_THEME_SETTINGS
  },
  {
    id: "blue",
    label: "Blue",
    description: "Single cyan fill against deep-navy CAD lighting.",
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
    description: "Single saturated magenta fill against a near-black studio backdrop.",
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
    description: "Single warm clay fill with a soft presentation stage.",
    preview: {
      background: CLAY_FILL_COLORS[0],
      modelColor: CLAY_FILL_COLORS[0],
      accentColor: CLAY_FILL_COLORS[0]
    },
    settings: CLAY_SUNRISE_THEME_PRESET_SETTINGS
  },
  {
    id: "beach",
    label: "Beach",
    description: "Two-color aqua-and-coral fill with warm beach presentation lighting.",
    preview: {
      background: `linear-gradient(135deg, ${BEACH_FILL_COLORS[0]} 0%, ${BEACH_FILL_COLORS[0]} 50%, ${BEACH_FILL_COLORS[1]} 50%, ${BEACH_FILL_COLORS[1]} 100%)`,
      modelColor: BEACH_FILL_COLORS[0],
      accentColor: BEACH_FILL_COLORS[1]
    },
    settings: BEACH_THEME_PRESET_SETTINGS
  },
  {
    id: "terminal",
    label: "Terminal",
    description: "Single terminal-green fill with green CAD edge linework and a dark grid floor.",
    preview: {
      background: TERMINAL_FILL_COLORS[0],
      modelColor: TERMINAL_FILL_COLORS[0],
      accentColor: TERMINAL_FILL_COLORS[0]
    },
    settings: TERMINAL_THEME_PRESET_SETTINGS
  }
]);

const THEME_PRESET_ID_ALIASES = Object.freeze({
  cinematic: "workbench",
  light: "workbench",
  dark: "workbench",
  charcoal: "workbench",
  darkoal: "workbench",
  "dark-2": "workbench"
});

export const DEFAULT_THEME_PRESET_ID = "workbench";

export const DEFAULT_THEME_PRESET = Object.freeze(
  THEME_PRESETS.find((preset) => preset.id === DEFAULT_THEME_PRESET_ID) || THEME_PRESETS[0]
);

export const DEFAULT_THEME_SETTINGS = Object.freeze(DEFAULT_THEME_PRESET.settings);
export const THEMES = THEME_PRESETS;
export const DEFAULT_THEME_ID = DEFAULT_THEME_PRESET_ID;
export const DEFAULT_THEME = DEFAULT_THEME_PRESET;

export function resolveSystemThemePresetId({ prefersDark = false } = {}) {
  return DEFAULT_THEME_PRESET_ID;
}

const PRESET_ID_SET = new Set(ENVIRONMENT_PRESETS.map((preset) => preset.id));
const LEGACY_CINEMATIC_MATERIALS = Object.freeze({
  defaultColor: "#aeb9c3",
  tintStrength: 0.28,
  saturation: 0.42,
  contrast: 1.02,
  brightness: 0.94,
  roughness: 0.46,
  metalness: 0.02,
  clearcoat: 0.18,
  clearcoatRoughness: 0.34,
  opacity: 1,
  envMapIntensity: 0.58
});
const PREVIOUS_CINEMATIC_MATERIALS = Object.freeze({
  defaultColor: "#aeb9c3",
  tintMode: "blend",
  tintStrength: 0.08,
  saturation: 1,
  contrast: 1.04,
  brightness: 1.02,
  roughness: 0.46,
  metalness: 0.02,
  clearcoat: 0.18,
  clearcoatRoughness: 0.34,
  opacity: 1,
  envMapIntensity: 0.58,
  emissiveIntensity: 0.06
});
const DIM_CINEMATIC_MATERIALS = Object.freeze({
  defaultColor: "#aeb9c3",
  tintMode: "blend",
  tintStrength: 0,
  saturation: 1.34,
  contrast: 1.02,
  brightness: 0.82,
  roughness: 0.76,
  metalness: 0,
  clearcoat: 0,
  clearcoatRoughness: 0.72,
  opacity: 1,
  envMapIntensity: 0.08,
  emissiveIntensity: 0.01
});
const LOW_CONTRAST_CINEMATIC_MATERIALS = Object.freeze({
  defaultColor: "#bcc8d4",
  tintMode: "blend",
  tintStrength: 0,
  saturation: 1.18,
  contrast: 1.07,
  brightness: 1.04,
  roughness: 0.58,
  metalness: 0.02,
  clearcoat: 0.12,
  clearcoatRoughness: 0.42,
  opacity: 1,
  envMapIntensity: 0.42,
  emissiveIntensity: 0.02
});
const SOFT_CONTRAST_CINEMATIC_MATERIALS = Object.freeze({
  defaultColor: "#748899",
  tintMode: "blend",
  tintStrength: 0,
  saturation: 1.18,
  contrast: 1.07,
  brightness: 1.04,
  roughness: 0.58,
  metalness: 0.02,
  clearcoat: 0.12,
  clearcoatRoughness: 0.42,
  opacity: 1,
  envMapIntensity: 0.42,
  emissiveIntensity: 0.02
});
const FEATURE_CONTRAST_CINEMATIC_MATERIALS = Object.freeze({
  defaultColor: "#556c7f",
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
});
const LEGACY_CINEMATIC_EDGES = Object.freeze({
  enabled: false,
  color: "#8fa1b5",
  thickness: 1
});
const PREVIOUS_CINEMATIC_EDGES = Object.freeze({
  enabled: true,
  color: "#8fa1b5",
  thickness: 1.65
});
const DIM_CINEMATIC_EDGES = Object.freeze({
  enabled: false,
  color: "#8fa1b5",
  thickness: 1
});
const LOW_CONTRAST_CINEMATIC_EDGES = Object.freeze({
  enabled: false,
  color: "#8fa1b5",
  thickness: 1
});
const LEGACY_CINEMATIC_BACKGROUND = Object.freeze({
  solidColor: "#050711",
  linearStart: "#02040b",
  linearEnd: "#252f47",
  linearAngle: 90,
  radialInner: "#171d30",
  radialOuter: "#02040b"
});
const PREVIOUS_CINEMATIC_BACKGROUND = LEGACY_CINEMATIC_BACKGROUND;
const DIM_CINEMATIC_BACKGROUND = Object.freeze({
  solidColor: "#0a0f18",
  linearStart: "#08111c",
  linearEnd: "#1f2c3d",
  linearAngle: 90,
  radialInner: "#182337",
  radialOuter: "#08111c"
});
const LEGACY_CINEMATIC_FLOOR = Object.freeze({
  mode: THEME_FLOOR_MODES.STAGE,
  color: "#141a29",
  roughness: 0.62,
  reflectivity: 0.22,
  shadowOpacity: 0.24,
  horizonBlend: 0.28
});
const PREVIOUS_CINEMATIC_FLOOR = Object.freeze({
  mode: THEME_FLOOR_MODES.STAGE,
  color: "#141a29",
  roughness: 0.62,
  reflectivity: 0.06,
  shadowOpacity: 0.24,
  horizonBlend: 0.12
});
const DIM_CINEMATIC_FLOOR = Object.freeze({
  mode: THEME_FLOOR_MODES.STAGE,
  color: "#121a24",
  roughness: 0.86,
  reflectivity: 0.06,
  shadowOpacity: 0.24,
  horizonBlend: 0.28
});
const LEGACY_CINEMATIC_ENVIRONMENT = Object.freeze({
  enabled: true,
  presetId: "studio-hdri-43",
  intensity: 0.46,
  rotationY: -0.35,
  useAsBackground: false
});
const DIM_CINEMATIC_ENVIRONMENT = Object.freeze({
  enabled: false,
  presetId: "studio-hdri-43",
  intensity: 0,
  rotationY: -0.35,
  useAsBackground: false
});
const PREVIOUS_CINEMATIC_LIGHTING = Object.freeze({
  toneMappingExposure: 1.2,
  directional: {
    enabled: true,
    color: "#f1f6fb",
    intensity: 2.45,
    position: {
      x: -190,
      y: 300,
      z: 210
    }
  },
  spot: {
    enabled: true,
    color: "#dbeafe",
    intensity: 1.34,
    angle: 0.72,
    distance: 0,
    position: {
      x: 160,
      y: 245,
      z: 126
    }
  },
  point: {
    enabled: true,
    color: "#8fb6d8",
    intensity: 0.34,
    distance: 0,
    position: {
      x: -260,
      y: 95,
      z: -220
    }
  },
  ambient: {
    enabled: true,
    color: "#1e293b",
    intensity: 0.2
  },
  hemisphere: {
    enabled: true,
    skyColor: "#dbe7f3",
    groundColor: "#070a14",
    intensity: 0.68
  }
});
const DIM_CINEMATIC_LIGHTING = Object.freeze({
  toneMappingExposure: 1.03,
  directional: {
    enabled: true,
    color: "#f1f6fb",
    intensity: 1.28,
    position: {
      x: -190,
      y: 300,
      z: 210
    }
  },
  spot: {
    enabled: true,
    color: "#dbeafe",
    intensity: 0.18,
    angle: 0.72,
    distance: 0,
    position: {
      x: 160,
      y: 245,
      z: 126
    }
  },
  point: {
    enabled: true,
    color: "#8fb6d8",
    intensity: 0.08,
    distance: 0,
    position: {
      x: -260,
      y: 95,
      z: -220
    }
  },
  ambient: {
    enabled: true,
    color: "#1e293b",
    intensity: 0.42
  },
  hemisphere: {
    enabled: true,
    skyColor: "#dbe7f3",
    groundColor: "#070a14",
    intensity: 0.92
  }
});

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
    edges: value?.edges || {},
    background: value?.background || {},
    floor: value?.floor || {},
    environment: value?.environment || {},
    lighting: value?.lighting || {}
  });
}

function valuesMatch(value, expected) {
  if (typeof expected === "number") {
    return Math.abs((Number(value) || 0) - expected) < 1e-6;
  }
  if (expected && typeof expected === "object") {
    if (!value || typeof value !== "object") {
      return false;
    }
    return Object.entries(expected).every(([key, nestedExpected]) => (
      valuesMatch(value[key], nestedExpected)
    ));
  }
  return value === expected;
}

function valuesMatchAny(value, expectedValues) {
  return expectedValues.some((expected) => valuesMatch(value, expected));
}

function isMigratableCinematicThemeSettings(settings) {
  const materialMatches = valuesMatchAny(settings?.materials, [
    LEGACY_CINEMATIC_MATERIALS,
    PREVIOUS_CINEMATIC_MATERIALS,
    DIM_CINEMATIC_MATERIALS,
    LOW_CONTRAST_CINEMATIC_MATERIALS,
    SOFT_CONTRAST_CINEMATIC_MATERIALS,
    FEATURE_CONTRAST_CINEMATIC_MATERIALS,
    CINEMATIC_THEME_SETTINGS.materials
  ]);
  const edgeMatches = valuesMatchAny(settings?.edges, [
    LEGACY_CINEMATIC_EDGES,
    PREVIOUS_CINEMATIC_EDGES,
    DIM_CINEMATIC_EDGES,
    LOW_CONTRAST_CINEMATIC_EDGES,
    CINEMATIC_THEME_SETTINGS.edges
  ]);
  const floorMatches = valuesMatchAny(settings?.floor, [
    LEGACY_CINEMATIC_FLOOR,
    PREVIOUS_CINEMATIC_FLOOR,
    DIM_CINEMATIC_FLOOR,
    CINEMATIC_THEME_SETTINGS.floor
  ]);
  const environmentMatches = valuesMatchAny(settings?.environment, [
    LEGACY_CINEMATIC_ENVIRONMENT,
    DIM_CINEMATIC_ENVIRONMENT,
    CINEMATIC_THEME_SETTINGS.environment,
    WORKBENCH_THEME_SETTINGS.environment
  ]);
  const backgroundMatches = valuesMatchAny(settings?.background, [
    LEGACY_CINEMATIC_BACKGROUND,
    PREVIOUS_CINEMATIC_BACKGROUND,
    DIM_CINEMATIC_BACKGROUND,
    CINEMATIC_THEME_SETTINGS.background
  ]);
  const lightingMatches = valuesMatchAny(settings?.lighting, [
    PREVIOUS_CINEMATIC_LIGHTING,
    DIM_CINEMATIC_LIGHTING,
    CINEMATIC_THEME_SETTINGS.lighting
  ]);
  return (
    materialMatches &&
    edgeMatches &&
    backgroundMatches &&
    floorMatches &&
    environmentMatches &&
    lightingMatches
  );
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
  const edges = source.edges && typeof source.edges === "object"
    ? source.edges
    : {};
  const lighting = source.lighting && typeof source.lighting === "object"
    ? source.lighting
    : {};
  const hasMaterialSettings = !!(source.materials && typeof source.materials === "object");
  const missingLegacyTintMode = hasMaterialSettings && !Object.hasOwn(materials, "tintMode");
  const missingLegacyEmissiveIntensity = hasMaterialSettings && !Object.hasOwn(materials, "emissiveIntensity");
  const normalizedDefaultColor = normalizeColor(
    materials.defaultColor || materials.tintColor,
    DEFAULT_THEME_SETTINGS.materials.defaultColor
  );
  const fillColors = normalizeThemeFillColors(materials.fillColors, normalizedDefaultColor);
  const normalizedFloorColor = normalizeColor(floor.color, DEFAULT_THEME_SETTINGS.floor?.color || "#141416");
  const fallbackGridSettings = createFloorGridSettings(normalizedFloorColor);
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
        missingLegacyTintMode ? "multiply" : DEFAULT_THEME_SETTINGS.materials.tintMode
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
        missingLegacyEmissiveIntensity ? 0 : DEFAULT_THEME_SETTINGS.materials.emissiveIntensity,
        0,
        2
      )
    },
    edges: {
      enabled: normalizeBoolean(edges.enabled, DEFAULT_THEME_SETTINGS.edges.enabled),
      contrastMode: normalizeEdgeContrastMode(edges.contrastMode, DEFAULT_THEME_SETTINGS.edges.contrastMode),
      color: normalizeColor(edges.color, DEFAULT_THEME_SETTINGS.edges.color),
      thickness: normalizeNumber(edges.thickness, DEFAULT_THEME_SETTINGS.edges.thickness, 0.5, 6),
      classes: normalizeEdgeClassSettings(edges.classes, DEFAULT_THEME_SETTINGS.edges.classes),
      highlightColor: normalizeColor(
        edges.highlightColor,
        DEFAULT_THEME_SETTINGS.edges.highlightColor || CAD_EDGE_HIGHLIGHT_COLOR
      ),
      highlightOpacity: normalizeNumber(edges.highlightOpacity, DEFAULT_THEME_SETTINGS.edges.highlightOpacity || 1, 0, 1),
      highlightThickness: normalizeNumber(edges.highlightThickness, DEFAULT_THEME_SETTINGS.edges.highlightThickness || 3, 0.5, 6),
      silhouette: normalizeBoolean(edges.silhouette, DEFAULT_THEME_SETTINGS.edges.silhouette || false),
      silhouetteScale: normalizeNumber(edges.silhouetteScale, DEFAULT_THEME_SETTINGS.edges.silhouetteScale || 0.004, 0, 0.04)
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
      mode: normalizeFloorMode(floor.mode, DEFAULT_THEME_SETTINGS.floor?.mode || THEME_FLOOR_MODES.STAGE),
      color: normalizedFloorColor,
      roughness: normalizeNumber(floor.roughness, DEFAULT_THEME_SETTINGS.floor?.roughness ?? 0.72, 0, 1),
      reflectivity: normalizeNumber(floor.reflectivity, DEFAULT_THEME_SETTINGS.floor?.reflectivity ?? 0.12, 0, 1),
      shadowOpacity: normalizeNumber(floor.shadowOpacity, DEFAULT_THEME_SETTINGS.floor?.shadowOpacity ?? 0.45, 0, 1),
      horizonBlend: normalizeNumber(floor.horizonBlend, DEFAULT_THEME_SETTINGS.floor?.horizonBlend ?? 0, 0, 1),
      gridCenterColor: normalizeColor(
        floor.gridCenterColor ?? floor.gridCenter,
        fallbackGridSettings.gridCenterColor
      ),
      gridCellColor: normalizeColor(
        floor.gridCellColor ?? floor.gridCell,
        fallbackGridSettings.gridCellColor
      ),
      gridOpacity: normalizeNumber(floor.gridOpacity, fallbackGridSettings.gridOpacity, 0, 1),
      gridDensity: normalizeNumber(
        floor.gridDensity,
        fallbackGridSettings.gridDensity,
        MIN_FLOOR_GRID_DENSITY,
        MAX_FLOOR_GRID_DENSITY
      )
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

  if (
    !Object.hasOwn(source, "colorMode") &&
    !Object.hasOwn(source, "modeColors") &&
    isMigratableCinematicThemeSettings(normalized)
  ) {
    return normalizeThemeSettings(deepClone(WORKBENCH_THEME_SETTINGS));
  }

  return normalized;
}

function cloneNormalizedThemeSettings(value = DEFAULT_THEME_SETTINGS) {
  return normalizeThemeSettings(JSON.parse(JSON.stringify(value)));
}

export function normalizeThemePresetId(presetId) {
  const normalized = String(presetId || "").trim();
  const canonical = THEME_PRESET_ID_ALIASES[normalized] || normalized;
  return THEME_PRESETS.some((preset) => preset.id === canonical) ? canonical : "";
}

export function getThemePresetById(presetId) {
  const normalizedPresetId = normalizeThemePresetId(presetId);
  return THEME_PRESETS.find((preset) => preset.id === normalizedPresetId) || DEFAULT_THEME_PRESET;
}

export function cloneThemePresetSettings(presetId) {
  return cloneNormalizedThemeSettings(getThemePresetById(presetId).settings);
}

export function cloneThemeSettings(themeId) {
  return cloneThemePresetSettings(themeId);
}

export function getThemePresetIdForSettings(themeSettings) {
  const currentSignature = createThemeSettingsSignature(normalizeThemeSettings(themeSettings));
  for (const preset of THEME_PRESETS) {
    const presetSignature = createThemeSettingsSignature(normalizeThemeSettings(preset.settings));
    if (presetSignature === currentSignature) {
      return preset.id;
    }
  }
  return null;
}

export function getThemeIdForSettings(themeSettings) {
  return getThemePresetIdForSettings(themeSettings);
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

export function inferThemeSettingsSceneTone(themeSettings, options = {}) {
  const normalized = resolveThemeSettingsForColorMode(themeSettings, options);
  const luminance = relativeLuminance(
    normalized.floor?.color,
    DEFAULT_THEME_SETTINGS.floor?.color || DEFAULT_THEME_SETTINGS.background.solidColor
  );
  return luminance >= 0.36 ? "light" : "dark";
}

export function inferThemeSceneTone(themeSettings) {
  return inferThemeSettingsSceneTone(themeSettings);
}

export function resolveThemeSettingsDisplayEdgeSettings(themeSettings) {
  const normalized = resolveThemeSettingsForColorMode(themeSettings);
  const edges = normalized.edges || DEFAULT_THEME_SETTINGS.edges;
  return { ...edges };
}

export function resolveThemeDisplayEdgeSettings(themeSettings) {
  return resolveThemeSettingsDisplayEdgeSettings(themeSettings);
}

export function getEnvironmentPresetById(presetId) {
  return ENVIRONMENT_PRESETS.find((preset) => preset.id === presetId) || ENVIRONMENT_PRESETS[0];
}
