/**
 * The model area's colours, written out ONCE: the viewport's background (the person's
 * Background setting: Light or Dark) and the scene's own colours — selection,
 * hover, the grid, the XYZ axes — that every 3D and 2D view draws with.
 *
 * The viewport is its own surface, not the app's chrome: a light model area in a dark app is
 * the default, as a CAD program's is, so nothing drawn in it may take its colours from the UI
 * theme. A view resolves its viewport theme (`resolveViewportTheme`) and draws in its `scheme`
 * on its `canvas` (a 3D view's background its `gradient`, top to bottom); the chrome over it
 * keeps the app's theme. `appTheme.js` keeps the app's own colours.
 *
 * The selection blue is more saturated than the brand on purpose: it is read against a model's
 * greys and colours, not against the chrome.
 *
 * No DOM, no React, no imports but core's own colours: the headless bundle, `node --test` and
 * the viewer all load this file directly.
 */
import { APP_THEME_COLORS } from "./appTheme.js";

/** The person's choices, in the Display menu's order; Light is the default. */
export const VIEWPORT_BACKGROUNDS = Object.freeze(["light", "dark"]);
export const DEFAULT_VIEWPORT_BACKGROUND = "light";

/**
 * The two looks a viewport is drawn in. Light: a soft grey gradient, never white, so a white part
 * reads against it, top to bottom; `canvas` the flat colour a 2D view draws on and the box behind a
 * scene takes, the light canvas (between the gradient's ends). Dark: the dark canvas, flat.
 */
export const VIEWPORT_LOOKS = Object.freeze({
  light: Object.freeze({ scheme: "light", canvas: APP_THEME_COLORS.light.canvas, gradient: Object.freeze(["#f4f5f6", "#dfe2e5"]) }),
  dark: Object.freeze({ scheme: "dark", canvas: APP_THEME_COLORS.dark.canvas, gradient: null })
});

/**
 * A stored value as one of the choices: anything else is the default, Light. That includes a value of
 * the choice there no longer is, "theme" (the app's own canvas, once Follow theme), read as Light.
 */
export function normalizeViewportBackground(value) {
  return VIEWPORT_BACKGROUNDS.includes(value) ? value : DEFAULT_VIEWPORT_BACKGROUND;
}

/**
 * The viewport's theme: `{ background, scheme, canvas, gradient }`, whatever the app's theme.
 *
 * @param {string} [background] `"light"` (default) or `"dark"`.
 */
export function resolveViewportTheme(background) {
  const choice = normalizeViewportBackground(background);
  return { background: choice, ...VIEWPORT_LOOKS[choice] };
}

/**
 * The scene's colours. `selected` a measurement or a mark picked, `selectedFill` a picked part's or
 * reference's fill, `selectedEdge` a picked edge's line, `hover` what the pointer is over;
 * `box` the box select's frame and its fill.
 */
export const SCENE_COLORS = Object.freeze({
  selected: "#2979ff",
  selectedFill: "#4f9dff",
  hover: "#8dc5ff",
  // A picked edge, and a picked face's outline: deep enough to read as a line on a model's light faces.
  selectedEdge: "#1a73e8",
  box: Object.freeze({ border: "#2979ff", fill: "rgba(41, 121, 255, 0.12)" })
});

/** The floor grid's line, per viewport scheme. */
export const GRID_COLORS = Object.freeze({
  light: Object.freeze({ color: "#4ea8cc", opacity: 0.45 }),
  dark: Object.freeze({ color: "#5d9ac0", opacity: 0.35 })
});

/**
 * The one XYZ palette: the grid's axes, the Axes setting's line and the view cube's, a shade deeper
 * on a light viewport to hold their contrast.
 */
export const AXIS_COLORS = Object.freeze({
  light: Object.freeze({ x: "#e5484d", y: "#2f9e57", z: "#3d6fe8" }),
  dark: Object.freeze({ x: "#f2555a", y: "#4cc970", z: "#5b8cff" })
});

/** The axis palette of a viewport scheme. Anything but `"dark"` is light. */
export function axisColors(scheme) {
  return scheme === "dark" ? AXIS_COLORS.dark : AXIS_COLORS.light;
}
