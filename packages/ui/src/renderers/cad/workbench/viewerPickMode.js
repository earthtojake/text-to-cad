import { VIEWER_PICK_MODE } from "@hardcore/core/lib/viewer/constants.js";

export function viewerSelectorRuntimeForRenderPane({
  hasTopology = false,
  retainingPreviousStepMesh = false,
  selectorRuntime = null
} = {}) {
  // Display style never changes the expanded topology frontier.
  return hasTopology && !retainingPreviousStepMesh ? selectorRuntime : null;
}

// One shared empty list for every part-state prop this module hands the scene.
// A fresh [] per call is a new prop identity on every render, which re-runs the
// viewer's scene-effects effect — and the viewport LOD resample it ends with —
// on renders that changed nothing. That resample publishes LOD status, whose
// React state re-renders the workspace: the viewport never stops sampling
// itself and never reports settled quality.
const EMPTY_PART_IDS = Object.freeze([]);

// Part selection and visibility are independent of lighting/display style.
export function viewerSelectedPartIdsForRenderPane({
  hasParts = false,
  selectedPartIds = []
} = {}) {
  return hasParts && Array.isArray(selectedPartIds) ? selectedPartIds : EMPTY_PART_IDS;
}

// Formats without parts use the shared empty list.
export function viewerHiddenPartIdsForRenderPane({
  inspectionEnabled = false,
  hasParts = false,
  hiddenPartIds = []
} = {}) {
  return inspectionEnabled && hasParts && Array.isArray(hiddenPartIds) ? hiddenPartIds : EMPTY_PART_IDS;
}

// Callers decide whether picking is enabled (parts, topology, or Measure).
// This helper stays format-agnostic.
export function viewerPickModeForRenderPane({
  selectionFilter = "all",
  panToolActive = false,
  topologySelectionPending = false,
  topologySelectionUnavailable = false,
  topologySelectionDeferred = false,
  topologyPickingActive = false,
  viewerMode = "",
  assemblyPickingActive = false,
  focusedPartIds = "",
  measureMode = false
} = {}) {
  // While panning, a drag is a camera move — picking on release would select
  // whatever the drag happened to finish over.
  if (panToolActive) {
    return VIEWER_PICK_MODE.NONE;
  }
  if (!measureMode && selectionFilter === "parts") return VIEWER_PICK_MODE.PARTS;
  if (topologySelectionPending || topologySelectionUnavailable || topologySelectionDeferred) {
    return VIEWER_PICK_MODE.NONE;
  }
  // Measure outranks both part and topology selection, and needs neither. The
  // endpoint always comes from the ray hit on the visible mesh; loaded topology
  // only refines that hit into a snap. An assembly with nothing expanded still
  // measures surface to surface across its parts.
  if (measureMode) {
    return VIEWER_PICK_MODE.MEASURE;
  }
  if (["faces", "edges"].includes(selectionFilter)) return VIEWER_PICK_MODE.TOPOLOGY;
  if (
    viewerMode === "assembly" &&
    !topologyPickingActive &&
    (
      assemblyPickingActive ||
      !String(focusedPartIds || "").trim()
    )
  ) {
    return VIEWER_PICK_MODE.ASSEMBLY;
  }
  return VIEWER_PICK_MODE.AUTO;
}
