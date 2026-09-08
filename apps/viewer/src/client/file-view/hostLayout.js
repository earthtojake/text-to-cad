// What a host may pin on <CadFileView> (docs/file-view.md, "Laying out inside
// a host").
//
// The standalone app measures its own window and owns its own document; a host
// embedding the surface in one pane of a larger window can say "lay out as a
// desktop no matter how wide this pane is", "the sheet is this wide" and "the
// document is dark" — and every one of them is nothing at all unless it is
// asked for, so the standalone app's behaviour does not change.
//
// Plain functions, and only relative imports of modules that are plain
// functions too, so `node --test` can load them without the bundler's aliases.
import { CAD_WORKSPACE_LAYOUT_MODE } from "../workbench/breakpoints.js";
import { applyColorSchemeToDocument, resolveColorSchemeMode } from "../ui/colorScheme.js";

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

// `"dark"` / `"light"` from a host resolve the "system" CAD theme — its
// light/dark half AND the chrome background it paints the scene on
// (chromeBackdrop.js) — and stop the surface writing the colour scheme to the
// document; null leaves all of it to the surface (the standalone case).
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
 * The surface's ONE write of the document's colour scheme — and the rule that
 * a host's `colorScheme` cancels it.
 *
 * Embedded, the document belongs to the host: it has a light/dark preference
 * of its own, applies it to `<html>` itself, and hands the resolved answer
 * down as `colorScheme`. A surface that also wrote the document would be a
 * second writer with a second preference — the viewer's own stored
 * `cad-viewer:color-scheme`, which is nobody's choice in a host — and the app
 * around it would flip light on a mount, a storage event or a theme edit.
 * Standalone there is no host and the surface's preference is the app's, so it
 * writes.
 *
 * The rule is a function rather than an `if` inside an effect so it can be
 * tested on its own (hostLayout.test.js) and so there is one place a document
 * write can happen from at all.
 *
 * Answers the mode written, or null when the write was skipped.
 */
export function applyColorSchemeUnlessHostPinned(
  colorScheme,
  colorSchemePreference,
  { prefersDark = false, root = undefined } = {}
) {
  if (hostPrefersDarkForColorScheme(colorScheme) !== null) {
    return null;
  }
  const target = root || (typeof document === "undefined" ? null : document.documentElement);
  if (!target) {
    return null;
  }
  applyColorSchemeToDocument(colorSchemePreference, target, { prefersDark });
  return resolveColorSchemeMode(colorSchemePreference, { prefersDark });
}
