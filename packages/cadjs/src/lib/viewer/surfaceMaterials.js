import { resolveThemeFillColor } from "../themeSettings.js";
import {
  CAD_DISPLAY_MODE,
  displayModeIsWireframe,
  displayModeSurfaceOpacity
} from "../../common/displaySettings.js";
import {
  BASE_VIEWER_THEME,
  createSafeColor,
  getViewerThemeNumber,
  HEX_COLOR_PATTERN
} from "./stageTheme.js";

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function isNumericArray(value, stride = 1) {
  return (
    (Array.isArray(value) || ArrayBuffer.isView(value)) &&
    value.length >= stride &&
    value.length % stride === 0
  );
}

export function shouldUseDisplayVertexColors(meshData) {
  return !!meshData?.has_source_colors && isNumericArray(meshData?.colors, 3);
}

export function partUsesDisplayVertexColors(meshData, part) {
  if (!shouldUseDisplayVertexColors(meshData)) {
    return false;
  }
  if (part && Object.hasOwn(part, "hasSourceColors")) {
    return !!part.hasSourceColors;
  }
  return true;
}

export function createSurfaceMaterial(THREE, viewerTheme, { color, useVertexColors = false } = {}) {
  const opacity = Number.isFinite(Number(viewerTheme?.surfaceOpacity))
    ? Number(viewerTheme.surfaceOpacity)
    : 1;
  return new THREE.MeshPhysicalMaterial({
    color: color || viewerTheme?.surface || BASE_VIEWER_THEME.surface,
    roughness: getViewerThemeNumber(viewerTheme, "surfaceRoughness", BASE_VIEWER_THEME.surfaceRoughness),
    metalness: getViewerThemeNumber(viewerTheme, "surfaceMetalness", BASE_VIEWER_THEME.surfaceMetalness),
    clearcoat: getViewerThemeNumber(viewerTheme, "surfaceClearcoat", BASE_VIEWER_THEME.surfaceClearcoat),
    clearcoatRoughness: getViewerThemeNumber(
      viewerTheme,
      "surfaceClearcoatRoughness",
      BASE_VIEWER_THEME.surfaceClearcoatRoughness
    ),
    side: THREE.DoubleSide,
    vertexColors: useVertexColors,
    transparent: opacity < 0.999,
    opacity,
    emissive: 0x000000,
    emissiveIntensity: 0,
    polygonOffset: false,
    polygonOffsetFactor: 0,
    polygonOffsetUnits: 0
  });
}

export function readSourceColor(THREE, value) {
  const normalized = String(value || "").trim();
  if (!HEX_COLOR_PATTERN.test(normalized)) {
    return null;
  }
  const expanded = normalized.length === 4
    ? `#${normalized[1]}${normalized[1]}${normalized[2]}${normalized[2]}${normalized[3]}${normalized[3]}`
    : normalized;
  return new THREE.Color(expanded);
}

export function shapeSourceColor(THREE, sourceColor, materialSettings = {}, { applyTint = true } = {}) {
  const shaped = (sourceColor || new THREE.Color("#ffffff")).clone();
  const tintStrength = clamp(Number(materialSettings.tintStrength) || 0, 0, 1);
  if (applyTint && tintStrength > 0) {
    const tintColor = createSafeColor(THREE, materialSettings.defaultColor || materialSettings.tintColor, "#ffffff");
    if (materialSettings.tintMode === "blend") {
      shaped.lerp(tintColor, tintStrength);
    } else {
      shaped.lerp(shaped.clone().multiply(tintColor), tintStrength);
    }
  }

  const saturation = clamp(Number(materialSettings.saturation) || 1, 0, 2.5);
  if (Math.abs(saturation - 1) > 1e-4) {
    const hsl = {};
    shaped.getHSL(hsl);
    shaped.setHSL(hsl.h, clamp(hsl.s * saturation, 0, 1), hsl.l);
  }

  const contrast = clamp(Number(materialSettings.contrast) || 1, 0, 2.5);
  const brightness = clamp(Number(materialSettings.brightness) || 1, 0, 2);
  shaped.r = clamp(((shaped.r - 0.5) * contrast + 0.5) * brightness, 0, 1);
  shaped.g = clamp(((shaped.g - 0.5) * contrast + 0.5) * brightness, 0, 1);
  shaped.b = clamp(((shaped.b - 0.5) * contrast + 0.5) * brightness, 0, 1);
  return shaped;
}

export function shapeSourceColorBuffer(THREE, colors, materialSettings = {}) {
  if (!isNumericArray(colors, 3)) {
    return colors;
  }
  const shapedColors = new Float32Array(colors.length);
  const color = new THREE.Color();
  for (let index = 0; index + 2 < colors.length; index += 3) {
    color.setRGB(
      clamp(Number(colors[index]) || 0, 0, 1),
      clamp(Number(colors[index + 1]) || 0, 0, 1),
      clamp(Number(colors[index + 2]) || 0, 0, 1)
    );
    const shaped = shapeSourceColor(THREE, color, materialSettings);
    shapedColors[index] = shaped.r;
    shapedColors[index + 1] = shaped.g;
    shapedColors[index + 2] = shaped.b;
  }
  return shapedColors;
}

export function createMaterialFillColor(THREE, materialSettings = {}, fillIndex = 0) {
  return createSafeColor(
    THREE,
    resolveThemeFillColor(materialSettings, fillIndex),
    materialSettings?.defaultColor || BASE_VIEWER_THEME.surface
  );
}

export function resolveMaterialFillBaseColor(THREE, materialSettings = {}, fillIndex = 0) {
  return shapeSourceColor(
    THREE,
    createMaterialFillColor(THREE, materialSettings, fillIndex),
    materialSettings,
    { applyTint: false }
  );
}

export function resolveSourceBaseColor(THREE, {
  hasVertexColors = false,
  sourceColor = null,
  materialSettings,
  fallbackColor = "#ffffff",
  fillIndex = 0,
  forceFill = false
}) {
  if (forceFill) {
    return resolveMaterialFillBaseColor(THREE, materialSettings, fillIndex);
  }
  if (hasVertexColors) {
    return new THREE.Color("#ffffff");
  }
  if (!sourceColor) {
    return resolveMaterialFillBaseColor(THREE, {
      ...materialSettings,
      defaultColor: fallbackColor || materialSettings?.defaultColor
    }, fillIndex);
  }
  return shapeSourceColor(THREE, sourceColor, materialSettings);
}

export function applyMaterialSettingsToRecord(THREE, record, materialSettings, {
  displayMode = CAD_DISPLAY_MODE.SOLID
} = {}) {
  if (!record?.material || !materialSettings) {
    return;
  }
  const wireframeMode = displayModeIsWireframe(displayMode);
  const forceFill = materialSettings.overrideSourceColors === true || wireframeMode;
  const hasVertexColors = !forceFill && !!record.hasVertexColors;
  const nextUseVertexColors = hasVertexColors;
  record.useVertexColors = nextUseVertexColors;
  record.baseColor = resolveSourceBaseColor(THREE, {
    hasVertexColors,
    sourceColor: forceFill ? null : record.sourceColor || null,
    materialSettings,
    fallbackColor: materialSettings?.defaultColor || BASE_VIEWER_THEME.surface,
    fillIndex: record.fillIndex || 0,
    forceFill
  });
  record.material.vertexColors = nextUseVertexColors;
  record.material.roughness = clamp(Number(materialSettings.roughness) || 0, 0, 1);
  record.material.metalness = clamp(Number(materialSettings.metalness) || 0, 0, 1);
  record.material.clearcoat = clamp(Number(materialSettings.clearcoat) || 0, 0, 1);
  record.material.clearcoatRoughness = clamp(Number(materialSettings.clearcoatRoughness) || 0, 0, 1);
  record.baseOpacity = clamp(displayModeSurfaceOpacity(displayMode, Number(materialSettings.opacity) || 0), 0, 1);
  record.material.opacity = record.baseOpacity;
  record.material.transparent = wireframeMode || record.baseOpacity < 0.999;
  record.material.depthWrite = displayMode === CAD_DISPLAY_MODE.TRANSPARENT || wireframeMode
    ? false
    : record.baseOpacity >= 0.999;
  record.material.envMapIntensity = Math.max(Number(materialSettings.envMapIntensity) || 0, 0);
  if (record.material.color && record.baseColor) {
    record.material.color.copy(record.baseColor);
  }
  record.baseEmissiveIntensity = clamp(Number(materialSettings.emissiveIntensity) || 0, 0, 2);
  record.baseEmissiveColor = record.baseColor ? record.baseColor.clone() : null;
  if ("emissive" in record.material && record.material.emissive) {
    if (record.baseEmissiveColor && record.baseEmissiveIntensity > 0) {
      record.material.emissive.copy(record.baseEmissiveColor);
    } else {
      record.material.emissive.set(0x000000);
    }
    record.material.emissiveIntensity = record.baseEmissiveIntensity;
  }
  record.material.needsUpdate = true;
}
