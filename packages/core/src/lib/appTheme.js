/**
 * The app's own colours, written out: what `--background`, `--foreground` and `--canvas`
 * resolve to in the light and the dark scheme.
 *
 * A running app reads the CSS tokens, because a host may restyle them. Some places cannot:
 * the parity page's headless bundle has no app stylesheet at all, a pane whose tokens read
 * back empty (a detached element, a test harness with no styles) still has to paint
 * something, and the board's and the schematic's canvases are drawn from their theme's
 * palette, never from a token. All of them need the same colours as the app.
 *
 * So they live here, ONCE, as the numbers `packages/ui/src/styles/tokens.css` declares:
 * `--background` `oklch(1 0 0)` / `#2c2c2c`, `--foreground` `oklch(0.145 0 0)` /
 * `oklch(0.985 0 0)`, and `--canvas` `oklch(0.94 0 0)` / `oklch(0.235 0 0)`, light / dark.
 * `canvas` is the content area behind every view, 2D and 3D: the board's canvas, the
 * schematic's surround, a drawing's and a 3D view's. Change a token and change these
 * together; `packages/ui/src/styles/canvas.test.js` reads the stylesheet and fails when any of
 * the three drifts from it. The viewport's own colours (its Background setting, the scene's
 * selection, grid and axes) are `viewportTheme.js`'s.
 *
 * No DOM, no React, no imports: the headless bundle, `node --test` and the
 * viewer all load this file directly.
 */

/** `{ background, foreground, canvas }` as `#rrggbb`, per colour scheme. */
export const APP_THEME_COLORS = Object.freeze({
  light: Object.freeze({ background: "#ffffff", foreground: "#0a0a0a", canvas: "#ebebeb" }),
  dark: Object.freeze({ background: "#2c2c2c", foreground: "#fafafa", canvas: "#1e1e1e" })
});

/**
 * The colours of one scheme. Anything but `"dark"` is light, so an absent or
 * malformed appearance renders rather than throwing.
 *
 * @param {string} [colorScheme] `"light"` (default) or `"dark"`.
 * @returns {{ background: string, foreground: string, canvas: string }}
 */
export function appThemeColors(colorScheme) {
  return colorScheme === "dark" ? APP_THEME_COLORS.dark : APP_THEME_COLORS.light;
}
