export const DEFAULT_IMPLICIT_GRAPHICS_SETTINGS = Object.freeze({
  resolutionScale: 2,
  interactionResolutionScale: 1.25,
  detail: 1.25,
  normalSmoothing: 1,
  modelColors: true,
  shadows: true,
  ambientOcclusion: true,
  rimLight: true
});

export const IMPLICIT_GRAPHICS_LIMITS = Object.freeze({
  resolutionScale: Object.freeze({ min: 0.5, max: 5, step: 0.05 }),
  interactionResolutionScale: Object.freeze({ min: 0.25, max: 4, step: 0.05 }),
  detail: Object.freeze({ min: 0.25, max: 8, step: 0.05 }),
  normalSmoothing: Object.freeze({ min: 0.25, max: 5, step: 0.05 })
});

function clampNumber(value, fallback, { min = -Infinity, max = Infinity } = {}) {
  const numericValue = Number(value);
  const resolvedValue = Number.isFinite(numericValue) ? numericValue : fallback;
  return Math.min(Math.max(resolvedValue, min), max);
}

function normalizeBoolean(value, fallback) {
  return typeof value === "boolean" ? value : fallback;
}

export function normalizeImplicitGraphicsSettings(value = {}) {
  const settings = value && typeof value === "object" ? value : {};
  return {
    resolutionScale: clampNumber(
      settings.resolutionScale,
      DEFAULT_IMPLICIT_GRAPHICS_SETTINGS.resolutionScale,
      IMPLICIT_GRAPHICS_LIMITS.resolutionScale
    ),
    interactionResolutionScale: clampNumber(
      settings.interactionResolutionScale,
      DEFAULT_IMPLICIT_GRAPHICS_SETTINGS.interactionResolutionScale,
      IMPLICIT_GRAPHICS_LIMITS.interactionResolutionScale
    ),
    detail: clampNumber(
      settings.detail,
      DEFAULT_IMPLICIT_GRAPHICS_SETTINGS.detail,
      IMPLICIT_GRAPHICS_LIMITS.detail
    ),
    normalSmoothing: clampNumber(
      settings.normalSmoothing,
      DEFAULT_IMPLICIT_GRAPHICS_SETTINGS.normalSmoothing,
      IMPLICIT_GRAPHICS_LIMITS.normalSmoothing
    ),
    modelColors: normalizeBoolean(settings.modelColors, DEFAULT_IMPLICIT_GRAPHICS_SETTINGS.modelColors),
    shadows: normalizeBoolean(settings.shadows, DEFAULT_IMPLICIT_GRAPHICS_SETTINGS.shadows),
    ambientOcclusion: normalizeBoolean(
      settings.ambientOcclusion,
      DEFAULT_IMPLICIT_GRAPHICS_SETTINGS.ambientOcclusion
    ),
    rimLight: normalizeBoolean(settings.rimLight, DEFAULT_IMPLICIT_GRAPHICS_SETTINGS.rimLight)
  };
}

export function implicitGraphicsSettingsEqual(a, b) {
  const normalizedA = normalizeImplicitGraphicsSettings(a);
  const normalizedB = normalizeImplicitGraphicsSettings(b);
  return Object.keys(DEFAULT_IMPLICIT_GRAPHICS_SETTINGS)
    .every((key) => normalizedA[key] === normalizedB[key]);
}
