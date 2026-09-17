import {
  normalizeThemeSettings
} from "@hardcore/core/lib/themeSettings.js";
import {
  normalizeDisplaySettings
} from "@hardcore/core/lib/displaySettings.js";

import { resolveCadEdgeSettings } from "@hardcore/core/common/cadInk.js";

export function normalizeViewerRenderState({
  themeSettings = {},
  displaySettings = null
} = {}) {
  const normalizedThemeSettings = normalizeThemeSettings(themeSettings);
  const normalizedDisplaySettings = normalizeDisplaySettings(displaySettings);
  return {
    themeSettings: normalizedThemeSettings,
    displaySettings: normalizedDisplaySettings,
    displayMode: normalizedDisplaySettings.mode,
    edgeSettings: resolveCadEdgeSettings(normalizedDisplaySettings.edges, { themeEdges: normalizedThemeSettings.edges }),
    clipSettings: normalizedDisplaySettings.clip
  };
}
