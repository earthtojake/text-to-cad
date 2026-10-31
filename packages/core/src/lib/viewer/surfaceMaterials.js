import { resolveThemeFillColor } from "../themeSettings.js";
import { applyColorGrading } from "../../common/colorGrading.js";
import {
  BASE_VIEWER_THEME,
  createSafeColor,
  HEX_COLOR_PATTERN
} from "./stageTheme.js";

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
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
    const tintColor = createSafeColor(THREE, materialSettings.defaultColor, "#ffffff");
    if (materialSettings.tintMode === "blend") {
      shaped.lerp(tintColor, tintStrength);
    } else {
      shaped.lerp(shaped.clone().multiply(tintColor), tintStrength);
    }
  }

  return applyColorGrading(shaped, materialSettings);
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
