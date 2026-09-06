// Per-file surface state that is pure functions over storage, the viewport and a
// catalog entry. Lifted verbatim out of CadWorkspace when the file surface moved
// into <CadFileView>; nothing here changed but its address.
import {
  getCadWorkspaceLayoutMode,
  shouldCadWorkspaceDefaultFileSettingsOpen
} from "@/workbench/breakpoints";
import {
  cadWorkspaceDefaultFileSheetWidthForViewport,
  readCadDirectorySessionState,
  CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH
} from "@/workbench/persistence";
import { renderFormatLabel } from "cadgen-js/lib/renderCapabilities";

// The title over a file sheet whose only tab is status: a mesh never had
// file-specific controls, and DXF lost its when the geometry moved into a baked
// render package, whose settings the producer owns.
export function statusOnlyFileSheetTitle(sourceFormat) {
  return renderFormatLabel(sourceFormat) || "STL";
}

// Single user-facing label for "the viewer is (re)generating the render artifacts a STEP model
// needs before it can render" — used for both the filename status chip and its tooltip across every
// artifact-generation trigger (first build, stale rebuild, source-changed regen). Browser-side
// asset-load/parse stages ("loading mesh", reference "loading topology", etc.) are a different
// concept and keep their own wording.
// The URDF loader reports its stage in lower case ("loading meshes 7/13") because the
// file-list chip reads that way; the viewport card is a sentence and needs a capital.
export function capitalizeFirst(value) {
  const text = String(value || "").trim();
  return text ? `${text.slice(0, 1).toUpperCase()}${text.slice(1)}` : "";
}

export const ARTIFACT_GENERATING_LABEL = "Generating artifacts";
export const EMPTY_LIST = Object.freeze([]);
export const DESKTOP_SIDEBAR_MIN_WIDTH = 150;
export const DESKTOP_SIDEBAR_MAX_WIDTH = 520;
export const DEFAULT_SIDEBAR_WIDTH = CAD_WORKSPACE_DEFAULT_SIDEBAR_WIDTH;
// The sheet's range and what a host may pin live in hostLayout.js (a module
// with no bundler aliases, so its tests run under plain node).
export {
  DESKTOP_TAB_TOOLS_MAX_WIDTH,
  DESKTOP_TAB_TOOLS_MIN_WIDTH,
  hostPrefersDarkForColorScheme,
  normalizeHostSceneBackground,
  normalizeHostSheetWidth,
  resolveHostLayoutMode
} from "./hostLayout.js";
export const CAD_WORKSPACE_TOP_BAR_HEIGHT = 44;
export const DEFAULT_LARGE_FILE_STATE = Object.freeze({
  selectableTopologyEnabled: false
});

export function normalizeLargeFileState(value = {}) {
  return {
    selectableTopologyEnabled: value?.selectableTopologyEnabled === true
  };
}

export function readViewerViewportWidth() {
  if (typeof window === "undefined") {
    return 1600;
  }
  const width = Number(window.innerWidth);
  return Number.isFinite(width) && width > 0 ? width : 1600;
}

export function readViewerLayoutMode() {
  return getCadWorkspaceLayoutMode(readViewerViewportWidth());
}

export function readDirectorySessionState(viewportWidth = readViewerViewportWidth()) {
  return readCadDirectorySessionState({
    defaultFileSheetWidthPx: cadWorkspaceDefaultFileSheetWidthForViewport(viewportWidth)
  });
}

export function readInitialFileSheetOpen() {
  const storedOpen = readDirectorySessionState().fileSheetOpen;
  return typeof storedOpen === "boolean"
    ? storedOpen
    : shouldCadWorkspaceDefaultFileSettingsOpen(readViewerViewportWidth());
}

export function readInitialFileSheetWidth() {
  const viewportWidth = readViewerViewportWidth();
  return (
    readDirectorySessionState(viewportWidth).fileSheetWidthPx ||
    cadWorkspaceDefaultFileSheetWidthForViewport(viewportWidth)
  );
}

export function readInitialFileSheetWidthIsCustom() {
  const viewportWidth = readViewerViewportWidth();
  return readDirectorySessionState(viewportWidth).fileSheetWidthPx != null;
}

// Hide an entry's render assets (url/hash/bytes/assets) so the viewer treats it as "not yet
// renderable" — used while its render artifact is missing/stale/building or has failed, so the
// viewer shows a loading/error state and never renders a stale cache. Once the artifact is ready
// the unstripped catalog entry is used and the mesh loads.
export function entryWithoutRenderAssets(entry) {
  if (!entry) {
    return entry;
  }
  const next = { ...entry };
  delete next.url;
  delete next.hash;
  delete next.bytes;
  delete next.assets;
  // A baked mesh published as a `glb` relation rather than as the entry's own url would
  // otherwise stay renderable while its replacement is being built -- which is exactly the
  // stale cache this function exists to hide.
  if (next.relations?.glb) {
    const relations = { ...next.relations };
    delete relations.glb;
    next.relations = relations;
  }
  return next;
}

