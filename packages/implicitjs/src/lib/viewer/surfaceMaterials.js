import {
  BASE_VIEWER_THEME,
  HEX_COLOR_PATTERN
} from "./stageTheme.js";

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function firstThemeFillColor(materialSettings = {}, fallback = BASE_VIEWER_THEME.surface) {
  const fillColors = Array.isArray(materialSettings.fillColors) ? materialSettings.fillColors : [];
  return String(fillColors[0] || materialSettings.defaultColor || fallback || BASE_VIEWER_THEME.surface);
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
    const tintColor = readSourceColor(THREE, materialSettings.defaultColor || materialSettings.tintColor) || new THREE.Color("#ffffff");
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

export function resolveSourceBaseColor(THREE, {
  hasVertexColors = false,
  sourceColor = null,
  materialSettings = {},
  fallbackColor = BASE_VIEWER_THEME.surface,
  forceFill = false
} = {}) {
  if (forceFill || !sourceColor) {
    const fillColor = readSourceColor(
      THREE,
      firstThemeFillColor(materialSettings, fallbackColor)
    ) || new THREE.Color(fallbackColor || BASE_VIEWER_THEME.surface);
    return shapeSourceColor(THREE, fillColor, materialSettings, { applyTint: false });
  }
  if (hasVertexColors) {
    return new THREE.Color("#ffffff");
  }
  return shapeSourceColor(THREE, sourceColor, materialSettings);
}
