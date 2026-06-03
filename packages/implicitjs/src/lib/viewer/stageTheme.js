export const BASE_VIEWER_THEME = {
  sceneBackground: "#09090b",
  surface: "#f4f4f5",
  surfaceRoughness: 0.92,
  surfaceMetalness: 0.03
};

export const HEX_COLOR_PATTERN = /^#(?:[0-9a-fA-F]{3}){1,2}$/;

export function getViewerThemeValue(viewerTheme, key, fallback) {
  const value = viewerTheme?.[key];
  return value ?? BASE_VIEWER_THEME[key] ?? fallback;
}
