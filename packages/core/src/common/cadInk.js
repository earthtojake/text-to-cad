import {
  CAD_EDGE_CLASS_IDS,
  normalizeDisplayEdgeSettings
} from "./displaySettings.js";

// Full widths in drawing-buffer (device) pixels. Both the instanced CAD pass
// and LineMaterial use the same values and analytic antialiasing feather.
const WIDTHS = Object.freeze({ feature: 1, tangent: 0.65, seam: 0.8, degenerate: 0 });
// Model ink is appearance-independent; only the canvas and guides adapt.
const PALETTE = Object.freeze({ feature: "#253443", tangent: "#667788", seam: "#495b6c", degenerate: "#667788" });

export function resolveCadEdgeSettings(value = null, { themeEdges = null } = {}) {
  const ink = {
    ...normalizeDisplayEdgeSettings(value),
    color: PALETTE.feature,
    opacity: 1,
    thickness: WIDTHS.feature,
    classes: Object.fromEntries(CAD_EDGE_CLASS_IDS.map((classId) => [classId, {
      color: PALETTE[classId],
      opacity: 1,
      thickness: WIDTHS[classId]
    }])),
    highlightColor: "#8dc5ff",
    highlightOpacity: 1,
    highlightThickness: 3,
    silhouetteScale: 0.004,
    ...(typeof value?.depthTest === "boolean" ? { depthTest: value.depthTest } : {})
  };
  return themeEdges
    ? { ...normalizeThemeEdgeSettings(themeEdges, ink), ...normalizeDisplayEdgeSettings(value),
        ...(typeof value?.depthTest === "boolean" ? { depthTest: value.depthTest } : {}) }
    : ink;
}

// A custom Inspect theme owns its authored outline independently of the closed
// display toggles. Default inspection ink and every Render recipe remain fixed.
export function normalizeThemeEdgeSettings(value = {}, fallback = resolveCadEdgeSettings()) {
  const source = value && typeof value === "object" ? value : {};
  const color = (input, defaultColor) => {
    const text = String(input || "").trim().toLowerCase();
    return /^#[0-9a-f]{6}$/.test(text) ? text : /^#[0-9a-f]{3}$/.test(text)
      ? `#${text[1]}${text[1]}${text[2]}${text[2]}${text[3]}${text[3]}` : defaultColor;
  };
  const number = (input, defaultValue, min, max) => Number.isFinite(Number(input))
    ? Math.max(min, Math.min(max, Number(input))) : defaultValue;
  const baseColor = color(source.color, fallback.color);
  return {
    ...fallback,
    ...normalizeDisplayEdgeSettings(source, fallback),
    color: baseColor,
    opacity: number(source.opacity, fallback.opacity, 0, 1),
    thickness: number(source.thickness, fallback.thickness, 0.5, 6),
    classes: Object.fromEntries(CAD_EDGE_CLASS_IDS.map((id) => {
      const style = source.classes?.[id] || {};
      const base = fallback.classes[id];
      return [id, {
        color: color(style.color, source.color ? baseColor : base.color),
        opacity: number(style.opacity, base.opacity, 0, 1),
        thickness: number(style.thickness, base.thickness, 0, 6),
      }];
    })),
    highlightColor: color(source.highlightColor, fallback.highlightColor),
    highlightOpacity: number(source.highlightOpacity, fallback.highlightOpacity, 0, 1),
    highlightThickness: number(source.highlightThickness, fallback.highlightThickness, 0.5, 6),
    silhouetteScale: number(source.silhouetteScale, fallback.silhouetteScale, 0, 0.04),
    ...(typeof source.depthTest === "boolean" ? { depthTest: source.depthTest } : {}),
  };
}

export function resolveCadGridSettings(value = null, { colorMode = "light" } = {}) {
  const dark = colorMode === "dark";
  return {
    enabled: value?.enabled === true,
    centerColor: dark ? "#697786" : "#6b7280",
    cellColor: dark ? "#495665" : "#cbd5e1",
    opacity: 0.16,
    density: 1
  };
}
