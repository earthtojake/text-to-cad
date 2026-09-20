import {
  normalizeThemeSettings
} from "@hardcore/core/lib/themeSettings.js";
import {
  normalizeDisplaySettings
} from "@hardcore/core/lib/displaySettings.js";

import { resolveCadEdgeSettings } from "@hardcore/core/common/cadInk.js";
import { shareSettingsValue } from "./shareSettingsValue.js";

// Normalization must not invalidate unchanged scene subsystems. The resolver
// belongs to one viewport, just like the scene receiving its values.
export function createViewerRenderStateResolver() {
  let previous;
  return input => (previous = shareSettingsValue(previous, normalizeViewerRenderState(input)));
}

export function normalizeViewerRenderState({
  themeSettings = {},
  displaySettings = null
} = {}) {
  const normalizedThemeSettings = normalizeThemeSettings(themeSettings);
  const normalizedDisplaySettings = normalizeDisplaySettings(displaySettings);
  // Grouped View resolution has already decided surface and edge policy.
  // Preserve that explicit policy across this internal legacy normalization.
  if (displaySettings?.surfaces) {
    normalizedDisplaySettings.surfaces = displaySettings.surfaces;
    normalizedDisplaySettings.edges = { ...normalizedDisplaySettings.edges, ...displaySettings.edges };
  }
  return {
    themeSettings: normalizedThemeSettings,
    displaySettings: normalizedDisplaySettings,
    displayMode: normalizedDisplaySettings.mode,
    edgeSettings: resolveCadEdgeSettings(normalizedDisplaySettings.edges),
    clipSettings: normalizedDisplaySettings.clip
  };
}
