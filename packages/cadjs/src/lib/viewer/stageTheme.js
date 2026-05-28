import { THEME_FLOOR_MODES } from "../themeSettings.js";
import {
  clampSceneModelRadius,
  VIEWER_SCENE_SCALE,
  getLightingScopeRadius,
  getSceneScaleSettings
} from "./sceneScale.js";

export const BASE_VIEWER_THEME = {
  sceneBackground: "#09090b",
  surface: "#f4f4f5",
  surfaceRoughness: 0.92,
  surfaceMetalness: 0.03,
  surfaceClearcoat: 0,
  surfaceClearcoatRoughness: 0.6,
  edge: "#18181b",
  edgeThickness: 1,
  edgeOpacity: 0.84,
  selected: "#2563eb",
  hover: "#0ea5e9",
  gridCenter: "#3f3f46",
  gridCell: "#27272a",
  gridOpacity: 0.16,
  stageFloorColor: "#141416",
  stageFloorOpacity: 0.78,
  stageFloorRoughness: 0.92,
  stageFloorMetalness: 0,
  stageFloorTransmission: 0,
  stageFloorIor: 1.35,
  stageFloorThickness: 0.035,
  stageFloorAttenuationDistance: 4,
  viewPlanePalette: {
    axis: {
      x: {
        front: [250, 88, 79],
        back: [122, 32, 28]
      },
      y: {
        front: [92, 233, 123],
        back: [30, 99, 46]
      },
      z: {
        front: [84, 131, 255],
        back: [30, 53, 126]
      }
    },
    center: {
      fill: [252, 215, 74],
      stroke: [255, 235, 153]
    },
    shell: {
      inner: [24, 31, 48],
      outer: [8, 12, 20],
      stroke: [148, 163, 184]
    }
  }
};

export const THEME_BACKGROUND_TYPES = {
  SOLID: "solid",
  LINEAR: "linear",
  RADIAL: "radial",
  TRANSPARENT: "transparent"
};

export const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}){1,2}$/;

const BACKGROUND_TEXTURE_SIZE = 1024;
const FLOOR_GLOW_TEXTURE_SIZE = 512;
const MIN_WIREFRAME_EDGE_CONTRAST = 3;
const WIREFRAME_LIGHT_EDGE_COLOR = "#dbeafe";
const WIREFRAME_DARK_EDGE_COLOR = "#111827";

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function normalizeHexColor(value, fallback = "") {
  const normalized = String(value || "").trim();
  if (!HEX_COLOR_PATTERN.test(normalized)) {
    return fallback;
  }
  return normalized.length === 4
    ? `#${normalized[1]}${normalized[1]}${normalized[2]}${normalized[2]}${normalized[3]}${normalized[3]}`.toLowerCase()
    : normalized.toLowerCase();
}

function hexChannelToLinear(value) {
  const srgb = value / 255;
  return srgb <= 0.03928
    ? srgb / 12.92
    : ((srgb + 0.055) / 1.055) ** 2.4;
}

function relativeLuminance(value) {
  const color = normalizeHexColor(value, "#000000");
  const red = parseInt(color.slice(1, 3), 16);
  const green = parseInt(color.slice(3, 5), 16);
  const blue = parseInt(color.slice(5, 7), 16);
  return (
    0.2126 * hexChannelToLinear(red) +
    0.7152 * hexChannelToLinear(green) +
    0.0722 * hexChannelToLinear(blue)
  );
}

function contrastRatio(colorA, colorB) {
  const luminanceA = relativeLuminance(colorA);
  const luminanceB = relativeLuminance(colorB);
  const lighter = Math.max(luminanceA, luminanceB);
  const darker = Math.min(luminanceA, luminanceB);
  return (lighter + 0.05) / (darker + 0.05);
}

function minimumContrast(color, backgroundColors) {
  const normalizedBackgrounds = backgroundColors
    .map((backgroundColor) => normalizeHexColor(backgroundColor, ""))
    .filter(Boolean);
  if (!normalizedBackgrounds.length) {
    return Infinity;
  }
  return Math.min(...normalizedBackgrounds.map((backgroundColor) => contrastRatio(color, backgroundColor)));
}

function wireframeBackgroundColors(themeSettings = {}, viewerTheme = BASE_VIEWER_THEME) {
  const background = themeSettings?.background || {};
  const backgroundType = String(background.type || "").trim().toLowerCase();
  const colors = [];
  if (backgroundType === THEME_BACKGROUND_TYPES.LINEAR) {
    colors.push(background.linearStart, background.linearEnd);
  } else if (backgroundType === THEME_BACKGROUND_TYPES.RADIAL) {
    colors.push(background.radialInner, background.radialOuter);
  } else if (backgroundType === THEME_BACKGROUND_TYPES.SOLID) {
    colors.push(background.solidColor);
  }
  const normalizedColors = colors
    .map((backgroundColor) => normalizeHexColor(backgroundColor, ""))
    .filter(Boolean);
  return normalizedColors.length
    ? normalizedColors
    : [viewerTheme?.sceneBackground, BASE_VIEWER_THEME.sceneBackground];
}

export function resolveWireframeEdgeColor({
  edgeColor = "",
  themeSettings = {},
  viewerTheme = BASE_VIEWER_THEME,
  minimumContrastRatio = MIN_WIREFRAME_EDGE_CONTRAST
} = {}) {
  const normalizedEdgeColor = normalizeHexColor(edgeColor, "");
  const backgroundColors = wireframeBackgroundColors(themeSettings, viewerTheme);
  if (
    normalizedEdgeColor &&
    minimumContrast(normalizedEdgeColor, backgroundColors) >= minimumContrastRatio
  ) {
    return normalizedEdgeColor;
  }
  return minimumContrast(WIREFRAME_LIGHT_EDGE_COLOR, backgroundColors) >=
    minimumContrast(WIREFRAME_DARK_EDGE_COLOR, backgroundColors)
    ? WIREFRAME_LIGHT_EDGE_COLOR
    : WIREFRAME_DARK_EDGE_COLOR;
}

export function getViewerThemeValue(viewerTheme, key, fallback) {
  const value = viewerTheme?.[key];
  return value ?? BASE_VIEWER_THEME[key] ?? fallback;
}

export function getViewerThemeNumber(viewerTheme, key, fallback) {
  const value = Number(getViewerThemeValue(viewerTheme, key, fallback));
  return Number.isFinite(value) ? value : fallback;
}

export function normalizeFloorMode(value, fallback = THEME_FLOOR_MODES.STAGE) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "glass") {
    return THEME_FLOOR_MODES.STAGE;
  }
  return Object.values(THEME_FLOOR_MODES).includes(normalized)
    ? normalized
    : fallback;
}

export function resolveFloorMode(floorSettings = {}) {
  return normalizeFloorMode(floorSettings?.mode);
}

function toThemeArray(value) {
  if (Array.isArray(value)) {
    return value.filter(Boolean);
  }
  return value ? [value] : [];
}

function colorToRgba(THREE, value, alpha = 1) {
  const color = new THREE.Color(value || "#000000");
  return `rgba(${Math.round(color.r * 255)}, ${Math.round(color.g * 255)}, ${Math.round(color.b * 255)}, ${clamp(alpha, 0, 1)})`;
}

export function normalizeGradientStops(stops) {
  const filteredStops = toThemeArray(stops);
  if (!filteredStops.length) {
    return [];
  }
  return filteredStops
    .map((stop, index) => {
      if (typeof stop === "string") {
        return {
          offset: filteredStops.length === 1 ? 0 : index / (filteredStops.length - 1),
          color: stop
        };
      }
      const fallbackOffset = filteredStops.length === 1 ? 0 : index / (filteredStops.length - 1);
      const offset = Number(stop?.offset);
      return {
        offset: Number.isFinite(offset) ? clamp(offset, 0, 1) : fallbackOffset,
        color: stop?.color || stop?.value || "#000000"
      };
    })
    .sort((left, right) => left.offset - right.offset);
}

export function createSceneBackgroundTexture(THREE, viewerTheme, themeBackground = null) {
  const backgroundType = String(themeBackground?.type || "").trim().toLowerCase();
  const useThemeBackground = !!backgroundType;
  const gradientStops = useThemeBackground
    ? (
      backgroundType === THEME_BACKGROUND_TYPES.LINEAR
        ? [
          { offset: 0, color: themeBackground.linearStart || "#000000" },
          { offset: 1, color: themeBackground.linearEnd || "#ffffff" }
        ]
        : backgroundType === THEME_BACKGROUND_TYPES.RADIAL
          ? [
            { offset: 0, color: themeBackground.radialInner || "#000000" },
            { offset: 1, color: themeBackground.radialOuter || "#ffffff" }
          ]
          : []
    )
    : normalizeGradientStops(viewerTheme?.sceneBackgroundGradient);
  const glowLayers = useThemeBackground ? [] : toThemeArray(viewerTheme?.sceneBackgroundGlow);
  if (!gradientStops.length && !glowLayers.length) {
    return null;
  }

  const canvas = document.createElement("canvas");
  canvas.width = BACKGROUND_TEXTURE_SIZE;
  canvas.height = BACKGROUND_TEXTURE_SIZE;
  const context = canvas.getContext("2d");
  if (!context) {
    return null;
  }

  context.fillStyle = useThemeBackground
    ? themeBackground.solidColor || BASE_VIEWER_THEME.sceneBackground
    : viewerTheme?.sceneBackground || BASE_VIEWER_THEME.sceneBackground;
  context.fillRect(0, 0, canvas.width, canvas.height);

  if (gradientStops.length) {
    if (backgroundType === THEME_BACKGROUND_TYPES.RADIAL) {
      const radialGradient = context.createRadialGradient(
        canvas.width / 2,
        canvas.height / 2,
        canvas.width * 0.1,
        canvas.width / 2,
        canvas.height / 2,
        canvas.width * 0.75
      );
      for (const stop of gradientStops) {
        radialGradient.addColorStop(stop.offset, stop.color);
      }
      context.fillStyle = radialGradient;
      context.fillRect(0, 0, canvas.width, canvas.height);
    } else {
      const angleDeg = Number.isFinite(Number(themeBackground?.linearAngle)) ? Number(themeBackground.linearAngle) : 180;
      const angleRad = (angleDeg * Math.PI) / 180;
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;
      const radius = Math.max(canvas.width, canvas.height);
      const x1 = cx - Math.cos(angleRad) * radius;
      const y1 = cy - Math.sin(angleRad) * radius;
      const x2 = cx + Math.cos(angleRad) * radius;
      const y2 = cy + Math.sin(angleRad) * radius;
      const linearGradient = context.createLinearGradient(x1, y1, x2, y2);
      for (const stop of gradientStops) {
        linearGradient.addColorStop(stop.offset, stop.color);
      }
      context.fillStyle = linearGradient;
      context.fillRect(0, 0, canvas.width, canvas.height);
    }
  }

  for (const glowLayer of glowLayers) {
    const resolvedX = Number(glowLayer?.x);
    const resolvedY = Number(glowLayer?.y);
    const x = Number.isFinite(resolvedX) ? clamp(resolvedX, 0, 1) : 0.5;
    const y = Number.isFinite(resolvedY) ? clamp(resolvedY, 0, 1) : 0.5;
    const radius = Math.max(Number(glowLayer?.radius) || 0, 0.08);
    const opacity = clamp(Number(glowLayer?.opacity) || 0, 0, 1);
    if (opacity <= 0) {
      continue;
    }
    const centerX = canvas.width * x;
    const centerY = canvas.height * y;
    const outerRadius = canvas.width * radius;
    const glow = context.createRadialGradient(centerX, centerY, 0, centerX, centerY, outerRadius);
    glow.addColorStop(0, colorToRgba(THREE, glowLayer?.color || "#ffffff", opacity));
    glow.addColorStop(0.5, colorToRgba(THREE, glowLayer?.color || "#ffffff", opacity * 0.3));
    glow.addColorStop(1, colorToRgba(THREE, glowLayer?.color || "#ffffff", 0));
    context.fillStyle = glow;
    context.fillRect(0, 0, canvas.width, canvas.height);
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;
  return texture;
}

export function disposeTexture(texture) {
  texture?.dispose?.();
}

export function applySceneBackground(runtime, viewerTheme, themeBackground = null) {
  if (!runtime?.THREE || !runtime?.scene) {
    return;
  }
  if (String(themeBackground?.type || "").toLowerCase() === THEME_BACKGROUND_TYPES.TRANSPARENT) {
    disposeTexture(runtime.sceneBackgroundTexture);
    runtime.sceneBackgroundTexture = null;
    runtime.scene.background = null;
    runtime.renderer?.setClearAlpha?.(0);
    return;
  }
  runtime.renderer?.setClearAlpha?.(1);
  disposeTexture(runtime.sceneBackgroundTexture);
  runtime.sceneBackgroundTexture = createSceneBackgroundTexture(runtime.THREE, viewerTheme, themeBackground);
  if (runtime.sceneBackgroundTexture) {
    runtime.scene.background = runtime.sceneBackgroundTexture;
    return;
  }
  runtime.scene.background = new runtime.THREE.Color(
    themeBackground?.solidColor || viewerTheme.sceneBackground || BASE_VIEWER_THEME.sceneBackground
  );
}

export function createSafeColor(THREE, value, fallback = "#000000") {
  const normalizedValue = String(value || "").trim();
  const normalizedFallback = String(fallback || "#000000").trim();
  const colorValue = HEX_COLOR_PATTERN.test(normalizedValue) ? normalizedValue : normalizedFallback;
  try {
    return new THREE.Color(colorValue);
  } catch {
    return new THREE.Color(HEX_COLOR_PATTERN.test(normalizedFallback) ? normalizedFallback : "#000000");
  }
}

export function resolveBackgroundFloorColor(THREE, themeBackground = {}, viewerTheme = BASE_VIEWER_THEME) {
  const fallbackColor = viewerTheme?.stageFloorColor || viewerTheme?.sceneBackground || BASE_VIEWER_THEME.stageFloorColor;
  const backgroundType = String(themeBackground?.type || "").trim().toLowerCase();
  if (backgroundType === THEME_BACKGROUND_TYPES.LINEAR) {
    return createSafeColor(THREE, themeBackground.linearStart, fallbackColor)
      .lerp(createSafeColor(THREE, themeBackground.linearEnd, fallbackColor), 0.7);
  }
  if (backgroundType === THEME_BACKGROUND_TYPES.RADIAL) {
    return createSafeColor(THREE, themeBackground.radialInner, fallbackColor)
      .lerp(createSafeColor(THREE, themeBackground.radialOuter, fallbackColor), 0.72);
  }
  if (backgroundType === THEME_BACKGROUND_TYPES.SOLID) {
    return createSafeColor(THREE, themeBackground.solidColor, fallbackColor);
  }
  return createSafeColor(THREE, fallbackColor, BASE_VIEWER_THEME.stageFloorColor);
}

export function resolveStageFloorGlassFactor(themeSettings = {}) {
  const materials = themeSettings?.materials || {};
  const environment = themeSettings?.environment || {};
  const roughness = clamp(Number(materials.roughness) || 0, 0, 1);
  const clearcoat = clamp(Number(materials.clearcoat) || 0, 0, 1);
  const envSignal = environment?.enabled
    ? clamp(((Number(materials.envMapIntensity) || 0) * (Number(environment.intensity) || 0)) / 3, 0, 1)
    : 0;
  return clamp((clearcoat * 0.5) + ((1 - roughness) * 0.25) + (envSignal * 0.35), 0, 1);
}

export function resolveStageFloorColor(THREE, viewerTheme, themeSettings = {}) {
  const explicitFloorColor = String(themeSettings?.floor?.color || "").trim();
  if (HEX_COLOR_PATTERN.test(explicitFloorColor)) {
    return createSafeColor(THREE, explicitFloorColor, viewerTheme?.stageFloorColor || BASE_VIEWER_THEME.stageFloorColor);
  }

  const backgroundColor = resolveBackgroundFloorColor(THREE, themeSettings?.background, viewerTheme);
  const glassFactor = resolveStageFloorGlassFactor(themeSettings);
  if (glassFactor >= 0.35) {
    const backgroundHsl = {};
    backgroundColor.getHSL(backgroundHsl);
    const floorColor = backgroundColor.clone();
    const lightness = backgroundHsl.l < 0.42
      ? clamp(backgroundHsl.l + 0.012, 0.06, 0.14)
      : clamp(backgroundHsl.l - 0.045, 0.36, 0.78);
    floorColor.setHSL(backgroundHsl.h, clamp(backgroundHsl.s * 0.14, 0, 0.04), lightness);
    return floorColor;
  }

  const groundColor = createSafeColor(
    THREE,
    themeSettings?.lighting?.hemisphere?.groundColor,
    viewerTheme?.stageFloorColor || BASE_VIEWER_THEME.stageFloorColor
  );
  const defaultColor = createSafeColor(THREE, themeSettings?.materials?.defaultColor, "#ffffff");
  const floorColor = backgroundColor.clone()
    .lerp(groundColor, 0.42 - (glassFactor * 0.24))
    .lerp(defaultColor, 0.07 - (glassFactor * 0.04))
    .lerp(backgroundColor, glassFactor * 0.5);
  const floorHsl = {};
  const backgroundHsl = {};
  floorColor.getHSL(floorHsl);
  backgroundColor.getHSL(backgroundHsl);
  const lightness = backgroundHsl.l < 0.42
    ? clamp(
      Math.max(floorHsl.l, backgroundHsl.l + (0.055 - (glassFactor * 0.035))),
      0.1 - (glassFactor * 0.04),
      0.34 - (glassFactor * 0.13)
    )
    : clamp(Math.min(floorHsl.l, backgroundHsl.l - 0.075), 0.38, 0.78);
  floorColor.setHSL(
    floorHsl.h,
    clamp(floorHsl.s * (0.58 - (glassFactor * 0.2)), 0.025, 0.38),
    lightness
  );
  return floorColor;
}

export function getStageFloorSetting(themeSettings, key, fallback, min = 0, max = 1) {
  const value = Number(themeSettings?.floor?.[key]);
  return Number.isFinite(value) ? clamp(value, min, max) : fallback;
}

export function createStageFloorGlowTexture(THREE, color, opacity) {
  const resolvedOpacity = clamp(Number(opacity) || 0, 0, 1);
  if (resolvedOpacity <= 0.001 || typeof document === "undefined") {
    return null;
  }

  const canvas = document.createElement("canvas");
  canvas.width = FLOOR_GLOW_TEXTURE_SIZE;
  canvas.height = FLOOR_GLOW_TEXTURE_SIZE;
  const context = canvas.getContext("2d");
  if (!context) {
    return null;
  }

  const center = FLOOR_GLOW_TEXTURE_SIZE / 2;
  const gradient = context.createRadialGradient(center, center, 0, center, center, center);
  gradient.addColorStop(0, colorToRgba(THREE, color, resolvedOpacity));
  gradient.addColorStop(0.28, colorToRgba(THREE, color, resolvedOpacity * 0.56));
  gradient.addColorStop(0.62, colorToRgba(THREE, color, resolvedOpacity * 0.16));
  gradient.addColorStop(1, colorToRgba(THREE, color, 0));
  context.fillStyle = gradient;
  context.fillRect(0, 0, canvas.width, canvas.height);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;
  return texture;
}

export function createStageFloorPlane(THREE, viewerTheme, themeSettings, size, floorZ, lift = 0) {
  const glassFactor = resolveStageFloorGlassFactor(themeSettings);
  const horizonBlend = getStageFloorSetting(themeSettings, "horizonBlend", 0, 0, 1);
  const reflectivity = getStageFloorSetting(themeSettings, "reflectivity", 0.12, 0, 1);
  const floorColor = resolveStageFloorColor(THREE, viewerTheme, themeSettings);
  const roughness = getStageFloorSetting(
    themeSettings,
    "roughness",
    clamp(getViewerThemeNumber(viewerTheme, "stageFloorRoughness", 0.92) - (glassFactor * 0.48), 0.16, 1),
    0,
    1
  );
  const opacity = horizonBlend <= 0.001
    ? 1
    : clamp(
      (getViewerThemeNumber(viewerTheme, "stageFloorOpacity", 0.78) - (glassFactor * 0.02)) * (1 - (horizonBlend * 0.3)),
      0.62,
      1
    );
  const floorHsl = {};
  floorColor.getHSL(floorHsl);
  const isDarkFloor = floorHsl.l < 0.18;
  const specularColor = isDarkFloor
    ? floorColor.clone().lerp(new THREE.Color("#1c5f8f"), 0.5)
    : new THREE.Color("#ffffff");
  const specularIntensity = isDarkFloor
    ? clamp(reflectivity * 0.38, 0, 0.06)
    : clamp(reflectivity * 1.4, 0.04, 0.36);
  const clearcoat = isDarkFloor
    ? clamp(reflectivity * 0.22, 0, 0.05)
    : clamp((reflectivity * 0.58) + (glassFactor * 0.12), 0, 0.9);
  const clearcoatRoughness = isDarkFloor
    ? clamp(Math.max(roughness * 0.95, 0.35), 0.35, 0.85)
    : clamp(
      roughness * 0.62,
      0.04,
      0.8
    );
  const envMapIntensity = clamp(
    (
      Number(themeSettings?.materials?.envMapIntensity || 0) *
        (themeSettings?.environment?.enabled ? Number(themeSettings?.environment?.intensity || 0) : 0) *
        (0.08 + (glassFactor * 0.1))
    ) + (reflectivity * 0.48),
    0,
    1.15
  );
  const material = new THREE.MeshPhysicalMaterial({
    color: floorColor,
    roughness,
    metalness: clamp(getViewerThemeNumber(viewerTheme, "stageFloorMetalness", 0) + (reflectivity * 0.06), 0, 0.18),
    clearcoat,
    clearcoatRoughness,
    reflectivity,
    specularColor,
    specularIntensity,
    transmission: clamp(
      getViewerThemeNumber(viewerTheme, "stageFloorTransmission", BASE_VIEWER_THEME.stageFloorTransmission) +
        (glassFactor * 0.005),
      0,
      0.02
    ),
    ior: getViewerThemeNumber(viewerTheme, "stageFloorIor", BASE_VIEWER_THEME.stageFloorIor),
    thickness: getViewerThemeNumber(
      viewerTheme,
      "stageFloorThickness",
      BASE_VIEWER_THEME.stageFloorThickness
    ),
    attenuationDistance: getViewerThemeNumber(
      viewerTheme,
      "stageFloorAttenuationDistance",
      BASE_VIEWER_THEME.stageFloorAttenuationDistance
    ),
    transparent: opacity < 0.999,
    opacity,
    side: THREE.FrontSide,
    depthWrite: opacity >= 0.999,
    envMapIntensity
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1, 1, 1), material);
  mesh.position.set(0, 0, floorZ + lift);
  mesh.scale.set(size, size, 1);
  mesh.receiveShadow = false;
  mesh.castShadow = false;
  mesh.renderOrder = -3;
  return mesh;
}

export function createStageFloorGlowPlane(THREE, themeSettings, lightingScopeRadius, size, floorZ, sceneScaleMode, lift = 0.008) {
  const spotLight = themeSettings?.lighting?.spot || {};
  if (spotLight.enabled === false) {
    return null;
  }

  const reflectivity = getStageFloorSetting(themeSettings, "reflectivity", 0.12, 0, 1);
  const shadowOpacity = getStageFloorSetting(themeSettings, "shadowOpacity", 0.45, 0, 1);
  const spotIntensity = Math.max(Number(spotLight.intensity) || 0, 0);
  const glowOpacity = clamp(0.025 + (spotIntensity * 0.11) + (reflectivity * 0.32) - (shadowOpacity * 0.06), 0, 0.36);
  const texture = createStageFloorGlowTexture(THREE, spotLight.color || "#ffffff", glowOpacity);
  if (!texture) {
    return null;
  }

  const sceneScaleSettings = getSceneScaleSettings(sceneScaleMode);
  const safeLightingRadius = Math.max(Number(lightingScopeRadius) || 0, getLightingScopeRadius(sceneScaleMode));
  const glowSize = Math.min(
    size * 0.24,
    Math.max(safeLightingRadius * 8, sceneScaleSettings.minGridSize * 3.4)
  );
  const material = new THREE.MeshBasicMaterial({
    map: texture,
    transparent: true,
    opacity: 1,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
    side: THREE.FrontSide,
    toneMapped: true
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1, 1, 1), material);
  mesh.position.set(0, 0, floorZ + lift);
  mesh.scale.set(glowSize * 1.45, glowSize, 1);
  mesh.receiveShadow = false;
  mesh.castShadow = false;
  mesh.renderOrder = -2.8;
  return mesh;
}

export function createStageShadowPlane(THREE, themeSettings, size, floorZ, lift = 0.01) {
  const opacity = getStageFloorSetting(themeSettings, "shadowOpacity", 0.45, 0, 1);
  if (opacity <= 0.001) {
    return null;
  }
  const material = new THREE.ShadowMaterial({
    color: 0x000000,
    opacity,
    transparent: true,
    depthWrite: false
  });
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1, 1, 1), material);
  mesh.position.set(0, 0, floorZ + lift);
  mesh.scale.set(size, size, 1);
  mesh.receiveShadow = true;
  mesh.castShadow = false;
  mesh.renderOrder = -2;
  return mesh;
}

export function updateSpotLightTarget(runtime) {
  if (!runtime?.spotLight?.target?.position) {
    return;
  }
  const floorZ = Number(runtime.gridFloorZ);
  const targetZ = runtime.floorMode !== THEME_FLOOR_MODES.NONE && Number.isFinite(floorZ) ? floorZ : 0;
  runtime.spotLight.target.position.set(0, 0, targetZ);
  runtime.spotLight.target.updateMatrixWorld?.();
}

export function getStageFloorSize(radius, sceneScaleMode = VIEWER_SCENE_SCALE.CAD) {
  const sceneScaleSettings = getSceneScaleSettings(sceneScaleMode);
  const safeRadius = clampSceneModelRadius(radius, sceneScaleMode);
  return Math.max(sceneScaleSettings.minGridSize * 80, safeRadius * 160);
}
