import { getThemePresetById } from "@text-to-cad/core/common/themeSettings.js";

/**
 * What a CAM result's toolpaths are drawn in. Each operation's feed moves take a hue of the viewer's
 * categorical palette (the Workbench fill colours, past the first, which is the model's own grey), in
 * operation order; the palette's pastels are kept for a dark background and taken down to a mid tone
 * on a light one, where they would wash out. Rapids are one muted ink, the markers' grey. The Job
 * panel's swatches use the same colours, so a row and its path read as one. Pure.
 */

const FALLBACK = Object.freeze(["#f4a7a7", "#f8c77e", "#f7e38d", "#b9e88f", "#8fe3c0", "#92d7f5", "#a9b8ff", "#c7a8ff", "#f2a7d9"]);

function palette() {
  const fills = getThemePresetById("workbench-light")?.settings?.materials?.fillColors;
  return Array.isArray(fills) && fills.length > 1 ? fills.slice(1) : FALLBACK;
}

export const RAPID_COLOURS = Object.freeze({ light: "#71717a", dark: "#a1a1aa" });

function hexToHsl(hex) {
  const value = parseInt(String(hex).replace("#", ""), 16);
  const [r, g, b] = [(value >> 16) & 255, (value >> 8) & 255, value & 255].map((channel) => channel / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  const h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [h / 6, s, l];
}

function hslToHex([h, s, l]) {
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  const channel = (t) => {
    const u = t < 0 ? t + 1 : t > 1 ? t - 1 : t;
    const v = u < 1 / 6 ? p + (q - p) * 6 * u : u < 1 / 2 ? q : u < 2 / 3 ? p + (q - p) * (2 / 3 - u) * 6 : p;
    return Math.round(v * 255).toString(16).padStart(2, "0");
  };
  return `#${channel(h + 1 / 3)}${channel(h)}${channel(h - 1 / 3)}`;
}

/** The colour of the `order`th operation of a job, for the scheme ("light" or "dark"). */
export function operationColour(order, scheme = "light") {
  const fills = palette();
  const hex = fills[((order % fills.length) + fills.length) % fills.length];
  if (scheme === "dark") return hex;
  const [h, s] = hexToHsl(hex);
  return hslToHex([h, Math.min(0.7, Math.max(s, 0.55)), 0.42]);
}

/** Every operation's colour by its index, in the job's order, for the scheme. */
export function camOpColours(job, scheme = "light") {
  return Object.fromEntries((job?.operations || []).map((op, order) => [op.index, operationColour(order, scheme)]));
}
