import {
  CAD_EDGE_CLASS_IDS,
  normalizeDisplayEdgeSettings
} from "./displaySettings.js";
import { GRID_AXIS_COLORS, GRID_LINE_DEFAULTS } from "../lib/viewer/stageGrid.js";

// Full widths in drawing-buffer (device) pixels. Both the instanced CAD pass
// and LineMaterial use the same values and analytic antialiasing feather.
const WIDTHS = Object.freeze({ feature: 1, tangent: 0.65, seam: 0.8, degenerate: 0 });
// Model ink is appearance-independent; only the canvas and guides adapt.
const PALETTE = Object.freeze({ feature: "#253443", tangent: "#667788", seam: "#495b6c", degenerate: "#667788" });

export function resolveCadEdgeSettings(value = null) {
  const customColor = value?.color && value.color !== PALETTE.feature ? value.color : null;
  return {
    ...normalizeDisplayEdgeSettings(value),
    color: value?.color || PALETTE.feature,
    opacity: 1,
    thickness: WIDTHS.feature,
    classes: Object.fromEntries(CAD_EDGE_CLASS_IDS.map((classId) => [classId, {
      color: value?.classes?.[classId]?.color || customColor || PALETTE[classId],
      opacity: 1,
      thickness: WIDTHS[classId]
    }])),
    highlightColor: "#8dc5ff",
    highlightOpacity: 1,
    highlightThickness: 3,
    silhouetteScale: 0.004,
    ...(value?.visibility ? { depthTest: value.visibility !== "all" } :
      typeof value?.depthTest === "boolean" ? { depthTest: value.depthTest } : {})
  };
}

// The grid's lines in its colour (graph-paper blue by default); its X and Y axes in the view cube's red and green.
export function resolveCadGridSettings(value = null, { colorMode = "light" } = {}) {
  const dark = colorMode === "dark";
  const axes = GRID_AXIS_COLORS[dark ? "dark" : "light"];
  const lines = GRID_LINE_DEFAULTS[dark ? "dark" : "light"];
  return {
    enabled: value?.enabled === true,
    color: value?.color ?? lines.color,
    opacity: value?.opacity ?? lines.opacity,
    density: value?.density ?? 1,
    xAxisColor: axes.x,
    yAxisColor: axes.y
  };
}
