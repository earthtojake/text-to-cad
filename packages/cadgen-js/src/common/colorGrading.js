function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function finiteOr(value, fallback) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

export function resolveColorGrading(materialSettings = {}) {
  return {
    saturation: clamp(finiteOr(materialSettings.saturation, 1), 0, 2.5),
    contrast: clamp(finiteOr(materialSettings.contrast, 1), 0, 2.5),
    brightness: clamp(finiteOr(materialSettings.brightness, 1), 0, 2)
  };
}

/**
 * Mutate a Three-compatible linear RGB color with the shared material grading
 * policy. Keeping the scalar math here makes uniform and vertex source colors
 * honor the same explicit zero values in every renderer.
 */
export function applyColorGrading(color, materialSettings = {}) {
  if (!color) {
    return color;
  }
  const { saturation, contrast, brightness } = resolveColorGrading(materialSettings);
  if (Math.abs(saturation - 1) > 1e-4) {
    const hsl = {};
    color.getHSL(hsl);
    color.setHSL(hsl.h, clamp(hsl.s * saturation, 0, 1), hsl.l);
  }
  color.r = clamp(((color.r - 0.5) * contrast + 0.5) * brightness, 0, 1);
  color.g = clamp(((color.g - 0.5) * contrast + 0.5) * brightness, 0, 1);
  color.b = clamp(((color.b - 0.5) * contrast + 0.5) * brightness, 0, 1);
  return color;
}
