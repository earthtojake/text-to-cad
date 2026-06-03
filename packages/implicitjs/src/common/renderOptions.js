import {
  cloneThemeSettings,
  normalizeThemeSettings,
  resolveThemeSettingsForColorMode
} from "./themeSettings.js";

export function resolveAppearanceJobConfig(job = {}, { defaultThemeId = "workbench" } = {}) {
  if (typeof job.appearance === "string") {
    return {
      themeId: job.appearance,
      settings: null
    };
  }
  if (job.appearance && typeof job.appearance === "object" && !Array.isArray(job.appearance)) {
    return {
      themeId: defaultThemeId,
      settings: job.appearance
    };
  }
  return {
    themeId: defaultThemeId,
    settings: null
  };
}

export function resolveAppearanceSettings(job = {}, { defaultThemeId = "workbench" } = {}) {
  const appearance = resolveAppearanceJobConfig(job, { defaultThemeId });
  const themeSettings = cloneThemeSettings(appearance.themeId || defaultThemeId);
  const normalized = normalizeThemeSettings(appearance.settings || themeSettings);
  return typeof job.appearance === "string"
    ? resolveThemeSettingsForColorMode(normalized, { prefersDark: false })
    : normalized;
}
