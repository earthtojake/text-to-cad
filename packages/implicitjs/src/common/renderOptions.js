import {
  cloneThemeSettings,
  normalizeThemeSettings,
  resolveThemeSettingsForColorMode
} from "./themeSettings.js";

export function resolveThemeJobConfig(job = {}, { defaultThemeId = "workbench" } = {}) {
  if (typeof job.theme === "string") {
    return {
      themeId: job.theme,
      settings: null
    };
  }
  if (job.theme && typeof job.theme === "object" && !Array.isArray(job.theme)) {
    return {
      themeId: defaultThemeId,
      settings: job.theme
    };
  }
  return {
    themeId: defaultThemeId,
    settings: null
  };
}

export function resolveThemeSettings(job = {}, { defaultThemeId = "workbench" } = {}) {
  const theme = resolveThemeJobConfig(job, { defaultThemeId });
  const themeSettings = cloneThemeSettings(theme.themeId || defaultThemeId);
  const normalized = normalizeThemeSettings(theme.settings || themeSettings);
  return typeof job.theme === "string"
    ? resolveThemeSettingsForColorMode(normalized, { prefersDark: false })
    : normalized;
}
