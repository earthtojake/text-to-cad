// The scene's backdrop when the active CAD theme is "System".
//
// A theme paints the scene, and every preset but one — and the custom theme —
// paints the backdrop its own settings ask for: Cinematic's radial charcoal is
// Cinematic. "System" is the one that means *follow the app*, so it paints the
// chrome's own ground: the `--background` token on the document, which the
// standalone viewer's globals and a host's (the desktop app's) both define as
// the same shadcn neutral pair.
//
// A page with no such token is not an error, it is a headless render: the
// snapshot bundle draws into an offscreen canvas with no stylesheet and no
// chrome to match. That falls back to the literal values of that pair, which
// are what `oklch(1 0 0)` and `oklch(0.145 0 0)` resolve to, so the colour is
// the same with a stylesheet or without one.
//
// Plain functions, no `@/` imports and no React, so `node --test` loads this
// file directly; `document` arrives as an argument for the same reason.

/** The `--background` pair, written out: what the tokens resolve to. */
export const CHROME_BACKDROP_FALLBACK = Object.freeze({
  light: "#ffffff",
  dark: "#0a0a0a"
});

/** The custom property both apps define the chrome's ground in. */
export const CHROME_BACKGROUND_TOKEN = "--background";

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
 * Three notations, because three are what a computed `--background` can be:
 * `oklch()` (what both apps author), `rgb()`/`rgba()` (what a browser
 * serialises a legacy colour to) and hex (what a hand-written token or a
 * theme setting looks like). Alpha is dropped — a backdrop is opaque — and
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
 * The `--background` token as the document computes it right now, or `""`.
 *
 * Read off `<html>`, because that is where both apps declare the pair and
 * where the `.dark` class that swaps them is toggled.
 */
export function readChromeBackgroundToken(doc = typeof document === "undefined" ? null : document) {
  const root = doc?.documentElement;
  const view = doc?.defaultView;
  if (!root || typeof view?.getComputedStyle !== "function") {
    return "";
  }
  try {
    return view.getComputedStyle(root).getPropertyValue(CHROME_BACKGROUND_TOKEN).trim();
  } catch {
    return "";
  }
}

/**
 * The colour the "System" theme paints the scene on: the chrome's own
 * ground, or the written-out pair when there is no chrome to read.
 *
 * `prefersDark` is the APP's light/dark — a host's `colorScheme`, or the
 * standalone viewer's own resolved scheme — never the theme's, which has no
 * vote in what the app looks like.
 */
export function resolveChromeBackdropColor({ token = "", prefersDark = false } = {}) {
  return cssColorToHex(token)
    || (prefersDark === true ? CHROME_BACKDROP_FALLBACK.dark : CHROME_BACKDROP_FALLBACK.light);
}

/**
 * The colour the scene reaches its edges with, for the box the canvas fills.
 *
 * The WebGL canvas is opaque and covers that box, so this is only ever seen
 * for the frame between a resize and the renderer catching up — and "only a
 * frame" is exactly long enough to see a band of the app's own background
 * above a dark stage. A gradient's edge stop is the honest answer there, not
 * its solid base: that is the colour the picture ends on.
 *
 * It is also what a test can read. `scene.background` is a three.js texture
 * with no DOM presence and the viewport renderer keeps no drawing buffer, so
 * the box's own `background-color` is the one place the chosen backdrop is
 * legible from outside the renderer.
 */
export function sceneBackdropEdgeColor(background = null, fallback = CHROME_BACKDROP_FALLBACK.light) {
  const type = String(background?.type || "").trim().toLowerCase();
  const edge = type === "linear"
    ? background?.linearEnd
    : type === "radial"
      ? background?.radialOuter
      : background?.solidColor;
  return cssColorToHex(edge) || cssColorToHex(background?.solidColor) || fallback;
}
