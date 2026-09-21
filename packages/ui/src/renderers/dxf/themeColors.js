/**
 * The two colours a drawing is painted with, read from the app's own tokens.
 *
 * A DXF's default pen (ACI 7) means "whatever contrasts with the background",
 * so the drawing has no colour of its own to fall back on: it is the theme's
 * `--foreground` on the theme's `--background`. The same pair the rest of the
 * app is drawn in, and the same background the 3D viewers' chrome uses in the
 * default theme.
 *
 * Read at DRAW time off the pane's own element rather than resolved once:
 * a host toggles `.dark` on `<html>` whenever it likes, and a token read in an
 * effect would be the value from before the switch.
 *
 * When the tokens cannot be read the pair comes from `APP_THEME_COLORS`, which
 * is also what `cadgen dxf snapshot` paints with: the headless bundle has no
 * stylesheet to read, so that constant is the one place the two colours are
 * written down and the CLI and this pane cannot drift.
 */
import { APP_THEME_COLORS } from "@hardcore/core/lib/appTheme.js";
import { cssColorToHex } from "../kit/look/chromeBackdrop.js";

/** What a pane falls back to when the tokens cannot be read at all. */
export const DRAWING_THEME_FALLBACK = APP_THEME_COLORS;

function token(element, name) {
  try {
    const view = element?.ownerDocument?.defaultView;
    if (typeof view?.getComputedStyle !== "function") {
      return "";
    }
    return view.getComputedStyle(element).getPropertyValue(name).trim();
  } catch {
    return "";
  }
}

/**
 * `{ background, foreground }` as `#rrggbb`, for the element's cascade.
 *
 * @param {Element|null} element
 * @param {"light"|"dark"} colorScheme  Which fallback pair an unreadable token takes.
 */
export function readDrawingThemeColors(element, colorScheme = "light") {
  const fallback = colorScheme === "dark" ? DRAWING_THEME_FALLBACK.dark : DRAWING_THEME_FALLBACK.light;
  if (!element) {
    return { ...fallback };
  }
  return {
    background: cssColorToHex(token(element, "--background")) || fallback.background,
    foreground: cssColorToHex(token(element, "--foreground")) || fallback.foreground
  };
}
