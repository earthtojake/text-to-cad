/**
 * The app's own surface pair, written out: what `--background` and
 * `--foreground` resolve to in the light and the dark scheme.
 *
 * A running app reads the CSS tokens, because a host may restyle them. Two
 * places cannot: the headless snapshot bundle has no app stylesheet at all, and
 * a pane whose tokens read back empty (a detached element, a test harness with
 * no styles) still has to paint something. Both need the same two colours as
 * the app, or a CLI render and the viewer would disagree about what "the
 * drawing's default pen" looks like.
 *
 * So the pair lives here, ONCE, as the numbers `packages/ui/src/styles/tokens.css`
 * declares: `oklch(1 0 0)` / `oklch(0.145 0 0)` light, `oklch(0.28 0 0)` /
 * `oklch(0.985 0 0)` dark. Change a token and change these together — a test
 * cannot read a stylesheet that the snapshot bundle never loads.
 *
 * No DOM, no React, no imports: the snapshot bundle, `node --test` and the
 * viewer all load this file directly.
 */

/** `{ background, foreground }` as `#rrggbb`, per colour scheme. */
export const APP_THEME_COLORS = Object.freeze({
  light: Object.freeze({ background: "#ffffff", foreground: "#171717" }),
  dark: Object.freeze({ background: "#292929", foreground: "#fafafa" })
});

/**
 * The pair for one scheme. Anything but `"dark"` is light, so an absent or
 * malformed appearance renders rather than throwing.
 *
 * @param {string} [colorScheme] `"light"` (default) or `"dark"`.
 * @returns {{ background: string, foreground: string }}
 */
export function appThemeColors(colorScheme) {
  return colorScheme === "dark" ? APP_THEME_COLORS.dark : APP_THEME_COLORS.light;
}
