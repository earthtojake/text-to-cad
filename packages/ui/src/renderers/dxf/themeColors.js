/**
 * The two colours a drawing is painted with, read from the app's own tokens.
 *
 * A DXF's default pen (ACI 7) means "whatever contrasts with the background",
 * so the drawing has no colour of its own to fall back on: it is the theme's
 * `--foreground` on the app's canvas, `--canvas`: the content area every view
 * draws on, a board's, a schematic's and a 3D view's alike.
 *
 * Read at DRAW time off the pane's own element rather than resolved once:
 * a host toggles `.dark` on `<html>` whenever it likes, and a token read in an
 * effect would be the value from before the switch.
 *
 * When the tokens cannot be read the pair comes from `APP_THEME_COLORS`, the one
 * place the app's colours are written down. The parity page's headless drawing
 * (a snapshot) paints with the same constant's `background` and `foreground`, so a
 * still keeps the paper it had before the canvas moved to `--canvas`.
 */
import { APP_THEME_COLORS } from "@cad/core/lib/appTheme.js";
import { CANVAS_TOKEN, cssColorToHex } from "../kit/look/canvasColor.js";

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
 * `{ background, foreground }` as `#rrggbb`, for the element's cascade: `background` the canvas.
 *
 * @param {Element|null} element
 * @param {"light"|"dark"} colorScheme  Which fallback pair an unreadable token takes.
 */
export function readDrawingThemeColors(element, colorScheme = "light") {
  const fallback = colorScheme === "dark" ? DRAWING_THEME_FALLBACK.dark : DRAWING_THEME_FALLBACK.light;
  if (!element) {
    return { background: fallback.canvas, foreground: fallback.foreground };
  }
  return {
    background: cssColorToHex(token(element, CANVAS_TOKEN)) || fallback.canvas,
    foreground: cssColorToHex(token(element, "--foreground")) || fallback.foreground
  };
}
