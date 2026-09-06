// What a host may pin on <CadFileView> (docs/file-view.md, "Laying out inside
// a host").
//
// The standalone app measures its own window and owns its own document; a host
// embedding the surface in one pane of a larger window can say "lay out as a
// desktop no matter how wide this pane is", "the sheet is this wide" and "the
// document is dark" — and every one of them is nothing at all unless it is
// asked for, so the standalone app's behaviour does not change.
//
// Plain functions in a module with no `@/` imports, so `node --test` can load
// them without the bundler's aliases.
import { CAD_WORKSPACE_LAYOUT_MODE } from "../workbench/breakpoints.js";

export const DESKTOP_TAB_TOOLS_MIN_WIDTH = 240;
export const DESKTOP_TAB_TOOLS_MAX_WIDTH = 448;

// `"desktop"` pins the desktop layout: the file sheet as a column beside the
// model rather than a drawer over it. Anything else means "measure".
export function resolveHostLayoutMode(layout) {
  return String(layout || "").trim().toLowerCase() === CAD_WORKSPACE_LAYOUT_MODE.DESKTOP
    ? CAD_WORKSPACE_LAYOUT_MODE.DESKTOP
    : null;
}

// A pinned sheet width, or null for the stored one. Clamped to the sheet's own
// range so a host cannot ask for a sheet the sheet cannot draw.
export function normalizeHostSheetWidth(value) {
  const width = Number(value);
  if (!Number.isFinite(width) || width <= 0) {
    return null;
  }
  return Math.round(Math.min(DESKTOP_TAB_TOOLS_MAX_WIDTH, Math.max(DESKTOP_TAB_TOOLS_MIN_WIDTH, width)));
}

// `"dark"` / `"light"` from a host resolve the "system" CAD theme preset and
// stop the surface writing the colour scheme to the document; null leaves
// both to the surface (the standalone case).
export function hostPrefersDarkForColorScheme(colorScheme) {
  const normalized = String(colorScheme || "").trim().toLowerCase();
  if (normalized === "dark") {
    return true;
  }
  if (normalized === "light") {
    return false;
  }
  return null;
}

/**
 * A host's scene backdrop, or null for the theme's own. Hex only: the theme
 * model stores colours as hex, and a host that has an oklch token converts
 * before asking. `#rgb` is expanded so one shorthand does not silently fall
 * back to the theme.
 */
export function normalizeHostSceneBackground(value) {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim().toLowerCase();
  if (/^#[0-9a-f]{6}$/.test(trimmed)) {
    return trimmed;
  }
  if (/^#[0-9a-f]{3}$/.test(trimmed)) {
    return "#" + [...trimmed.slice(1)].map((c) => c + c).join("");
  }
  return null;
}
