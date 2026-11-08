// The canvas: the content area behind every view, the colour a scene is drawn on.
//
// The app's `--canvas` token defines it, the 2D views' and the 3D views' alike; the
// tools view's scene takes it in place of its theme's background, and the box the
// scene fills is painted it too. Preview and Render paint their own studio.
// A missing or unreadable token falls back to the written-out pair (core's
// `lib/appTheme.js`). This is app UI resolution; the standalone snapshot
// renderer consumes its own supplied theme settings without app preferences.
//
// Plain functions, no `@/` imports and no React, so `node --test` loads this
// file directly; `document` arrives as an argument for the same reason.
import { APP_THEME_COLORS } from "@cad/core/lib/appTheme.js";

/** The `--canvas` pair, written out: what the token resolves to.
 *
 * Taken from the app's own colours rather than spelled again here: the 2D views
 * draw on the same pair, and a second copy of the number is the one that drifts. */
export const CANVAS_FALLBACK = Object.freeze({
  light: APP_THEME_COLORS.light.canvas,
  dark: APP_THEME_COLORS.dark.canvas
});

/** The custom property defining the canvas. */
export const CANVAS_TOKEN = "--canvas";

function clamp01(value) {
  return Math.min(1, Math.max(0, value));
}

function hexChannel(value) {
  return Math.round(clamp01(value) * 255).toString(16).padStart(2, "0");
}

function linearToSrgb(channel) {
  return channel <= 0.0031308
    ? channel * 12.92
    : 1.055 * Math.pow(channel, 1 / 2.4) - 0.055;
}

/**
 * One component of a CSS colour function. `none` is zero (CSS Color 4's
 * missing component), a percentage is scaled against that component's own
 * range, and anything unparseable is null so the caller can give up on the
 * whole colour rather than guess a channel.
 */
function colorComponent(token, percentScale = 1) {
  const text = String(token ?? "").trim().toLowerCase();
  if (!text || text === "none") {
    return 0;
  }
  if (text.endsWith("%")) {
    const percent = Number(text.slice(0, -1));
    return Number.isFinite(percent) ? (percent / 100) * percentScale : null;
  }
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}

/** A hue in degrees, from `120`, `120deg`, `2rad`, `0.3turn` or `100grad`. */
function hueDegrees(token) {
  const text = String(token ?? "").trim().toLowerCase();
  if (!text || text === "none") {
    return 0;
  }
  const match = /^(-?[\d.]+)(deg|rad|grad|turn)?$/u.exec(text);
  if (!match) {
    return null;
  }
  const value = Number(match[1]);
  if (!Number.isFinite(value)) {
    return null;
  }
  switch (match[2]) {
    case "rad":
      return (value * 180) / Math.PI;
    case "grad":
      return value * 0.9;
    case "turn":
      return value * 360;
    default:
      return value;
  }
}

/**
 * The arguments of `fn(...)`, split on commas, whitespace and the alpha
 * slash. `oklch(1 0 0)`, `rgb(255, 255, 255)` and `rgb(255 255 255 / 80%)`
 * all arrive as the same three-or-four element list.
 */
function colorFunctionArguments(value, name) {
  const text = String(value ?? "").trim().toLowerCase();
  if (!text.startsWith(`${name}(`) || !text.endsWith(")")) {
    return null;
  }
  return text
    .slice(name.length + 1, -1)
    .split(/[\s,/]+/u)
    .filter(Boolean);
}

/** OKLab → sRGB hex (Björn Ottosson's matrices), clipped into gamut. */
function oklabToHex(lightness, aAxis, bAxis) {
  const l = (lightness + 0.3963377774 * aAxis + 0.2158037573 * bAxis) ** 3;
  const m = (lightness - 0.1055613458 * aAxis - 0.0638541728 * bAxis) ** 3;
  const s = (lightness - 0.0894841775 * aAxis - 1.2914855480 * bAxis) ** 3;
  const red = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
  const green = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
  const blue = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s;
  return `#${[red, green, blue].map((channel) => hexChannel(linearToSrgb(channel))).join("")}`;
}

/**
 * A CSS colour as `#rrggbb`, or null when this parser does not know it.
 *
 * Three notations, because three are what a computed token can be:
 * `oklch()` (what both apps author), `rgb()`/`rgba()` (what a browser
 * serialises a legacy colour to) and hex (what a hand-written token or a
 * theme setting looks like). Alpha is dropped — the canvas is opaque — and
 * every other notation is null rather than an approximation.
 */
export function cssColorToHex(value) {
  if (typeof value !== "string") {
    return null;
  }
  const text = value.trim().toLowerCase();
  if (!text) {
    return null;
  }
  if (/^#[0-9a-f]{6}$/u.test(text)) {
    return text;
  }
  if (/^#[0-9a-f]{3}$/u.test(text)) {
    return `#${[...text.slice(1)].map((digit) => digit + digit).join("")}`;
  }
  const oklch = colorFunctionArguments(text, "oklch");
  if (oklch && oklch.length >= 3) {
    const lightness = colorComponent(oklch[0], 1);
    const chroma = colorComponent(oklch[1], 0.4);
    const hue = hueDegrees(oklch[2]);
    if (lightness === null || chroma === null || hue === null) {
      return null;
    }
    const radians = (hue * Math.PI) / 180;
    return oklabToHex(lightness, chroma * Math.cos(radians), chroma * Math.sin(radians));
  }
  for (const name of ["rgb", "rgba"]) {
    const rgb = colorFunctionArguments(text, name);
    if (!rgb || rgb.length < 3) {
      continue;
    }
    const channels = rgb.slice(0, 3).map((token) => {
      const component = colorComponent(token, 255);
      return component === null ? null : component / 255;
    });
    if (channels.some((channel) => channel === null)) {
      return null;
    }
    return `#${channels.map((channel) => hexChannel(channel)).join("")}`;
  }
  return null;
}

/**
 * The `--canvas` token as the document computes it right now, or `""`.
 *
 * Read off `<html>`, because that is where both apps declare the tokens and
 * where the `.dark` class that swaps them is toggled.
 */
export function readCanvasToken(doc = typeof document === "undefined" ? null : document) {
  const root = doc?.documentElement;
  const view = doc?.defaultView;
  if (!root || typeof view?.getComputedStyle !== "function") {
    return "";
  }
  try {
    return view.getComputedStyle(root).getPropertyValue(CANVAS_TOKEN).trim();
  } catch {
    return "";
  }
}

/**
 * The canvas, or the written-out pair when there is no token to read.
 *
 * `prefersDark` is the APP's light/dark — a host's `colorScheme`, or the
 * standalone viewer's own resolved scheme. Scene lighting and materials do
 * not change the app's appearance.
 */
export function resolveCanvasColor({ token = "", prefersDark = false } = {}) {
  return cssColorToHex(token)
    || (prefersDark === true ? CANVAS_FALLBACK.dark : CANVAS_FALLBACK.light);
}

/**
 * The colour the scene reaches its edges with, for the box the scene fills.
 *
 * The WebGL surface is opaque and covers that box, so this is only ever seen
 * for the frame between a resize and the renderer catching up — and "only a
 * frame" is exactly long enough to see a band of another colour above a dark
 * stage. A gradient's edge stop is the honest answer there, not its solid
 * base: that is the colour the picture ends on.
 *
 * It is also what a test can read. `scene.background` is a three.js texture
 * with no DOM presence and the viewport renderer keeps no drawing buffer, so
 * the box's own `background-color` is the one place the chosen colour is
 * legible from outside the renderer.
 * @param {{ type?: unknown, linearEnd?: unknown, radialOuter?: unknown, solidColor?: unknown } | null} background
 * @param {string} fallback
 */
export function sceneEdgeColor(background = null, fallback = CANVAS_FALLBACK.light) {
  const type = String(background?.type || "").trim().toLowerCase();
  // A transparent scene reveals the canvas behind it, not a dormant solid color.
  if (type === "transparent") return fallback;
  const edge = type === "linear"
    ? background?.linearEnd
    : type === "radial"
      ? background?.radialOuter
      : background?.solidColor;
  return cssColorToHex(edge) || cssColorToHex(background?.solidColor) || fallback;
}
